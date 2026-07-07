# projectmem AI Instructions

These instructions are MANDATORY for all AI coding agents working in this project. Failure to follow them means your work is incomplete and the audit trail is corrupted.

This file is stable operating guidance. Do not rewrite it unless the user asks or projectmem itself changes.

## Start of every session

**Step 1 — Identify your mode by reading `.projectmem/summary.md` and `.projectmem/PROJECT_MAP.md`.**

- **Setup Mode** — `summary.md` and/or `PROJECT_MAP.md` still contain the **placeholder text** from `pjm init`. Concrete signals you are in Setup Mode:
  - `summary.md` contains the phrase *"Replace this placeholder with a concise description..."*
  - Section bodies say *"None logged yet."*
  - `PROJECT_MAP.md` contains *"Status: not created yet"* or *"This file should be created by the first AI assistant..."*

  → **You MUST populate both files with real project content before doing any other work for the user.** This is not optional and not deferred — your first response in a Setup Mode session is the memory-population pass. Procedure:

  1. Read `README.md`, `package.json` / `pyproject.toml` / `Cargo.toml`, entry-point files (typically `src/main.*`, `index.html`, `app/__init__.py`, etc.), and any obvious architectural files.
  2. For **each architectural choice** you identify (frameworks, language, build system, deployment target, data flow): call `add_decision` (MCP) or `pjm decision` (CLI) — one call per decision.
  3. For **each gotcha / setup detail / library quirk**: call `add_note` (MCP) or `pjm note` (CLI) — one call per gotcha.
  4. Each `add_decision` / `add_note` call appends to `events.jsonl` AND auto-regenerates `summary.md`. **NEVER edit `summary.md` directly** — it is derived; your edits will be overwritten on the next event.
  5. **DO edit `PROJECT_MAP.md` directly** to replace its placeholder. `PROJECT_MAP.md` is structural and is NOT derived from events. Write the project's purpose, main folders, entry points, important files, relationships, and suggested first reads. Make sure PROJECT_MAP.md has a `## Project purpose` section with a real description — that section is auto-copied into `summary.md`'s Project purpose on the next regeneration (the only path by which summary.md's Project purpose gets populated; there is intentionally no MCP tool for it).
  6. After step 5, summary.md and PROJECT_MAP.md both contain real content (summary.md picks up the Project purpose from PROJECT_MAP.md on the next `add_decision` / `add_note` call's auto-regen — or you can force it now with `pjm regenerate`). The project is in Maintenance Mode for every subsequent session.

- **Maintenance Mode** — `summary.md` AND `PROJECT_MAP.md` contain **real project content, NOT the `pjm init` placeholder text**. Concrete signals you are in Maintenance Mode:
  - `summary.md` describes the actual project, lists real issues / decisions / notes by content.
  - `PROJECT_MAP.md` has real folder descriptions, entry points, and file relationships — not *"Status: not created yet."*

  → **STOP analyzing the project structure.** The memory is already built. Use the existing summary + map. Focus exclusively on the user's actual task and on logging your own work via the trigger table.
  - Do NOT re-scan source files. Trust the memory.
  - Do NOT re-write `summary.md` or `PROJECT_MAP.md`. They are already correct; if you find an out-of-date detail, fix it through the trigger table (`add_note` / `add_decision` / `log_issue`) — never via direct file edit on summary.md.

**Step 2 — Read these three files (or call the MCP equivalents):**

| File | MCP tool | Purpose |
| --- | --- | --- |
| `.projectmem/AI_INSTRUCTIONS.md` | `get_instructions()` | Workflow rules (this file) |
| `.projectmem/summary.md` | `get_summary()` | Distilled project memory |
| `.projectmem/PROJECT_MAP.md` | `get_project_map()` | Structural layout |

Prefer the MCP tools when available — they're cheaper (~500 tokens) than reading files individually and they auto-resolve the project root regardless of your working directory.

**Step 3 — Check `.projectmem/issues/` only when a logged issue looks relevant to the current task** (use `get_issue(issue_id)` via MCP, or read the file). Don't read every issue on every session — that's wasteful.

**Step 4 — Treat `.projectmem/events.jsonl` as the append-only raw log.** Do not edit it by hand unless repairing corruption. Use write tools.

## MANDATORY Triggers — You MUST act on these automatically

When a trigger fires, you MUST call the corresponding tool IMMEDIATELY, before continuing any other work. **Prefer MCP tools** (left column) when you're connected via an MCP-capable client; **fall back to CLI** (right column) otherwise.

| Trigger | MCP tool | CLI command |
| --- | --- | --- |
| Bug, error, or unexpected behavior | `log_issue(summary, location)` | `pjm log "<text>" --at "<file:line>"` |
| Fix attempt FAILED | `record_attempt(summary, outcome="failed")` | `pjm attempt "<text>" --failed --at "<file:line>"` |
| Fix attempt PARTIAL (helped but didn't fully fix) | `record_attempt(summary, outcome="partial")` | `pjm attempt "<text>" --partial --at "<file:line>"` |
| Fix attempt WORKED | `record_attempt(summary, outcome="worked")` | `pjm attempt "<text>" --worked --at "<file:line>"` |
| Fix confirmed — close the issue | `record_fix(summary)` | `pjm fix "<text>" --at "<file:line>"` |
| Architectural / design decision | `add_decision(summary)` | `pjm decision "<text>" --at "<file:line>"` |
| Gotcha / setup detail / constraint discovered | `add_note(summary)` | `pjm note "<text>" --at "<file:line>"` |
| Before finishing the session | `get_summary()` | `pjm show` |

All write tools auto-append to `events.jsonl` AND auto-regenerate `summary.md`. You do NOT need to call a separate "save" or "regenerate" command after each tool. The summary follows the events automatically.

## Execution Rules

1. **Log BEFORE you fix.** When you see a bug, call `log_issue` (or `pjm log`) BEFORE writing fix code. The issue survives interruptions and session boundaries; in-flight fix work does not.
2. **Record IMMEDIATELY after each attempt.** Do not batch multiple attempts into one entry. Each distinct approach gets its own `record_attempt` call.
3. **Close with `record_fix` only after evidence.** Test passes, error is gone, or the user confirms — anything less and the issue stays open.
4. **Never skip logging because it feels minor.** A small fix today is a mystery regression tomorrow. Log it.
5. **NEVER edit `.projectmem/summary.md` or `.projectmem/events.jsonl` directly via filesystem write.** Both are derived/append-only. Use the write tools. (You MAY edit `PROJECT_MAP.md` directly when restructuring it; it's not derived from events.)

## What to track

Use projectmem to preserve the development story that would otherwise be lost between chats, terminal sessions, and commits.

Track:

- new issues, bugs, regressions, unclear behavior, or investigation topics
- hypotheses about causes
- attempted fixes or experiments (each as its own `record_attempt`)
- whether each attempt worked, failed, or partially helped
- final fixes and the files involved
- architectural, product, or implementation decisions and their reasons
- gotchas, setup requirements, flaky tests, environment notes, important constraints
- key files future contributors or AI agents should read first

Do NOT track secrets, credentials, private customer data, access tokens, or large transcripts.

## Auto-Capture (active)

Git hooks installed by `pjm init` automatically capture:

- Commits (post-commit hook)
- Reverts (auto-classified as failed approaches)
- Merges (auto-classified as milestones)
- File churn (the `pjm watch` daemon flags rapid same-file edits)

You do NOT need to manually log any of those. You SHOULD still manually log:

- Decisions with rationale (`add_decision` / `pjm decision`)
- Pre-attempt context for complex fixes (`record_attempt` / `pjm attempt`)
- External factors and gotchas (`add_note` / `pjm note`)
- Failure context that commit messages don't capture

## Pre-commit safety net

Every `git commit` automatically runs `pjm precheck` against the staged files. If you're about to commit a file with unresolved issues, recent failed attempts, or high churn, you'll see a warning block before the commit lands. Read it; it exists to stop you from repeating known failures. To bypass once: `git commit --no-verify`.

## Rules summary

- **MANDATORY: Log before you exit.** Work is not finished until project memory reflects what happened.
- **MANDATORY: Record failed and partial attempts.** Negative and partial-credit knowledge is often the most valuable part of project memory.
- Keep entries concise but specific enough that another person or AI can avoid repeating work. Include file paths, error names, test names.
- Prefer several small accurate entries over one vague long entry.
- Do not claim something is fixed until tests, reproduction, or user confirmation supports it.
- Do not overwrite history. `events.jsonl` is append-only; `summary.md` is derived from it.
- If MCP is unavailable, use the CLI (`pjm log`, `pjm attempt`, `pjm fix`, `pjm decision`, `pjm note`). If neither is available, clearly tell the user what should be recorded.
- **`pjm` is the canonical CLI command** (since v0.0.4). The legacy `projectmem` alias still works if installed.

## Minimal prompt for AI tools (Universal Mode)

Read `.projectmem/AI_INSTRUCTIONS.md`, `.projectmem/summary.md`, and `.projectmem/PROJECT_MAP.md` before working. This project uses mandatory memory tracking with auto-capture enabled. If summary.md contains placeholder text, populate it via `pjm decision` and `pjm note` (or the `add_decision` / `add_note` MCP tools) — never edit summary.md directly. Git hooks log commits, reverts, and merges automatically. You MUST still run `pjm log` when you find a bug, `pjm attempt` for fix attempts, `pjm fix` when confirmed, and `pjm decision` for architectural choices. Skipping these steps means your work is incomplete.
