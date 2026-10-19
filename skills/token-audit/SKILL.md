---
name: token-audit
description: Measure Claude Code token spend from the local transcripts. Reports input-token equivalents by source, session, agent type and context size; review runs and their fixed-prefix share; compactions and the files re-read after them; a replay of the compaction threshold; attribution by tool family; spend per commit, per closed issue and per ticket touched. Also probes each agent type's first-call prefix and compares saved reports against a log of configuration changes. Use only when the user explicitly requests the Token Audit skill.
disable-model-invocation: true
---

# Token audit

Claude Code writes every session to a JSONL transcript under `~/.claude/projects`
(`$CLAUDE_CONFIG_DIR/projects` when that variable is set). Each assistant line carries the
API usage of its call, so the transcripts are enough to measure where tokens go. This skill
turns a window of transcripts into a report, saves it, and compares it with earlier ones.
These files sit in this skill's folder:

- `scripts/token_audit.py`: the only entry point, standard-library Python 3.8+. It has four
  subcommands: `audit`, `compare`, `probe` and `note`.
- `tests/test_token_audit.py`: unit tests on a synthetic fixture (`tests/fixtures/`), run
  with `python3 -m unittest discover -s tests`.

Everything is saved under `~/.claude/token-audit/`: `reports/` (text and JSON),
`probes/` (JSON) and `changes.md` (the changes log). `--out DIR` points elsewhere. Never
save reports inside a repository: they contain session titles, session IDs and project paths.

## 1. When to run it

- Run it after each configuration change, once about a week of normal use has followed, and
  otherwise once a month.
- Run it whenever the user asks how much a setting, an agent type or a workflow costs.

The script skips the running session by itself: Claude Code exports its ID as
`CLAUDE_CODE_SESSION_ID`, and `audit` adds it to the skipped sessions shown in the report
(`--include-current` counts it). Add `--skip-session ID` for any other session to leave out.

## 2. How to run it

```bash
python3 scripts/token_audit.py audit --projects '-Users-me-code-myapp*' \
  --since 2026-10-19 --until 2026-10-26 \
  --git ~/code/myapp --author me@example.com --issue-key APP --label after-reviewer \
  --compare ~/.claude/token-audit/reports/2026-10-08_2026-10-18.json
```

- `--projects` is a glob on folder names under the root. A folder name is the session's
  working directory with `/` turned into `-`, so worktrees of a repository match
  `<repo-folder>*`. The default is every project.
- `--since` / `--until` take a date (local time; `--until` includes that whole day) or an
  ISO timestamp. A transcript, main session or subagent, counts when its first event
  falls in the window. Events after `--until` are ignored, so re-running a past window
  gives the same numbers later. The default is everything up to now.
- `--git REPO` (repeatable) counts the commits in the window and the issues they close
  (`Closes #12`, `Fixes owner/repo#13`). It reads only `HEAD`: commits on other branches
  are missed, so run it on the branch that collects the work, or merge first. Without
  `--since` the commits start at the first event of the selected transcripts, and without
  `--until` they end at the last one (not now); with no transcript selected and a bound
  missing, it counts no commits. The report prints the bounds used.
- `--issue-key PREFIX` (repeatable, or a comma list such as `--issue-key IDP,IW`) counts
  ticket keys such as `IDP-123` anywhere in the commit messages, for trackers like Jira.
  A prefix is an uppercase letter followed by uppercase letters, digits or `_`; keys are
  case-sensitive and deduplicated across repositories. There is no generic key pattern
  because one would match `UTF-8`, `SHA-256` or `ISO-8601`. A ticket counts as touched,
  not closed: a key in a commit does not mean the ticket is done. The ticket figures appear
  only with this option.
- `--author TEXT` (repeatable) counts only commits whose author name or e-mail contains
  TEXT (passed to `git log --author`; several values match any of them). It applies to
  commits, closed issues and tickets; spend stays the window's total. The report prints the
  filter, or `none`.
- `--label` is appended to the report name. `--compare OLD.json` prints the comparison and saves
  it next to the new report.
- `--replay 600000,400000,300000` sets the `autoCompactWindow` values to replay; the first
  is the reference. `--reread-calls 20` sets how many calls after a compaction count for
  re-reads.

