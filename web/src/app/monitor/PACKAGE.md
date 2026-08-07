# Monitor package.json note

This directory is **not** a standalone Next.js app. The real app root is `web/`.

Historically a nested `package.json` here declared its own `next` scripts and a subset of deps (`react-ace`, `ace-builds`, …). That caused tooling to treat monitor as a second Next package, while:

- `ace` / `react-ace` are already declared in [`web/package.json`](../../package.json) and unused under this module
- `dev` / `build` must run from `web/` (`pnpm --dir web …`)

The nested package file was removed intentionally. Do not reintroduce a nested Next app here.
