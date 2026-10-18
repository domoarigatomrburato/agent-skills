import glob
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
FIXTURES = SKILL / "tests" / "fixtures" / "projects"
S1 = "11111111-1111-1111-1111-111111111111"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


token_audit = load_module("token_audit", SKILL / "scripts" / "token_audit.py")


def without_current_session(case):
    """The tests may run inside a Claude session, which exports its own session id."""
    patcher = patch.dict(os.environ)
    patcher.start()
    case.addCleanup(patcher.stop)
    os.environ.pop("CLAUDE_CODE_SESSION_ID", None)


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = token_audit.main(argv)
    return code, buf.getvalue()


class AuditCase(unittest.TestCase):
    def setUp(self):
        without_current_session(self)
        self.out = tempfile.mkdtemp(prefix="token-audit-test-")
        self.addCleanup(shutil.rmtree, self.out, True)

    def audit(self, *extra):
        argv = ["audit", "--root", str(FIXTURES), "--out", self.out,
                "--projects", "-Users-test-proj*", "--since", "2026-10-08"] + list(extra)
        code, text = run(argv)
        self.assertEqual(code, 0, text)
        reports = sorted(glob.glob(os.path.join(self.out, "reports", "*.json")))
        self.assertEqual(len(reports), 1, reports)
        with open(reports[0]) as fh:
            return json.load(fh), text


