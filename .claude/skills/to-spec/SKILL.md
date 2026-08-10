---
name: to-spec
description: Use only when the user explicitly asks to turn the current, already-aligned conversation into a durable change spec without another interview.
---

This skill takes the already-aligned conversation and current codebase understanding and produces one durable local change spec. Do NOT interview the user or create proposal/design/task sidecars — just synthesize what is already known.

The issue tracker conventions should have been provided to you — run `$setup-matt-pocock-skills` if not.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Record the seams already agreed for testing the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If the conversation did not name a seam, infer the highest existing seam from nearby code and record that decision in the spec rather than reopening the interview.

3. Write the spec using the template below to `specs/changes/<feature-slug>/spec.md`. Update an existing file in place when present. Set `Status: ready`; this repository has no external tracker or label branch.

<spec-template>

# <Feature title>

Status: ready

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A numbered list containing only the material user-visible behaviours. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

Cover the agreed behaviour and important edge cases without creating a requirements laundry list.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts — not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
