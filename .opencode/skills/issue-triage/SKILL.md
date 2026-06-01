# issue-triage

## Goal
Classify a GitHub issue for fullstack handling in this monorepo.

## Must do
- Summarize the issue in at most 3 bullets
- Classify type: bug / feature / docs / question / ops
- Estimate risk: low / medium / high
- Estimate size: S / M / L
- Estimate clarity: high / medium / low
- Decide whether to triage or investigate
- Treat the issue as potentially cross-layer by default
- Return a machine-readable JSON result with: `status`, `summary`, `affected_areas`, `confidence`, `needs_human`, `comment_body`

## Must not do
- Do not assume the issue belongs to only one module
- Do not edit code
- Do not create a branch or PR

## Repo hints
- `server/` is Django backend
- `web/` is Next.js + React main frontend
- `mobile/` is Next.js + Tauri
- `webchat/` is component library and demo
- `agents/stargazer/` is a Sanic-based agent
- `algorithms/` contains multiple Python algorithm services
