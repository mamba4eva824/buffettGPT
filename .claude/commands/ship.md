---
description: "Final verification, commit, and PR creation workflow"
---

# Ship — Final Verification & PR Creation

Prepare the current work for shipping. Follow these steps in order.

## Step 1: Final Gate Check

**Spawn a Verifier agent** (from `.claude/agents/verifier.md`) via Task tool with the full verification suite. If any gate fails, fix the issue before proceeding. Do NOT ship with failing gates.

## Step 2: Change Summary

**Spawn two agents in parallel:**

- **Reviewer agent** (from `.claude/agents/reviewer.md`): Review all changed files against the original acceptance criteria. Check for any last-minute issues, security concerns, or missing edge cases.
- **Bash agent** (`subagent_type=Bash`): Run `git diff --stat` and `git log --oneline` for the current branch vs the base branch to get the full scope of changes.

Use their output to produce a summary:
- List all modified/created/deleted files
- Summarize the purpose of each change
- Note any breaking changes or migration steps needed

## Step 3: Commit
Stage and commit all changes with a descriptive commit message following conventional commits format. Ask the user for approval of the commit message before committing.

## Step 4: Create PR
Create a pull request using `gh pr create` with:
- A concise title (under 70 characters)
- Body with Summary (bullet points), Test Plan, and any migration notes
- Target branch: `dev` (or as specified by user)

## Step 5: Report
Share the PR URL with the user.
