## 1. Definition loading foundation

- [x] 1.1 Add a shared JSON definition loader for community + optional enterprise directories
- [x] 1.2 Support merge-by-id semantics and allow enterprise definitions to override community definitions
- [x] 1.3 Add node_mgmt enterprise support-files placeholders for controllers and collectors

## 2. Controller definition migration

- [x] 2.1 Move builtin controller initialization from Python constants to JSON definitions
- [x] 2.2 Ensure definition IDs are used only for merge semantics and not written into the integer `Controller.id` primary key
- [x] 2.3 Seed community controller definitions with Windows x86_64 and Linux x86_64 defaults

## 3. Collector architecture modeling

- [x] 3.1 Add `Collector.cpu_architecture`
- [x] 3.2 Change collector uniqueness to `(node_operating_system, cpu_architecture, name)`
- [x] 3.3 Keep generic collectors compatible with empty architecture values and existing IDs

## 4. Runtime architecture-aware collector resolution

- [x] 4.1 Add a shared exact-then-generic collector resolution helper
- [x] 4.2 Update collector package resolution/install paths to use architecture-aware collector lookup
- [x] 4.3 Update default config creation to prefer exact-arch collectors and still allow generic fallback
- [x] 4.4 Update NATS config creation paths to resolve collectors/configurations with architecture awareness
- [x] 4.5 Audit remaining collector list/filter/display paths and implement minimal architecture-aware backend API exposure for filter/list/retrieve behavior

## 5. Verification

- [x] 5.1 Extend targeted architecture support tests for definition loader and collector architecture records
- [x] 5.2 Add targeted verification for NATS config creation exact-match and generic-fallback behavior
- [x] 5.3 Run `uv run pytest apps/node_mgmt/tests/test_architecture_support.py -q`
- [x] 5.4 Run `uv run python -m compileall apps/node_mgmt/nats/node.py apps/node_mgmt/tests/test_architecture_support.py`
- [x] 5.5 Add targeted verification for collector API filter/list/retrieve architecture exposure
