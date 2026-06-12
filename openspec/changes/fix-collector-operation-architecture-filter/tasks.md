## 1. Tests

- [x] 1.1 Add a frontend regression test proving collector operation queries include `cpu_architecture`.
- [x] 1.2 Add a frontend regression test proving unknown architecture blocks collector operation modal opening.

## 2. Implementation

- [x] 2.1 Update the node page collector operation handler to validate selected node architecture before opening the modal.
- [x] 2.2 Ensure collector option loading continues to pass `cpu_architecture` and treats `tags` only as a category filter.

## 3. Verification

- [x] 3.1 Run the targeted frontend test.
- [x] 3.2 Run the relevant web lint/type-check command if dependency state allows it.
