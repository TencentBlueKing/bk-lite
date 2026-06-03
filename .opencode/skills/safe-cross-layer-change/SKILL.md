# safe-cross-layer-change

## Goal
Handle a cross-layer issue cautiously when the fix may touch multiple areas.

## Must do
- Minimize cross-layer blast radius
- Verify interface compatibility across changed layers
- Prefer the smallest backward-compatible fix
- Run all validators for changed paths
- Escalate if auth, security, deploy, or migration is involved

## Must not do
- Do not widen scope beyond the issue
- Do not make speculative architecture changes
- Do not skip validation