The report name is `<since>_<until>[_label]` in local dates; `<until>` gains `THHMM` when
it is not a whole day, and `<since>` is `all` when unbounded. Compare two saved reports
later with `compare OLD.json NEW.json`. Record each configuration change on the day it
happens:

```bash
python3 scripts/token_audit.py note "autoCompactWindow 600000 -> 400000 for main sessions"
python3 scripts/token_audit.py note "reviewer agent type for review fan-out" --date 2026-10-18T14:30
```

## 3. How to read each section

- **ITE and the cost model.** Spend is in input-token equivalents of the same model: input
  1x, cache write 1h 2x, cache write 5m 1.25x (a usage without a 1h/5m split counts as 5m),
  cache read 0.1x, output 5x. The context of a call is input + cache write + cache read.
  This is a price ratio, not a bill. It is comparable across reports of the same model.
- **Split by source.** Every call re-sends the whole context, so when contexts are large,
  cache reads dominate. Cache writes follow new content and output follows generation.
- **Average context and share at 300k or more.** Large contexts make every call expensive.
  The band table shows where spend sits, and the share at 300k or more is the part a lower
  compaction threshold could move.
- **Per session.** One long-running session can dominate a window. Check the top rows before
  drawing conclusions from totals.
- **Per agent type and first-call context.** The first-call context is the fixed prefix:
  system prompt, tool schemas, CLAUDE.md files, skill listing, MCP and app tools, plus
  the first prompt. Every call of that agent reads it again. It is also split by entrypoint
  so that Desktop and headless prefixes never mix. The Desktop app's optional tool sets
  land here too: measured on two machines (October 2026), the browser tools added about
  8–11k to a main session's prefix and 5–8k to a `general-purpose` subagent's, and the
  iOS Simulator tools, where present, about 2.5k and 6.6k; agent types with a `tools:`
  allowlist (a read-only reviewer, implementers) were unaffected.
- **Review runs.** A subagent is a review agent when its type is `reviewer`, or when its
  description mentions review, simplify, inquisition, qualifier or verify, its type is not an
  implementer type and its description does not say fix or apply. Review agents of the same
  parent session form one run when each starts within 10 minutes of the previous one's end.
  The prefix share is the part of a run's spend that only pays for the agents' fixed
  prefixes. A high share means many small agents with large prefixes.
- **Compactions, re-reads and the rework hint.** For each compaction, the re-read is the
  tokens of files that the first N calls after it read again (Read, or `cat`/`sed`/`head`
  and similar in Bash), counting only files already read before the compaction. It is
  also given for the whole new segment. The rework hint counts edits in those first N calls to
  files already edited before the compaction. Re-reads are the cost a compaction adds back;
  the hint flags work that may have been redone.
- **The replay.** It is an estimate: it replays each main session's observed context
  growth under another `autoCompactWindow`. Assumptions: compaction triggers at
  0.95 x window, the post-compaction prefix and the summary have fixed sizes, observed
  compactions keep the simulated context, and the penalty is context re-added after each
  compaction (re-reads). Read the row whose penalty is the measured median re-read. Its
  change in percent of the grand total is the expected saving.
- **Attribution by tool family.** It estimates each content item's lifetime cost: written once,
  then read by every later call of its segment. Characters become tokens with a ratio calibrated on the
  window itself (`uncalibrated` means it fell back to 3.5). The rollup shows which tools
  fill the context, and the total exceeds direct spend because the model is approximate.
- **ITE per commit, per closed issue and per ticket touched.** These normalise for windows
  of different length and workload. Prefer them, and the per-session figures, over totals.
  With `--author` they count only your own commits against the window's whole spend, so
  they give the cost of your own work instead of being diluted by other people's commits.

## 4. Levers, ranked by the effect measured so far

1. **The compaction threshold** (`autoCompactWindow`) for main sessions. Watch average main
   context, share at 300k or more, compactions per main session, re-reads, and the replay.
2. **A read-only reviewer agent type** for review and verification fan-out. Watch the
   first-call context of `sub:reviewer`, review-run median ITE and prefix share.
3. **A `tools:` allowlist on implementer agent types.** Watch their first-call context.
4. **A smaller fixed prefix everywhere:** explicit-only skills, disabled unused plugins,
   fewer MCP servers and connectors, a slimmer global CLAUDE.md, and Desktop app tools
   such as the browser turned off when not needed. Watch first-call context per kind and
   the probes.