class WindowedAuditTests(AuditCase):
    def setUp(self):
        super().setUp()
        self.report, self.text = self.audit("--until", "2026-10-11")

    def test_calibration_uses_the_only_qualifying_interval(self):
        # C1 -> C2: 5000 chars of tool result; delta = ctx(C2) - ctx(C1) - out(C1)
        # = 22110 - 20010 - 100 = 2000 tokens, so 5000 / 2000 = 2.5 chars/token.
        att = self.report["attribution"]
        self.assertAlmostEqual(att["chars_per_token"], 2.5)
        self.assertEqual(att["intervals"], 1)
        self.assertTrue(att["calibrated"])

    def test_main_direct_spend(self):
        main = self.report["spend"]["main"]
        self.assertEqual(main["calls"], 6)
        # C1 10 + 20000*2 + 100*5                  = 40510
        # C2 10 + 2100*2 + 20000*0.1 + 200*5      =  7210
        # C3 10 + 600*2 + 309990*0.1 + 300*5      = 33709
        # C4 10 + 15000*2 + 50*5                  = 30260
        # C5 10 + 1100*2 + 15000*0.1 + 50*5       =  3960
        # C6 10 + 1300*2 + 16100*0.1 + 400*5      =  6220
        self.assertAlmostEqual(main["ite"], 121869)
        self.assertAlmostEqual(main["input"], 60)          # 6 * 10
        self.assertAlmostEqual(main["cache_write"], 80200)  # 2 * (20000+2100+600+15000+1100+1300)
        self.assertAlmostEqual(main["cache_read"], 36109)   # 0.1 * (20000+309990+15000+16100)
        self.assertAlmostEqual(main["output"], 5500)        # 5 * (100+200+300+50+50+400)
        # contexts 20010 + 22110 + 310600 + 15010 + 16110 + 17410 = 401250; / 6
        self.assertAlmostEqual(main["avg_ctx"], 66875)

    def test_sub_and_total_direct_spend(self):
        sub = self.report["spend"]["sub"]
        self.assertEqual(sub["calls"], 2)
        # S1 5 + 8000*1.25 (5m split) + 20*5            = 10105
        # S2 5 + 400*1.25 (no split: all 5m) + 8000*0.1 + 10*5 = 1355
        self.assertAlmostEqual(sub["ite"], 11460)
        # contexts 8005 + 8405 = 16410; / 2
        self.assertAlmostEqual(sub["avg_ctx"], 8205)
        tot = self.report["spend"]["all"]
        self.assertAlmostEqual(tot["ite"], 133329)  # 121869 + 11460
        self.assertAlmostEqual(tot["input"], 70)    # 60 + 10
        self.assertAlmostEqual(tot["cache_write"], 90700)  # 80200 + 10000 + 500
        self.assertAlmostEqual(tot["cache_read"], 36909)   # 36109 + 800
        self.assertAlmostEqual(tot["output"], 5650)        # 5500 + 150

    def test_share_above_300k(self):
        # only C3 (context 310600) is at or above 300k
        self.assertAlmostEqual(self.report["share_300k"]["all"], 33709 / 133329)
        self.assertAlmostEqual(self.report["share_300k"]["main"], 33709 / 121869)

    def test_first_call_context(self):
        kinds = self.report["kinds"]
        self.assertEqual(kinds["main"]["first_ctx"]["median"], 20010)       # 10 + 20000
        self.assertEqual(kinds["sub:reviewer"]["first_ctx"]["median"], 8005)  # 5 + 8000
        by_ep = self.report["first_ctx_by_entrypoint"]
        self.assertEqual(by_ep["main"]["claude-desktop"]["median"], 20010)

    def test_review_runs(self):
        review = self.report["review"]
        self.assertEqual(review["summary"]["runs"], 1)
        run0 = review["runs"][0]
        self.assertEqual(run0["agents"], 1)
        self.assertEqual(run0["parent"], S1)
        self.assertAlmostEqual(run0["ite"], 11460)
        # prefix = input part of S1 (5 + 8000*1.25 = 10005) + 0.1 * 8005 * (2 - 1)
        self.assertAlmostEqual(run0["prefix_share"], (10005 + 0.1 * 8005 * 1) / 11460)

    def test_compactions_and_rereads(self):
        comp = self.report["compactions"]
        self.assertEqual(comp["main"], 1)
        self.assertEqual(comp["main_sessions_with"], 1)
        self.assertEqual(comp["post_prefix_median"], 15010)  # ctx(C4) = 10 + 15000
        rows = comp["list"]
        self.assertEqual(len(rows), 1)
        # /repo/a.swift re-read after the boundary: 2500 chars / 2.5 = 1000 tokens;
        # /repo/c.swift is new, so the whole segment also counts 1000.
        self.assertAlmostEqual(rows[0]["reread_window"], 1000)
        self.assertAlmostEqual(rows[0]["reread_segment"], 1000)
        self.assertEqual(rows[0]["rework_hint"], 0)
        self.assertEqual(rows[0]["post_prefix"], 15010)
        self.assertAlmostEqual(comp["reread"]["median"], 1000)

    def test_excluded_transcripts_are_not_counted(self):
        # S2 (before since), the other project and C7 (after until) are absent.
        ids = [s["session"] for s in self.report["main_sessions"]]
        self.assertEqual(ids, [S1])
        self.assertEqual(self.report["main_sessions"][0]["title"], "Fixture session")
        self.assertEqual(self.report["selection"]["transcripts"], {"main": 1, "sub:reviewer": 1})

    def test_report_files_and_name(self):
        reports = sorted(os.listdir(os.path.join(self.out, "reports")))
        self.assertEqual(reports, ["2026-10-08_2026-10-11.json", "2026-10-08_2026-10-11.txt"])
        self.assertEqual(self.report["schema"], 1)
        self.assertIn("2026-10-08_2026-10-11.json", self.text)


class UnboundedAuditTests(AuditCase):
    def test_without_until_counts_the_late_call(self):
        report, _ = self.audit()
        # C7: 1 + 17410 * 0.1 = 1742
        self.assertEqual(report["spend"]["main"]["calls"], 7)
        self.assertAlmostEqual(report["spend"]["main"]["ite"], 121869 + 1742)

    def test_skip_session_drops_session_and_subagents(self):
        report, _ = self.audit("--until", "2026-10-11", "--skip-session", S1)
        self.assertEqual(report["spend"]["main"]["calls"], 0)
        self.assertEqual(report["spend"]["sub"]["calls"], 0)
        self.assertEqual(report["main_sessions"], [])


