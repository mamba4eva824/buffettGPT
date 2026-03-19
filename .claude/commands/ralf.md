---
description: "Run the RALF (Review-Audit-Loop-Fix) execution workflow on TodoWrite tasks"
---

# RALF (Review-Audit-Loop-Fix) — Execution Workflow

You are entering the RALF execution phase. Execute the tasks in the TodoWrite list following this strict loop.

## Ground Rule
> "Done" is not a feeling. Done = acceptance criteria met + gates pass + review passes.

## Execution Loop

For each task in the TodoWrite list:

### 1. IMPLEMENT

- Mark task as `in_progress`
- **Spawn an Implementer agent** (from `.claude/agents/implementer.md`) via Task tool:
  - Pass it the task description, acceptance criteria, and files to touch
  - The Implementer will make minimal, focused changes and report back
  - If it returns `STATUS: ARCHITECTURE_MISMATCH`, STOP and tell user to run `/gsd` again
- If the task requires understanding unfamiliar code first, **spawn a Researcher agent** (from `.claude/agents/researcher.md`) before the Implementer to gather context

### 2. VERIFY (Gates)

**Spawn a Verifier agent** (from `.claude/agents/verifier.md`) via Task tool:
- Pass it the list of files that were changed
- The Verifier will select and run the relevant gates:
  - Python tests: `cd chat-api/backend && make test`
  - Frontend lint: `cd frontend && npm run lint`
  - Terraform validate: `cd chat-api/terraform/environments/dev && terraform validate`
  - Lambda build: `cd chat-api/backend && ./scripts/build_lambdas.sh`
- It will return a structured Verification Report with PASS/FAIL per gate

If any gate fails, fix the issue (or spawn the Implementer again with the fix instructions) and re-run the Verifier. Do NOT proceed with failing gates.

### 3. REVIEW (Semantic Check)

**Spawn a Reviewer agent** (from `.claude/agents/reviewer.md`) via Task tool:
- Pass it the acceptance criteria and the files that were changed
- The Reviewer will check:
  - Does the code satisfy each acceptance criterion?
  - Are there security issues (injection, auth flaws)?
  - Are there side effects or regressions?
  - Does it follow existing codebase patterns?
- It will return PASS or FAIL with specific blockers

If the Reviewer returns FAIL, fix the blockers and re-run both Verifier and Reviewer.

### 4. LEARN
- If a failure occurred, note the lesson for future tasks
- Update approach if patterns emerge

### 5. COMPLETE
- Mark task as `completed` in TodoWrite
- Move to next task

## Parallelism Rules

When multiple TodoWrite tasks have **no dependency edges** and touch **disjoint file sets**:
- Spawn separate Implementer agents for each task in parallel
- Run their Verifier agents concurrently after implementation
- Each still gets its own Reviewer step

Otherwise, execute serially.

## Architecture Mismatch Protocol
If the Implementer reports `ARCHITECTURE_MISMATCH`:
1. Surface the Implementer's explanation to the user
2. STOP execution
3. Tell the user to run `/gsd` again for replanning

## Completion
When all tasks are done and all gates pass, summarize what was accomplished and ask if the user wants to `/verify` (final gate check) or `/ship` (create PR).
