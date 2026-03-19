# Agentic Workflow Guide

This guide explains how to use Claude Code's custom agents for structured, high-quality implementation workflows.

## Available Agents

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| `researcher` | Information gathering | Before planning, to understand codebase |
| `explorer-alternatives` | Generate solution options | When multiple approaches are viable |
| `challenger` | Red-team and critique | Before committing to an approach |
| `implementer` | Focused task execution | During implementation phase |
| `verifier` | Run verification gates | After implementation |
| `reviewer` | Semantic code review | Before marking task complete |

## The GSD+RALF Workflow

### Phase 1: GSD (Get Stuff Done) - Planning

```
User Request → Research → Alternatives → Challenge → Plan → Approval
```

#### Step 1: Research
Spawn the `researcher` agent to understand the current state:
```
Task(researcher): "Research how rate limiting currently works in this codebase. Find the key files, patterns, and any existing bypass logic."
```

#### Step 2: Explore Alternatives
Spawn the `explorer-alternatives` agent:
```
Task(explorer-alternatives): "Given the rate limiting research, propose 2-3 approaches for adding admin bypass. Include trade-offs."
```

#### Step 3: Challenge the Plan
Spawn the `challenger` agent:
```
Task(challenger): "Review the proposed admin bypass approach. Find failure modes, security risks, and missing constraints."
```

#### Step 4: Create the Plan
Use `TodoWrite` to create the task list based on the chosen approach.

#### Step 5: Get User Approval
Use `ExitPlanMode` or `AskUserQuestion` to confirm before implementing.

---

### Phase 2: RALF (Review-Audit-Loop-Fix) - Execution

```
For each task: Implement → Verify → Review → Complete
```

#### Step 1: Implement
Spawn the `implementer` agent:
```
Task(implementer): "Implement task #1: Add admin check to rate_limiter.py. AC: JWT with role=admin bypasses rate limit."
```

The implementer will:
- Make minimal, focused changes
- Report files changed and commands run
- Flag ARCHITECTURE_MISMATCH if the plan is impossible

#### Step 2: Verify
Spawn the `verifier` agent:
```
Task(verifier): "Run verification gates for the rate limiter changes. Focus on Python tests first."
```

The verifier will:
- Run the smallest relevant gate
- Report exact errors if any
- Suggest minimal fixes

#### Step 3: Review
Spawn the `reviewer` agent:
```
Task(reviewer): "Review the rate limiter changes against AC-1: admin bypass. Check for security issues."
```

The reviewer will:
- Validate against acceptance criteria
- Check for logic and security issues
- Output REVIEW_PASS or REVIEW_FAIL with blockers

#### Step 4: Complete or Loop
- If verify + review pass → mark task complete
- If either fails → fix issues and repeat

---

## Spawning Agents with Task Tool

### Single Agent
```
Task(
  subagent_type: "implementer",
  prompt: "Implement the rate limit bypass for admin users. AC: Requests with JWT role=admin skip rate limit check."
)
```

### Parallel Agents (Independent Tasks)
```
// Spawn multiple agents in one message
Task(researcher): "Research authentication patterns"
Task(researcher): "Research rate limiting patterns"
```

### Sequential Agents (Dependent Tasks)
```
// First gather info
Task(researcher): "Research the current auth flow"

// Wait for result, then implement
Task(implementer): "Based on auth research, add the admin bypass"
```

---

## Example: Complete Workflow Session

### User Request
"Add a feature to export chat history as PDF"

### Phase 1: GSD

**1. Research**
```
Task(researcher): "Research how chat history is currently stored and retrieved. Find the conversations_handler and message storage patterns."
```
Result: Conversations stored in DynamoDB, retrieved via REST API...

**2. Alternatives**
```
Task(explorer-alternatives): "Propose approaches for PDF export. Consider: client-side vs server-side generation, Lambda vs separate service, library options."
```
Result:
- Option 1: Client-side with jsPDF (conservative)
- Option 2: Lambda with ReportLab (balanced)
- Option 3: Step Functions pipeline (ambitious)

**3. Challenge**
```
Task(challenger): "Challenge the Lambda + ReportLab approach. Consider Lambda size limits, cold starts, memory for large chats."
```
Result: Blockers around large conversations, suggests streaming approach...

**4. Plan** (via TodoWrite)
1. Add ReportLab to Lambda layer
2. Create pdf_export_handler.py
3. Add /export endpoint to API Gateway
4. Add export button to frontend

**5. Approval**
"Proceed with implementation?"

### Phase 2: RALF

**For Task 1:**
```
Task(implementer): "Add ReportLab to Lambda layer in layer/requirements.txt"
Task(verifier): "Verify Lambda layer build succeeds"
```

**For Task 2:**
```
Task(implementer): "Create pdf_export_handler.py that exports conversation to PDF"
Task(verifier): "Run tests for pdf_export_handler"
Task(reviewer): "Review pdf_export_handler against AC: generates valid PDF with all messages"
```

*...continue for remaining tasks...*

---

## Workflow Triggers

You can invoke the workflow with natural language:

| User Says | Workflow |
|-----------|----------|
| "Plan this" or "GSD" | Full GSD workflow |
| "Implement this" or "RALF" | RALF execution loop |
| "Research..." | Spawn researcher agent |
| "What are my options for..." | Spawn explorer-alternatives |
| "Challenge this approach" | Spawn challenger agent |
| "Review the changes" | Spawn reviewer agent |
| "Run the gates" | Spawn verifier agent |

---

## Best Practices

### Do
- Research before planning
- Challenge before committing
- Verify after every implementation
- Review against acceptance criteria
- Use parallel agents when tasks are independent

### Don't
- Skip the challenge phase for complex features
- Implement without clear acceptance criteria
- Mark tasks complete without verification
- Ignore ARCHITECTURE_MISMATCH signals
- Run all agents sequentially when parallelism is possible

---

## Quick Reference

### Starting a New Feature
```
1. Task(researcher): understand current state
2. Task(explorer-alternatives): propose approaches
3. Task(challenger): stress-test chosen approach
4. TodoWrite: create task list
5. For each task:
   - Task(implementer)
   - Task(verifier)
   - Task(reviewer)
```

### Fixing a Bug
```
1. Task(researcher): understand the bug context
2. Task(implementer): fix the bug
3. Task(verifier): run tests
4. Task(reviewer): verify fix is complete
```

### Refactoring
```
1. Task(researcher): understand current patterns
2. Task(challenger): identify risks of refactor
3. TodoWrite: break into safe steps
4. For each step: implement → verify → review
```