class ReworkHintTests(AuditCase):
    def test_edit_of_a_file_edited_before_the_boundary(self):
        root = tempfile.mkdtemp(prefix="token-audit-root-")
        self.addCleanup(shutil.rmtree, root, True)
        proj = os.path.join(root, "-p")
        os.makedirs(proj)

        def asst(sec, mid, tid):
            return {"type": "assistant", "timestamp": "2026-10-10T10:00:%02d.000Z" % sec,
                    "message": {"id": mid, "model": "m", "usage": {
                        "input_tokens": 1, "cache_creation_input_tokens": 100,
                        "cache_read_input_tokens": 0, "output_tokens": 1},
                        "content": [{"type": "tool_use", "id": tid, "name": "Edit",
                                     "input": {"file_path": "/x", "old_string": "a", "new_string": "b"}}]}}

        def res(sec, tid):
            return {"type": "user", "timestamp": "2026-10-10T10:00:%02d.000Z" % sec,
                    "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": "ok"}]}}

        events = [
            {"type": "user", "timestamp": "2026-10-10T10:00:00.000Z", "message": {"content": "go"}},
            asst(1, "m1", "t1"), res(2, "t1"),
            {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-10-10T10:00:03.000Z"},
            {"type": "user", "timestamp": "2026-10-10T10:00:04.000Z", "isCompactSummary": True,
             "message": {"content": "summary"}},
            asst(5, "m2", "t2"), res(6, "t2"),
        ]
        with open(os.path.join(proj, "s.jsonl"), "w") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")
        code, text = run(["audit", "--root", root, "--out", self.out, "--since", "2026-10-08",
                          "--until", "2026-10-11"])
        self.assertEqual(code, 0, text)
        path = glob.glob(os.path.join(self.out, "reports", "*.json"))[0]
        with open(path) as fh:
            report = json.load(fh)
        self.assertEqual(report["compactions"]["list"][0]["rework_hint"], 1)
        self.assertEqual(report["compactions"]["reread"]["rework_total"], 1)


def write_events(path, events):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def usage_event(ts, mid, content=()):
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": mid, "model": "m", "usage": {
                "input_tokens": 1, "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": 0, "output_tokens": 1}, "content": list(content)}}


class DuplicateBoundaryTests(AuditCase):
    def test_replayed_boundary_and_its_events_are_counted_once(self):
        # A transcript that re-appends an earlier boundary (same uuid) and the events after it
        # (an assistant line with a Read and an Edit, and their tool results) has one
        # compaction, one re-read and one rework hint; the replayed boundary is reported as ignored.
        root = tempfile.mkdtemp(prefix="token-audit-root-")
        self.addCleanup(shutil.rmtree, root, True)

        def ts(sec):
            return "2026-10-10T10:00:%02d.000Z" % sec

        def uses(read_id, edit_id):
            return [{"type": "tool_use", "id": read_id, "name": "Read", "input": {"file_path": "/a.swift"}},
                    {"type": "tool_use", "id": edit_id, "name": "Edit",
                     "input": {"file_path": "/x", "old_string": "a", "new_string": "b"}}]

        def results(sec, read_id, edit_id, chars):
            return {"type": "user", "timestamp": ts(sec), "message": {"content": [
                {"type": "tool_result", "tool_use_id": read_id, "content": "r" * chars},
                {"type": "tool_result", "tool_use_id": edit_id, "content": "ok"}]}}

        boundary = {"type": "system", "subtype": "compact_boundary", "uuid": "b-1", "timestamp": ts(3)}
        write_events(os.path.join(root, "-p", "s.jsonl"), [
            {"type": "user", "timestamp": ts(0), "message": {"content": "go"}},
            usage_event(ts(1), "m1", uses("t1", "e1")), results(2, "t1", "e1", 500),
            boundary,
            usage_event(ts(4), "m2", uses("t2", "e2")), results(5, "t2", "e2", 1000),
            # replayed copies: the boundary, the post-boundary call and its results
            boundary,
            usage_event(ts(4), "m2", uses("t2", "e2")), results(5, "t2", "e2", 1000),
            usage_event(ts(7), "m3"),
        ])
        code, text = run(["audit", "--root", root, "--out", self.out, "--since", "2026-10-08",
                          "--until", "2026-10-11"])
        self.assertEqual(code, 0, text)
        path = glob.glob(os.path.join(self.out, "reports", "*.json"))[0]
        with open(path) as fh:
            report = json.load(fh)
        comp = report["compactions"]
        self.assertEqual(comp["main"], 1)
        self.assertEqual(comp["duplicates_ignored"], 1)
        self.assertEqual(len(comp["list"]), 1)
        self.assertEqual(report["main_sessions"][0]["compactions"], 1)
        self.assertEqual(report["spend"]["main"]["calls"], 3)
        # no interval qualifies for calibration (needs > 4000 chars), so R = 3.5;
        # the re-read of /a.swift counts once: 1000 / 3.5
        self.assertAlmostEqual(report["attribution"]["chars_per_token"], 3.5)
        self.assertAlmostEqual(comp["list"][0]["reread_window"], 1000 / 3.5)
        self.assertAlmostEqual(comp["list"][0]["reread_segment"], 1000 / 3.5)
        self.assertEqual(comp["list"][0]["rework_hint"], 1)


