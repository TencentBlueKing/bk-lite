---
name: setup-matt-pocock-skills
description: Use only when the user explicitly asks to install, repair, or reconfigure this repository's Grill engineering workflow, tracker conventions, and domain docs.
---

# Setup Matt Pocock's Skills

Repair or re-establish the fixed per-repo configuration that the engineering skills assume:

- **Issue tracker** — durable local Markdown under `specs/changes/`
- **Domain docs** — where `CONTEXT.md` and ADRs live, and the consumer rules for reading them
- **Agent entrypoint** — the existing root `AGENTS.md`

This vendored variant is deliberately repository-specific. Do not offer GitHub, GitLab, Jira, triage-label, multi-context, or alternate-agent-entry branches. If the user wants a different workflow, stop and treat that as a new architecture decision rather than silently expanding this skill.

## Process

### 1. Explore

Read the current repository state before proposing repairs:

- `AGENTS.md`, especially `## Agent skills`
- `CONTEXT.md`
- `docs/adr/`
- `docs/agents/{workflow,issue-tracker,domain,skills}.md`
- `specs/changes/`

### 2. Present findings

Summarise only concrete drift or missing files. The fixed target is:

- one `AGENTS.md` entrypoint;
- one root `CONTEXT.md` glossary;
- sparse ADRs under `docs/adr/`;
- durable change specs and tickets under `specs/changes/<feature>/`;
- no external tracker or label vocabulary.

### 3. Confirm and edit

Show the user a concise draft of any material repairs to:

- the `## Agent skills` block in `AGENTS.md`;
- `docs/agents/workflow.md`;
- `docs/agents/issue-tracker.md`;
- `docs/agents/domain.md`;
- `docs/agents/skills.md`.

Preserve correct existing content and make only the required repairs.

### 4. Write

Update the existing `## Agent skills` block in `AGENTS.md` in place. Do not create another agent entrypoint or append a duplicate block.

The block:

```markdown
## Agent skills

### Workflow

Clear small changes use the direct path. Ambiguous or hard-to-reverse work starts only through explicit `$grill-with-docs`; delivery uses `$implement`, and cross-session work may use `$to-spec` then `$to-tickets`. See `docs/agents/workflow.md`.

### Issue tracker

Engineering change specs and tickets are durable Markdown under `specs/changes/<feature>/`. See `docs/agents/issue-tracker.md`.

### Domain docs

This repository uses one root `CONTEXT.md` and sparse ADRs under `docs/adr/`. See `docs/agents/domain.md`.

### Installed skill set

The repository vendors the fixed 13-skill Grill closure plus the BK-Lite-specific `bklite-ops-product-design` and `tech-debt-audit` skills. See `docs/agents/skills.md`.
```

Preserve all four subsections. Repair `docs/agents/workflow.md` from the fixed routing above and repair `docs/agents/skills.md` from the actual vendored directories and pinned upstream metadata; never drop either section because another file is missing.

Then write the docs files using the seed templates in this skill folder as a starting point:

- [issue-tracker-local.md](./issue-tracker-local.md) — local-markdown issue tracker
- [domain.md](./domain.md) — domain doc consumer rules + layout

### 5. Done

Run skill validation and the repository residual checks. Tell the user exactly what was repaired and which engineering skills read these files. Re-running this skill is only necessary when this fixed infrastructure drifts.
