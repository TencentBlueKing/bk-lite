## 1. Server-side archive admission guards

- [x] 1.1 Add a shared Playbook archive policy helper in `server/apps/job_mgmt` for raw size, member count, single-member size, and total expanded size checks
- [x] 1.2 Apply the archive policy to `PlaybookCreateSerializer.validate_file()` and `PlaybookUpgradeSerializer.validate_file()`
- [x] 1.3 Refactor archive parsing helpers so upload and upgrade flows avoid eager whole-archive reads before guard checks
- [x] 1.4 Add preview guard checks so `preview_file` rejects oversized archives before whole-package processing

## 2. Transfer and executor protections

- [x] 2.1 Refactor `server/apps/job_mgmt/services/playbook_execution.py` to avoid whole-archive in-memory relay and fail oversized stored archives early
- [x] 2.2 Extend `agents/ansible-executor/service/ansible_runner.py::_safe_extract_zip()` with ZIP member-count, per-member-size, and total-expanded-size limits
- [x] 2.3 Ensure executor download and extraction paths use the same bounded archive policy for Playbook ZIP handling

## 3. Regression coverage and verification

- [x] 3.1 Add `job_mgmt` tests for archive upload / upgrade rejection and preview rejection under archive resource limits
- [x] 3.2 Add `ansible-executor` tests for ZIP member-count and expanded-size guard failures
- [x] 3.3 Run the targeted `job_mgmt` and `ansible-executor` test suites covering the new archive guard behavior
