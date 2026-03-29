# Claude Agent Setup

State-of-the-art configuration for the Claude Code multi-agent system.

---

## Architecture

```
Human: "Build feature X"
  └── Manager (main session — CLAUDE.md)
        │
        ├── Plan Mode → design approach, get approval
        │
        ├── Coder Agent (.claude/agents/coder.md)
        │     ├── isolation: worktree (own git branch)
        │     ├── skills: preloaded (e.g., fastapi-python)
        │     ├── maxTurns: bounded execution
        │     └── memory: none (fresh per task)
        │
        ├── Reviewer Agent (.claude/agents/reviewer.md)
        │     ├── tools: read-only + test execution
        │     ├── memory: project (learns patterns)
        │     └── verdict: APPROVE or REQUEST_CHANGES
        │
        └── If rejected → feedback → coder → re-review
```

The manager does NOT write code. It orchestrates coder and reviewer agents for every task.

## Agent Definitions

### Coder — `.claude/agents/coder.md`

```yaml
---
name: coder
description: Senior developer that implements coding tasks with tests. Spawned by the manager with task specs and skill assignments.
tools:
  - Read
  - Edit
  - Write
  - Bash
  - Glob
  - Grep
model: opus
isolation: worktree     # Each task gets its own git branch
# memory: (none)        # Fresh context per task — no cross-contamination
# maxTurns: 50          # Optional: bound execution to prevent runaway
---
```

**Workflow:**
1. Load assigned skill FIRST
2. Read existing code before writing new code
3. Implement the task spec
4. Write tests (happy path + error cases)
5. Run `python -m pytest` — all must pass
6. Report completion

### Reviewer — `.claude/agents/reviewer.md`

```yaml
---
name: reviewer
description: Staff-level code reviewer. Spawned by the manager after coder finishes.
tools:
  - Read
  - Grep
  - Glob
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git show:*)
  - Bash(python -m pytest:*)
  - Bash(python -m py_compile:*)
model: opus
memory: project          # Learns codebase patterns over time
# effort: high           # Optional: deeper analysis
---
```

**Workflow:**
1. Check acceptance criteria FIRST (unmet = automatic reject)
2. Run `git diff` to see changes
3. Read modified files in full context
4. Run `python -m pytest` — verify all pass
5. Check: security, correctness, test coverage, code quality
6. Produce structured verdict: APPROVE or REQUEST_CHANGES

**Memory:** Reviewer accumulates knowledge in `.claude/agent-memory/reviewer/`. It gets smarter with each review — remembering project conventions, recurring issues, and patterns.

## Skills

Match tasks to skills before spawning the coder:

| Task Type | Skill | Location |
|-----------|-------|----------|
| FastAPI / async Python / Pydantic | `fastapi-python` | `~/.claude/skills/fastapi-python/SKILL.md` |
| MCP server integration | `mcp-builder` | `~/.claude/skills/mcp-builder/SKILL.md` |
| UI / dashboard | `web-design-guidelines` | `~/.claude/skills/web-design-guidelines/SKILL.md` |
| React components | `vercel-react-best-practices` | `~/.claude/skills/vercel-react-best-practices/SKILL.md` |

**In the coder prompt:** `"Read and follow the skill at: ~/.claude/skills/<name>/SKILL.md"`

Skills can also be preloaded via frontmatter:
```yaml
skills:
  - fastapi-python
```

## Hooks — `.claude/settings.json`