class ReviewAgentRuleTests(AuditCase):
    def test_agents_applying_review_findings_are_not_review_agents(self):
        # reviewer and "Simplify review: reuse" are review agents; an implementer type and an
        # "Apply ... fixes" description are not, even though both descriptions match REVIEW_RE.
        root = tempfile.mkdtemp(prefix="token-audit-root-")
        self.addCleanup(shutil.rmtree, root, True)
        start = {"type": "user", "timestamp": "2026-10-10T10:00:00.000Z", "message": {"content": "go"}}
        write_events(os.path.join(root, "-p", "parent.jsonl"),
                     [start, usage_event("2026-10-10T10:00:01.000Z", "m0")])
        sub = os.path.join(root, "-p", "parent", "subagents")
        agents = [("agent-r1", "reviewer", "Review: correctness"),
                  ("agent-g1", "general-purpose", "Simplify review: reuse"),
                  ("agent-i1", "implementer-opus-high", "Simplify fixes: X"),
                  ("agent-g2", "general-purpose", "Apply code-review fixes")]
        for i, (name, kind, desc) in enumerate(agents):
            write_events(os.path.join(sub, name + ".jsonl"), [
                {"type": "user", "timestamp": "2026-10-10T10:01:%02d.000Z" % (2 * i), "message": {"content": "go"}},
                usage_event("2026-10-10T10:01:%02d.000Z" % (2 * i + 1), "m-" + name)])
            with open(os.path.join(sub, name + ".meta.json"), "w") as fh:
                json.dump({"agentType": kind, "description": desc}, fh)
        code, text = run(["audit", "--root", root, "--out", self.out, "--since", "2026-10-08",
                          "--until", "2026-10-11"])
        self.assertEqual(code, 0, text)
        with open(glob.glob(os.path.join(self.out, "reports", "*.json"))[0]) as fh:
            review = json.load(fh)["review"]
        self.assertEqual(review["summary"]["runs"], 1)
        self.assertEqual(review["runs"][0]["agents"], 2)
        self.assertEqual(review["runs"][0]["types"], {"reviewer": 1, "general-purpose": 1})


