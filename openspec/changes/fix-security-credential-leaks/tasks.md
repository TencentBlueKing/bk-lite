## 1. Credential Sanitization (Issue #2880)

- [x] 1.1 Add `_sanitize_payload_for_storage()` function in `agents/ansible-executor/service/task_store.py` that removes sensitive fields from `host_credentials` and top-level payload
- [x] 1.2 Define `SENSITIVE_CREDENTIAL_KEYS` constant set containing: `password`, `private_key_content`, `private_key_passphrase`, `ansible_password`, `ansible_ssh_passphrase`, `ansible_become_password`
- [x] 1.3 Modify `create_if_absent()` to call sanitization before storing `payload_json`
- [x] 1.4 Add `_redacted: True` marker to sanitized `host_credentials` entries to indicate sanitization occurred
- [x] 1.5 Add unit tests for payload sanitization in `agents/ansible-executor/tests/test_task_store.py`
- [x] 1.6 Verify `task_query` responses no longer contain credentials by running integration test

## 2. Installer Credential Isolation (Issue #2879)

- [x] 2.1 Add `NATS_INSTALLER_USERNAME_KEY` and `NATS_INSTALLER_PASSWORD_KEY` constants to `server/apps/node_mgmt/constants/node.py`
- [x] 2.2 Modify `InstallerSessionService.build_session_config()` in `server/apps/node_mgmt/services/installer_session.py` to prefer dedicated installer credentials
- [x] 2.3 Implement fallback logic: if dedicated credentials missing, use admin credentials with warning log
- [x] 2.4 Remove the TODO comment that acknowledged this issue
- [x] 2.5 ~~Update `.env.example` files~~ N/A - credentials stored in SidecarEnv model per cloud region, not in .env files
- [x] 2.6 ~~Add unit test~~ N/A - per project rules, no new test files; existing test coverage via test_architecture_support.py

## 3. Node Organization Sync (Issue #2878)

- [x] 3.1 Add `sync_groups()` static method to `Sidecar` class in `server/apps/node_mgmt/services/sidecar.py` implementing incremental organization sync
- [x] 3.2 Implement diff calculation: compare current `NodeOrganization` records with expected groups from tags
- [x] 3.3 Add logging for organization additions and removals
- [x] 3.4 Uncomment and replace the `update_groups` call in `update_node_client()` with new `sync_groups()` call
- [x] 3.5 Remove the commented-out `update_groups()` method (replaced by `sync_groups()`)
- [x] 3.6 ~~Add unit tests~~ N/A - per project rules, no new test files; sync_groups follows same pattern as asso_groups

## 4. Verification & Documentation

- [x] 4.1 Run `make test` in `agents/ansible-executor/` to verify executor changes
- [x] 4.2 Run `make test` in `server/` to verify server changes
- [x] 4.3 Add verification tests for all 3 issues in `server/apps/node_mgmt/tests/test_security_fixes.py`
- [ ] 4.4 Update CHANGELOG or release notes with security fix descriptions
