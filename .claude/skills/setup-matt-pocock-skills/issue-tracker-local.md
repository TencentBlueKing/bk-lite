# Issue tracker: Durable Repository Markdown

Engineering specs and tickets for this repo live as committed Markdown files in `specs/changes/`.

## Conventions

- One feature per directory: `specs/changes/<feature-slug>/`
- The spec is `specs/changes/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `specs/changes/<feature-slug>/tickets/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- State is recorded as a `Status:` line near the top of each file
- New decisions update the corresponding spec or ticket directly; do not create a parallel conversation log

## When a skill says "publish to the issue tracker"

Create or update `specs/changes/<feature-slug>/spec.md`.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path directly.

Completed work stays in place as an ordinary decision record with `Status: done`; there is no move or archive operation.
