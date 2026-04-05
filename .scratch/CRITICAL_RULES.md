# CRITICAL RULES — READ EVERY SESSION

This is the universal entrypoint for any agent working in any codebase.
Read this file FIRST after every compaction or session start.

---

## 0. ABSOLUTE RULE — NO SUBAGENTS

**NEVER use subagents (the Task tool) under any circumstances.** Do all work directly — reading files, searching, writing, editing, running commands. No delegation. No exceptions. This is the highest-priority rule and overrides any other guidance suggesting subagent use. When creating new projects, this must be emphasized at the start and the end of the project PLAN.md file when you create or update it. 

---

## 1. Session Startup (Including After Compaction)

**After every compaction, immediately read this file and continue working.** Do not wait for user input. The compaction summary tells you what was happening; this file and the project files tell you how to resume.

1. Read this file in full.
2. Read `.scratch/REPO_RULES.md` for repo-specific coding standards and reference files. The file that you should append self-reminders to specific to this repository.
3. Identify which project you are working on.
4. Read that project's `CONTEXT.md` to resume where you left off.
5. Check `PROGRESS.md` for current task status.
6. Check `ISSUES.md` for known roadblocks before starting work.
7. **Resume working immediately** — pick up the next pending task and continue.

---

## 2. Project Convention

Every task, feature, or refactor gets its own project directory:

```
.scratch/projects/<num>-<project-name>/
```

Use kebab-case for directory names (e.g. `option-a-unification`, `web-demo-migration`).

### Standard Files

Each project directory contains these standard files. Create them if they don't yet exist:

| File | Purpose |
|------|---------|
| `PROGRESS.md` | Task tracker with status (pending/in-progress/done). The source of truth for what's been completed and what remains. |
| `CONTEXT.md` | Current state for resumption after compaction. What just happened, what's next, key variable state. Update this before any large context shift. |
| `PLAN.md` | Implementation plan. Ordered steps, dependencies, acceptance criteria. |
| `DECISIONS.md` | Key decisions with rationale. Load `ASSUMPTIONS.md` before making a decision. |
| `ASSUMPTIONS.md` | Context loaded before making decisions. Project audience, user scenarios, constraints, invariants — anything that shapes *why* a decision gets made. |
| `ISSUES.md` | Roadblock index. After 3 failed attempts at the same problem, stop and create an `ISSUE_<num>.md` in the project directory with a detailed log of what was tried, what failed, and why. Reference it from `ISSUES.md`. |

### Project-Scoped Scratch Notes

ALL scratch notes, working files, ad-hoc explorations, and temporary analysis for a project go inside that project's directory — never loose in `.scratch/`. Name them descriptively (e.g. `watcher-refactor-notes.md`, `db-schema-analysis.md`). The standard files above are the convention; additional files are encouraged whenever they help preserve context.

### Project Lifecycle

- **Starting**: Create the directory and at minimum `PLAN.md` and `ASSUMPTIONS.md`.
- **Working**: Keep `PROGRESS.md` and `CONTEXT.md` current as you go.
- **Blocked**: Document in `ISSUES.md` with a linked `ISSUE_<num>.md`.
- **Complete**: Mark all tasks done in `PROGRESS.md`. Update `CONTEXT.md` with a final summary.

---

## 3. Context Preservation

- Write to `.scratch/projects/<project>/` frequently to preserve context across compaction.
- Update `CONTEXT.md` whenever you finish a significant chunk of work or are about to shift focus.
- `CONTEXT.md` should always answer: *"If I lost all memory right now, what do I need to know to continue?"*
- When reasoning through a non-obvious decision, write it to `DECISIONS.md` with the rationale and which assumptions informed it.

---

## 4. Coding Standards

- **TDD**: Write a failing test first, implement, verify the test passes.
- **DRY/YAGNI**: No duplication. No speculative features.

`REPO_RULES.md` may add repo-specific standards on top of these.

---

## 5. Large Documents

When writing large documents:

1. Write a detailed table of contents (with brief description per section) and SAVE IT TO FILE first.
2. Go section by section, APPENDING to the file as you go.
3. This prevents context window overflow from trying to write the whole thing at once.

---

## 6. ALWAYS CONTINUE — NEVER STOP

**After every compaction, resume working IMMEDIATELY.** Do NOT wait for user input. Do NOT ask "what should I do next?" — the answer is always in CONTEXT.md and PROGRESS.md. Pick up the next pending task and keep going until the active project is **completely and totally done** — fully integrated, fully tested, ready to use. Stopping early or waiting for permission is not acceptable.

---

## REMINDER — NO SUBAGENTS

**NEVER use the Task tool.** Do all work directly. This rule is absolute and non-negotiable.

## REMINDER — ALWAYS CONTINUE

**NEVER stop working after compaction.** Read CONTEXT.md, check PROGRESS.md, resume immediately. Keep going until the project is fully done.