class ProbeFolderTests(AuditCase):
    def test_audit_skips_headless_probe_folders(self):
        root = tempfile.mkdtemp(prefix="token-audit-root-")
        self.addCleanup(shutil.rmtree, root, True)
        start = {"type": "user", "timestamp": "2026-10-10T10:00:00.000Z", "message": {"content": "go"}}
        write_events(os.path.join(root, "-p", "s.jsonl"),
                     [start, usage_event("2026-10-10T10:00:01.000Z", "m1")])
        write_events(os.path.join(root, "-private-var-folders-xy-T-token-audit-probe-abc123", "q.jsonl"),
                     [start, usage_event("2026-10-10T10:00:01.000Z", "m2")])
        report, _ = self.audit_root(root)
        self.assertEqual(report["spend"]["main"]["calls"], 1)
        self.assertEqual([s["session"] for s in report["main_sessions"]], ["s"])

    def audit_root(self, root):
        code, text = run(["audit", "--root", root, "--out", self.out, "--projects", "*",
                          "--since", "2026-10-08", "--until", "2026-10-11"])
        self.assertEqual(code, 0, text)
        with open(glob.glob(os.path.join(self.out, "reports", "*.json"))[0]) as fh:
            return json.load(fh), text


class ReplayTests(unittest.TestCase):
    def test_replay_matches_hand_computation(self):
        calls = [dict(inp=0, cw=c, cr=0, cw1h=0, cw5m=0, out=0, seg=0) for c in (100, 200, 300)]
        # call 1: ctx 100, growth 100 -> 100*2                         = 200
        # call 2: ctx 200, growth 100 -> 100*0.1 + 100*2              = 210
        # call 3: ctx 300 > 250 -> compaction 300*0.1 + 10*5 + 50*2   = 180
        #         then ctx 50, growth 0 -> 50*0.1                     =   5
        ite, comps = token_audit.replay(calls, 250, 0, post=50, summary_out=10)
        self.assertAlmostEqual(ite, 595)
        self.assertEqual(comps, 1)


