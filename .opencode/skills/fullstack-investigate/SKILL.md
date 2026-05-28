# fullstack-investigate

## Goal
Investigate a fullstack issue and identify the smallest likely end-to-end fix.

## Must do
- Consider frontend, backend, and API interaction together
- Identify likely affected areas
- Explain the likely root cause
- Suggest the smallest safe cross-layer fix
- State confidence clearly
- Produce an issue comment draft
- Explicitly state whether the issue is valid / reproducible from repository evidence
- Include concrete exploration evidence (files, functions, call paths) before concluding
- Default workflow should stop at human confirmation, not implementation
- Return a machine-readable JSON result with: `status`, `is_valid`, `exploration_evidence`, `workflow_stage`, `confirmation_required`, `confirmation_status`, `implementation_ready`, `problem_summary`, `summary`, `affected_areas`, `root_cause`, `optimization_proposal`, `implementation_plan`, `implementation_summary`, `solution`, `confidence`, `risk_assessment`, `unknowns`, `needs_human`, `comment_body`

## Must not do
- Do not edit files
- Do not create a PR
- Do not force a module-local explanation if the issue is cross-layer
