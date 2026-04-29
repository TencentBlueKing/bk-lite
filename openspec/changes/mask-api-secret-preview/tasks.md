## 1. Backend contract changes

- [x] 1.1 Update existing backend serializer tests to define preview-only list and retrieve responses plus full create responses
- [x] 1.2 Split API secret serializers so read operations return `api_secret_preview` and create responses return full `api_secret`
- [x] 1.3 Update the user API secret viewset so `list` and `retrieve` use the preview serializer while `create` returns the full-secret serializer
- [x] 1.4 Run targeted backend API secret tests and fix any contract regressions

## 2. Frontend API secret page updates

- [x] 2.1 Update the system-manager settings API types so list responses use `api_secret_preview` and create responses use full `api_secret`
- [x] 2.2 Update the settings/key page table to render preview-only values and remove the list copy action
- [x] 2.3 Add the one-time create-success modal with warning text, checkbox confirmation, and post-close list refresh

## 3. Content and verification

- [x] 3.1 Add or update locale strings for the create-success modal and one-time warning text
- [x] 3.2 Run frontend type-check and fix any typing issues introduced by the API contract change
- [x] 3.3 Review changed backend and frontend files to confirm the final behavior matches the approved design