@unittest.skipIf(shutil.which("git") is None, "git is not installed")
class GitTests(AuditCase):
    def test_commits_and_closed_issues(self):
        repo = tempfile.mkdtemp(prefix="token-audit-git-")
        self.addCleanup(shutil.rmtree, repo, True)

        def git(*args, date=None):
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
            if date:
                env["GIT_AUTHOR_DATE"] = date
                env["GIT_COMMITTER_DATE"] = date
            subprocess.run(["git", "-C", repo] + list(args), check=True, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        git("init", "-q")
        git("commit", "-q", "--allow-empty", "-m", "Old work", "-m", "Closes #99",
            date="2026-09-01T12:00:00+00:00")
        git("commit", "-q", "--allow-empty", "-m", "Plain change", date="2026-10-09T12:00:00+00:00")
        git("commit", "-q", "--allow-empty", "-m", "Fix one", "-m", "Closes #12",
            date="2026-10-10T12:00:00+00:00")
        git("commit", "-q", "--allow-empty", "-m", "Fix two", "-m", "fixes: #12\nResolves owner/repo#13",
            date="2026-10-10T13:00:00+00:00")
        report, _ = self.audit("--until", "2026-10-11", "--git", repo)
        g = report["git"]
        self.assertEqual(g["commits"], 3)
        self.assertEqual(g["closing_commits"], 2)
        self.assertEqual(g["closed_issues"], 2)  # #12 and owner/repo#13
        self.assertAlmostEqual(g["ite_per_commit"], 133329 / 3)
        self.assertAlmostEqual(g["ite_per_issue"], 133329 / 2)


class ChangesLogAndCompareTests(AuditCase):
    def make_report(self, since, until, label):
        code, text = run(["audit", "--root", str(FIXTURES), "--out", self.out,
                          "--projects", "-Users-test-proj*", "--since", since, "--until", until,
                          "--label", label])
        self.assertEqual(code, 0, text)
        return os.path.join(self.out, "reports", "%s_%s_%s.json" % (since, until, label))

    def test_note_creates_heading_and_appends(self):
        run(["note", "first change", "--date", "2026-10-18", "--out", self.out])
        run(["note", "second change", "--date", "2026-10-18T14:30", "--out", self.out])
        with open(os.path.join(self.out, "changes.md")) as fh:
            lines = fh.read().splitlines()
        self.assertEqual(lines[0], "# Configuration changes")
        self.assertIn("- 2026-10-18 first change", lines)
        self.assertIn("- 2026-10-18T14:30 second change", lines)

    def test_compare_lists_changes_between_reports(self):
        old = self.make_report("2026-10-01", "2026-10-09", "old")
        new = self.make_report("2026-10-10", "2026-10-11", "new")
        for date, text in (("2026-09-30", "too early"), ("2026-10-09", "between windows"),
                           ("2026-10-10T09:00", "inside window"), ("2026-10-12", "too late")):
            run(["note", text, "--date", date, "--out", self.out])
        code, text = run(["compare", old, new, "--out", self.out])
        self.assertEqual(code, 0, text)
        lines = text.splitlines()
        between = [l for l in lines if "between windows" in l]
        inside = [l for l in lines if "inside window" in l and "2026-10-10T09:00" in l]
        self.assertEqual(len(between), 1)
        self.assertNotIn("inside new window", between[0])
        self.assertEqual(len(inside), 1)
        self.assertIn("inside new window", inside[0])
        self.assertNotIn("too early", text)
        self.assertNotIn("too late", text)

    def test_compare_with_itself_has_no_changes(self):
        path = self.make_report("2026-10-08", "2026-10-11", "self")
        with open(path) as fh:
            report = json.load(fh)
        text, rows = token_audit.compare_reports(report, report, [])
        self.assertTrue(rows)
        for label, old, new in rows:
            self.assertEqual(old, new, label)
        self.assertNotIn("WARNING", text)
        code, out = run(["compare", path, path, "--out", self.out])
        self.assertEqual(code, 0, out)


class CurrentSessionTests(AuditCase):
    def test_audit_skips_the_running_session(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": S1}):
            report, _ = self.audit("--until", "2026-10-11")
        self.assertEqual(report["spend"]["main"]["calls"], 0)
        self.assertEqual(report["spend"]["sub"]["calls"], 0)
        self.assertEqual(report["selection"]["skip_sessions"], [S1])

    def test_include_current_counts_the_running_session(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": S1}):
            report, _ = self.audit("--until", "2026-10-11", "--include-current")
        self.assertEqual(report["spend"]["main"]["calls"], 6)
        self.assertEqual(report["selection"]["skip_sessions"], [])

    def test_explicit_skip_is_not_repeated(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": S1}):
            report, _ = self.audit("--until", "2026-10-11", "--skip-session", S1)
        self.assertEqual(report["selection"]["skip_sessions"], [S1])

    def test_probe_reads_the_current_session(self):
        with patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": S1}):
            code, text = run(["probe", "--read", "current", "--root", str(FIXTURES), "--out", self.out])
        self.assertEqual(code, 0, text)
        with open(glob.glob(os.path.join(self.out, "probes", "*.json"))[0]) as fh:
            probe = json.load(fh)
        self.assertEqual(probe["session"], S1)
        self.assertEqual(probe["agents"][0]["prefix"], 8005)

    def test_probe_current_without_the_variable_fails(self):
        with self.assertRaises(SystemExit):
            run(["probe", "--read", "current", "--root", str(FIXTURES), "--out", self.out])


class ProbeEnvTests(unittest.TestCase):
    def test_inherited_session_variables_are_removed(self):
        environ = {
            "CLAUDE_CODE_ENTRYPOINT": "claude-desktop", "CLAUDE_CODE_SESSION_ID": "x",
            "CLAUDE_CODE_TERMINAL_MCP_TOOLS": "1", "CLAUDE_AGENT_SDK_VERSION": "1",
            "CLAUDE_PREVIEW_CLASSIFIER_FLOOR": "1", "MCP_CONNECTION_NONBLOCKING": "1",
            "CLAUDECODE": "1", "CLAUDE_PID": "1", "CLAUDE_EFFORT": "high",
            "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_USE_VERTEX": "1", "CLAUDE_CODE_USE_FOUNDRY": "1",
            "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1", "CLAUDE_CODE_SKIP_VERTEX_AUTH": "1",
            "CLAUDE_CODE_SKIP_FOUNDRY_AUTH": "1", "CLAUDE_CODE_OAUTH_TOKEN": "secret",
            "ANTHROPIC_BASE_URL": "u", "CLAUDE_CONFIG_DIR": "/c", "PATH": "/bin", "HOME": "/h",
            "CLAUDECODE_OTHER": "kept", "CLAUDE_PIDFILE": "kept",
        }
        env, removed = token_audit.probe_env(environ)
        self.assertEqual(removed, sorted([
            "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_TERMINAL_MCP_TOOLS",
            "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_PREVIEW_CLASSIFIER_FLOOR", "MCP_CONNECTION_NONBLOCKING",
            "CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT"]))
        self.assertEqual(set(env), set(environ) - set(removed))
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "secret")
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(environ["CLAUDE_CODE_ENTRYPOINT"], "claude-desktop")  # input not mutated


class ProbeTests(unittest.TestCase):
    def setUp(self):
        without_current_session(self)

    def test_read_existing_session(self):
        out = tempfile.mkdtemp(prefix="token-audit-probe-test-")
        self.addCleanup(shutil.rmtree, out, True)
        code, text = run(["probe", "--read", S1, "--root", str(FIXTURES), "--out", out, "--label", "t"])
        self.assertEqual(code, 0, text)
        files = glob.glob(os.path.join(out, "probes", "*_desktop_t.json"))
        self.assertEqual(len(files), 1, os.listdir(out))
        with open(files[0]) as fh:
            probe = json.load(fh)
        self.assertEqual(probe["mode"], "desktop")
        self.assertEqual(probe["version"], "2.1.300")
        self.assertEqual(probe["main_prefix"], 20010)
        agents = probe["agents"]
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["type"], "reviewer")
        self.assertEqual(agents[0]["prefix"], 8005)

    def test_latest_is_the_newest_started_session_with_subagents(self):
        # The older-started session was modified last (as a running session would be);
        # latest must still pick the session that started most recently.
        root = tempfile.mkdtemp(prefix="token-audit-root-")
        self.addCleanup(shutil.rmtree, root, True)
        paths = {}
        for sid, day in (("old", "2026-10-10"), ("new", "2026-10-12"), ("nosub", "2026-10-14")):
            paths[sid] = os.path.join(root, "-p", sid + ".jsonl")
            write_events(paths[sid], [{"type": "user", "timestamp": day + "T10:00:00.000Z",
                                       "message": {"content": "go"}}])
            if sid != "nosub":
                os.makedirs(os.path.join(root, "-p", sid, "subagents"))
        os.utime(paths["new"], (1_000_000, 1_000_000))
        os.utime(paths["old"], (2_000_000, 2_000_000))
        self.assertEqual(token_audit.latest_session(root), paths["new"])

    def test_probe_prompt(self):
        self.assertEqual(
            token_audit.probe_prompt(["reviewer", "implementer-opus-medium", "general-purpose:opus"]),
            "Call the Agent tool once per type, in parallel: reviewer, implementer-opus-medium, "
            "general-purpose with model opus. Give each exactly this prompt: 'Reply with the single "
            "word OK. Use no tools.' Then reply DONE.")
        self.assertIn("a with model sonnet", token_audit.probe_prompt(["a:sonnet"]))


class CalibrationTests(unittest.TestCase):
    def test_no_qualifying_interval_is_uncalibrated(self):
        r, n, p25, p75 = token_audit.calibrate([])
        self.assertEqual((r, n, p25, p75), (3.5, 0, 3.5, 3.5))
        one_call = [dict(calls=[dict(inp=1, cw=0, cr=0, out=0, seg=0)], items=[])]
        self.assertEqual(token_audit.calibrate(one_call)[0], 3.5)


if __name__ == "__main__":
    unittest.main()
