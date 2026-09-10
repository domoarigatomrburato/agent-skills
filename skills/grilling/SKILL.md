---
name: grilling
description: Challenge a plan or decision through focused questions. Use only when the user explicitly requests Grilling or asks to be grilled.
disable-model-invocation: true
---

# Grilling

Help the user reach a decision they can defend. Challenge assumptions and expose
consequences; keep the interview bounded by the decision they need to make.

## Establish the decision

Read the relevant context already available. Identify the outcome, constraints,
and unresolved choices. Investigate facts you can retrieve yourself before asking
the user. Distinguish verified facts, inferences, and preferences.

If the user has already settled a choice, carry it forward unless new evidence
materially challenges it. Use the project's language and existing decisions.

## Ask in useful rounds

Ask the few questions whose answers would most affect the next decision. Group
independent questions together; defer questions that depend on unanswered ones.
For each question, explain the tradeoff and give your recommendation when there
is enough evidence. Use concrete failure cases to challenge a vague answer.

Wait for the user's answers to preference or authority questions. Continue
independent fact-finding while waiting. Do not answer for the user or invent
additional questions merely to exhaust a decision tree. Use available tools
directly; this skill does not require agents or invoke other skills.

## Conclude

Stop when the material choices are settled, remaining uncertainty is acceptable
to the user, or the user asks to stop. Summarize the decision, its reasons, and
any unresolved risk or next experiment. A concise decision is a valid result;
a specification or acceptance-test inventory is not a required deliverable.

Treat the interview as discussion. Edit documents, implement, or publish only
when those actions are part of the user's request. Preserve existing authorization;
do not require another confirmation for work already authorized.
