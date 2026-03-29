# Personal Expense Tracker — Claude Instructions

## Orchestration Rules

This project uses a **manager → coder → reviewer** flow for ALL code changes.

### Manager Role (Main Session)
- The manager does NOT write code directly
- Plan first, then spawn agents
- Always spawn the reviewer after every coder task — NO EXCEPTIONS

### Workflow
1. **Plan** — Enter plan mode for non-trivial tasks (3+ steps)
2. **Spawn Coder** — Use `.claude/agents/coder.md` with `isolation: worktree`
3. **Review** — Use `.claude/agents/reviewer.md` after coder finishes
4. **Iterate** — If reviewer rejects, feed back to coder and re-review
5. **Merge** — Only after APPROVE verdict

### Skill Assignment
Match tasks to skills before spawning the coder:

| Task Type | Skill |
|-----------|-------|
| FastAPI / async Python / Pydantic | `fastapi-python` |
| MCP server integration | `mcp-builder` |
| UI / dashboard | `web-design-guidelines` |
| React components | `vercel-react-best-practices` |

### Session Startup
1. Read this file
2. Read `tasks/lessons.md` for past mistakes
3. `git status` + `git log --oneline -5` for current state
4. `python -m pytest tests/unit/ -q` to verify baseline
5. Ask the user what to work on

## Rules

- **Never add `Co-Authored-By: Claude`** to commit messages
- **Always use the reviewer** — we found 9 critical bugs when we skipped it once

## Operating Principles

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user, update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

- **Plan First:** Write plan to `tasks/todo.md` with checkable items
- **Verify Plans:** Check in before starting implementation
- **Track Progress:** Mark items complete as you go
- **Explicit Changes:** High-level summary at each step
- **Document Results:** Add review comments to `tasks/todo.md`
- **Capture Lessons:** Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First:** Make every change as simple as possible. Impact minimal code.
- **No Laziness:** Find root cause. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Changes should only touch what's necessary. Avoid introducing bugs.