### Active Hook: Quality Gate

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "coder",
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"decision\":\"block\",\"reason\":\"Code review pending. Use the reviewer agent to review the changes before proceeding.\"}}'"
          }
        ]
      }
    ]
  }
}
```

When the coder finishes, this hook blocks and reminds the manager to run the reviewer. Code review is enforced, not optional.

### Hook Events Available

| Event | Use Case |
|-------|----------|
| `PreToolUse` | Block dangerous operations (e.g., validate bash commands) |
| `PostToolUse` | Auto-lint after file edits (`matcher: "Edit\|Write"`) |
| `SubagentStop` | Quality gates after agent completion |
| `TaskCompleted` | Block task completion if review fails (agent teams) |
| `Stop` | Validate output before session ends |
| `SessionStart` | Inject environment variables, run setup scripts |
| `FileChanged` | Trigger actions on specific file modifications |

### Hook Exit Codes

| Code | Behavior |
|------|----------|
| 0 | Success — parse stdout as JSON |
| 2 | **Block** — stderr fed back as feedback to Claude |
| Other | Non-blocking error — logged in verbose mode |

## Rules

### CRITICAL: Always Use the Reviewer

We skipped the reviewer for 10 tasks once. Retroactive review found **9 critical bugs**: SQL injection, datetime crashes, HMAC weakness, broken TWAP, unauthenticated endpoints.

**Rule: Spawn the reviewer after EVERY coder task. No exceptions. No "skipping for velocity."**

### Never Add Co-Author to Commits

Never add `Co-Authored-By: Claude` or any similar line to git commit messages.

### Read Lessons Before Working

Check `tasks/lessons.md` at the start of each session for project-specific mistakes to avoid. After ANY correction from the user, update that file.

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
- **Manually compact at ~50% context usage** to prevent degradation

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

## Memory Architecture

```
.claude/
├── agent-memory/              # Committed — shareable via git
│   └── reviewer/              # Reviewer's learned patterns
│       └── MEMORY.md          # Auto-updated by reviewer (memory: project)
└── agent-memory-local/        # Gitignored — machine-local only

~/.claude/projects/<project>/
└── memory/                    # Auto memory (per-project, per-machine)
    ├── MEMORY.md              # Index (first 200 lines loaded per session)
    └── *.md                   # Topic-specific memory files
```

- **Reviewer memory** (`memory: project`): Persists across sessions, learns conventions
- **Coder memory**: None — each task is independent
- **Auto memory**: Claude's own memory system for user preferences and feedback

## Advanced Patterns

### Path-Scoped Rules (`.claude/rules/`)

Rules that only activate for specific file paths:

```yaml
# .claude/rules/security.md
---
paths:
  - "app/execution/**"
  - "app/alerts/security.py"
---
# Security-Critical Code Rules
- ALL queries MUST use parameterized SQL (never f-strings)
- ALL Telegram callbacks MUST verify HMAC signatures
- NEVER log access tokens, API keys, or secrets
```

### Dynamic Context in Skills

Shell commands execute before Claude sees the content:

```markdown
## Current state
- Branch: !`git branch --show-current`
- Uncommitted changes: !`git diff --stat`
- Test status: !`python -m pytest --tb=no -q 2>&1 | tail -1`
```

### Parallel Coder Agents

When tasks touch different files, spawn multiple coders simultaneously:

```
Manager spawns (parallel):
  ├── Coder A: "Implement VIX fetcher (app/signals/vix.py)"     ← worktree A
  ├── Coder B: "Implement PE fetcher (app/signals/pe_ratio.py)"  ← worktree B
  └── Coder C: "Implement RSI calculator (app/signals/rsi.py)"   ← worktree C

Then review each sequentially.
```

### Stop Hook for Test Enforcement

Prevent session from ending if tests fail:

```json
{
  "Stop": [{
    "hooks": [{
      "type": "command",
      "command": "python -m pytest tests/unit/ -q --tb=no 2>&1 | tail -1 | grep -q 'passed' || (echo 'Tests failing — fix before stopping' >&2 && exit 2)"
    }]
  }]
}
```

## Session Startup Checklist

1. Read `CLAUDE.md` for orchestration rules
2. Read `tasks/lessons.md` for past mistakes to avoid
3. `git status` + `git log --oneline -5` for current state
4. `python -m pytest tests/unit/ -q` to verify baseline
5. Ask the user what they want to work on
6. Follow manager → coder → reviewer flow for all code changes
