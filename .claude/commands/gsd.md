---
description: "Run the GSD (Get Stuff Done) planning workflow — Audit, PRD, Plan, Tasks, Approval"
---

# GSD (Get Stuff Done) — Specification & Planning Workflow

You are entering the GSD planning phase. Follow these steps strictly before any implementation begins.

## Step 1: Audit Snapshot

**Spawn parallel agents** to gather context before planning:

- **Researcher agent** (from `.claude/agents/researcher.md`): Explore the codebase for files, patterns, and existing implementations related to the user's request. Identify relevant Lambda handlers, DynamoDB tables, Terraform modules, and frontend components. Produce a structured research summary.
- **Researcher agent** (second instance): Check for existing tests, utilities, and schemas related to the request. Search `chat-api/backend/tests/`, shared utils, and Terraform state for anything that may be affected.

Launch both via the Task tool (`subagent_type=general-purpose`) in parallel, providing each with the researcher agent prompt from `.claude/agents/researcher.md`.

While agents are running, begin drafting the audit from what you already know:
- **Knowns / Evidence**: What's certain from the user's request and the codebase
- **Unknowns / Gaps**: Missing info that could change decisions
- **Constraints**: Time, infra, dependencies, policies (refer to CLAUDE.md for project-specific constraints)
- **Risks**: Top 3 things that could sink the plan

When agents return, incorporate their findings into the audit.

## Step 2: PRD (Acceptance Criteria)
Create acceptance criteria that are:
- **Observable**: Can be seen/measured
- **Testable**: Has a pass/fail condition
- **Phrased as Given/When/Then** or equivalent

Example:
```
AC-1: Given a logged-in user, when they click "Export", then a CSV downloads within 3 seconds.
AC-2: Given invalid input, when submitted, then an error message appears (no console errors).
```

## Step 3: Implementation Plan

**Spawn an Explorer-Alternatives agent** (from `.claude/agents/explorer-alternatives.md`) via Task tool:
- Pass it the audit snapshot and acceptance criteria
- Ask it to generate 2-4 alternative approaches with trade-offs
- Use its recommendation matrix to pick the best approach

Then draft the plan:
- **Objective**: One sentence
- **Approach Summary**: One paragraph
- **Steps**: Numbered, minimal but complete
- **Files to Modify**: List expected file changes
- **Verification Commands**: How to test each step

## Step 4: Task Graph
Break the plan into atomic tasks using `TodoWrite`. Each task must have:
- Clear acceptance criteria
- Dependencies (what must complete first)
- Expected files to touch
- Verification command

## Step 5: Self-Critique (Red Team)

**Spawn a Challenger agent** (from `.claude/agents/challenger.md`) via Task tool:
- Pass it the full plan, PRD, and task list
- It will return a Challenge Report with Critical Blockers, High/Medium risks, and a PROCEED/PAUSE recommendation

If the Challenger recommends PAUSE FOR REPLANNING, revise the plan before presenting to the user.

## Step 6: User Approval
**STOP and ask the user** before proceeding to execution:
- Present the PRD, task list, and Challenger's findings
- Ask for approval or adjustments
- Do NOT proceed until user confirms

When user approves, tell them to run `/ralf` to begin execution.
