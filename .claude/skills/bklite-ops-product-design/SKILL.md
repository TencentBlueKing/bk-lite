---
name: bklite-ops-product-design
description: Use when proposing or reviewing BK-Lite operations-product modules, MVP scope, product specifications, competitor-derived designs, workflow/state models, extensibility decisions, permissions, audit, execution safety, or acceptance criteria.
---

# BK-Lite Ops Product Design

## Core Principle

Design a usable operational closed loop for real customer environments. Do not confuse an MVP with a demo, and do not import every mature-product feature into the MVP.

**REQUIRED SUB-SKILL:** Use `superpowers:brainstorming` before changing a design or writing a new specification.

## Workflow

1. Read the repository `AGENTS.md`, the target specification, related code/docs, and recent commits.
2. Read `docs/design/product-decisions/global-product-principles.md`.
3. If a matching module memory exists under `docs/design/product-decisions/`, read it before forming recommendations.
4. Separate evidence into:
   - repository fact;
   - confirmed product decision;
   - current assumption;
   - open question.
5. Review with [references/review-checklist.md](references/review-checklist.md).
6. Treat competitor material as capability coverage and terminology input, not as the target architecture.
7. Ask one consequential question at a time. Do not reopen confirmed decisions unless new evidence creates a conflict.
8. Present 2-3 viable approaches when a real choice remains, lead with the recommendation, and state the trade-off.
9. Classify findings:
   - **Blocker**: breaks the business loop, creates unsafe execution, or leaves authorization ambiguous.
   - **MVP improvement**: materially improves usability or operability without changing product positioning.
   - **Later**: mature governance, optimization, analytics, or convenience capability.
   - **Confirm**: cannot be resolved from repository facts or decision memory.
10. After approval, update the design spec and applicable decision memory using [references/decision-memory-guide.md](references/decision-memory-guide.md).

## Judgment Rules

- Respect the user's declared MVP boundary. A deliberately deferred feature is not an omission.
- Preserve minimum execution safeguards even when advanced governance is deferred.
- Prefer configuration for regular, data-like variation; prefer backend plugins for behaviorally different platforms or protocols.
- Avoid fixed support matrices when customer environments vary and a stable generic engine can use mappings.
- Distinguish unsupported capability, unmapped configuration, inapplicable objects, and execution failure.
- Define state transitions, cancellation semantics, degraded paths, authorization, audit events, and acceptance scenarios.
- Verify unstable vendor lifecycle, product, or protocol facts from primary sources before using them.
- Do not edit code or specs until the design section being changed is approved.

## Output Shape

Start with the product judgment, then list blockers and MVP improvements. Keep later items short. End with one question or a concrete approved edit, not a generic checklist dump.

## Red Flags

- Recommending a minimal demo after the user asked for a commercially testable MVP.
- Declaring every competitor feature mandatory.
- Hard-coding customer environment variants without testing whether configuration or plugins fit better.
- Exposing arbitrary scripts in a settings page to gain flexibility.
- Treating vendor lifecycle status as equivalent to technical install capability.
- Using vague states such as only success/failure for a multi-stage operational workflow.
- Repeating questions already answered in decision memory.
