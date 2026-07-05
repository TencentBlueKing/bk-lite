<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

<!-- >>> projectmem bridge >>> -->
## projectmem (MANDATORY)

This project uses projectmem for persistent project memory and workflow rules.

At session start, call `get_instructions()`, `get_summary()`, and `get_project_map()` before answering project questions. Before modifying a file, call `precheck_file(path)`. During work, log bugs, attempts, fixes, decisions, and notes through the projectmem MCP tools or `pjm`; do not edit `.projectmem/summary.md` or `.projectmem/events.jsonl` by hand.
<!-- <<< projectmem bridge <<< -->