5. **Behaviour:** one session per issue instead of a day-long orchestrator. Watch ITE per
   main session, the top sessions' share, and ITE per closed issue.

Code-navigation tools (LSP, indexers, grep variants) rarely move spend by more than a few
percent. The Bash/search and LSP families in the rollup show their share.

## 5. Deciding the compaction threshold

Lower `autoCompactWindow` one step only when all of these hold over at least a week of
sessions run after the last change:

- the median main-session re-read per compaction (N-call window) stays well under about 30k
  tokens, and the maximum is rarely above it;
- the rework hint stays near zero;
- reading two or three post-compaction stretches of real sessions shows no rework:
  re-asked questions, repeated edits, or gates re-run on an unchanged tree.

Use the replay row with the measured penalty for the expected saving. Go back one step when
re-reads approach 30k or rework appears. Agent types that pin their own window in their
frontmatter are not affected by the setting.

## 6. Compare like with like

Desktop sessions carry the app's own tools and connectors, so their prefixes are much larger
than headless ones. Compare reports from the same host and the same entrypoint mix;
`compare` warns when either differs, and when the git repositories, author filters or
issue-key prefixes differ. Prefer per-session, per-commit and per-issue figures
over totals. Read the changes-log entries that `compare` lists between the two reports;
entries marked `inside new window` happened during the new window and only partly apply
to it.

## 7. Probes

A probe measures each agent type's first-call prefix in a session started for that purpose.

- **Headless:** `python3 scripts/token_audit.py probe` runs `claude -p` in a fresh empty
  temporary folder and asks it to start one subagent per type (default
  `reviewer,implementer:opus:medium,general-purpose:opus`; `--agents` takes `type`,
  `type:model` or `type:model:effort`, `--model` sets the main session's model). Then it
  reads the new session's transcript and removes the folder. It records each agent's
  prefix and model, the main session's prefix, the CLI version, and any requested type
  that started no subagent. Run it from a plain terminal when possible. From inside a
  Claude session the script removes the session's inherited variables before starting
  `claude -p` (their names are listed in the probe file as `env_removed`); a warning after
  the table means the child still did not run as headless.
- **Desktop (manual):** in a fresh Desktop session started in an empty folder whose name
  begins with `token-audit-probe-` (e.g. `/private/tmp/token-audit-probe-browser-on`, so
  audits skip it), type:

  > Call the Agent tool once per type, in parallel: reviewer, implementer with model opus and effort medium, general-purpose with model opus. Give each exactly this prompt: 'Reply with the single word OK. Use no tools.' Then reply DONE.

  Then run `python3 scripts/token_audit.py probe --read current --label browser-on`
  from that session, or `probe --read latest` from another one.
- **Desktop (side session):** from a Desktop session, when the user asks for it in words,
  Claude can start a fresh side session (`start_session`) whose working folder is an empty
  `/private/tmp/token-audit-probe-<label>` (the real path: the app refuses symlinked paths
  such as `/tmp`) and whose prompt is the probe text above. When it finishes, run
  `probe --read latest --label <label>`, or pass its transcript ID. The side session's
  brief and background add a few hundred tokens to its main session's first prompt, so
  that main prefix reads slightly high; the subagent prefixes are not affected. The app
  requires a background of at least 80 characters: keep it to one neutral line. A probe
  session may make one more tool call after the first, which does not change the
  first-call prefix.

Do one Desktop run with each app tool set on and one with it off, for example
`--label browser-on` / `browser-off`. The browser and iOS Simulator toggles are in the app's
Settings → Claude Code; only the user can change them, and only a new session picks the
change up.

The probe sessions' transcripts stay under the projects root, in folders named after their
`token-audit-probe-` working folder, and `audit` always skips those folders.

Probes are saved as `probes/<YYYYmmdd-HHMMSS>_<mode>[_label].json`, where the mode is
`desktop` or `headless`. Compare only probes of the same mode.

## 8. The changes log

`~/.claude/token-audit/changes.md` holds one line per configuration change:
`- YYYY-MM-DD text` or `- YYYY-MM-DDTHH:MM text`. Record every change with `note` on the
day it happens. Settings, agent definitions, CLAUDE.md edits, plugins, MCP servers,
connectors, skills and CLI upgrades all count. Without the log, `compare` cannot say which
change a difference belongs to.
