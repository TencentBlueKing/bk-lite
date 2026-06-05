## ADDED Requirements

### Requirement: Skill prompt params field
LLMSkill model SHALL have a `skill_params` JSONField (default: empty list) that stores a list of parameter objects. Each parameter object SHALL contain `key` (string), `value` (string), and `type` (enum: `text` | `password`).

#### Scenario: Create skill with prompt params
- **WHEN** user creates an LLMSkill with `skill_params: [{"key": "username", "value": "admin", "type": "text"}, {"key": "password", "value": "123", "type": "password"}]`
- **THEN** system stores the skill with `type=text` values in plaintext and `type=password` values encrypted via `EncryptMixin`

#### Scenario: Create skill without prompt params
- **WHEN** user creates an LLMSkill without providing `skill_params`
- **THEN** system stores `skill_params` as an empty list `[]`

### Requirement: Password params encrypted at rest
All `skill_params` entries with `type=password` SHALL have their `value` encrypted using `EncryptMixin.encrypt_field()` before persisting to database. Entries with `type=text` SHALL be stored as plaintext.

#### Scenario: Mixed type params storage
- **WHEN** user saves `skill_params: [{"key": "host", "value": "example.com", "type": "text"}, {"key": "token", "value": "secret123", "type": "password"}]`
- **THEN** `host` value is stored as `"example.com"` and `token` value is stored as a Fernet-encrypted string

### Requirement: Password params masked on read
API responses for LLMSkill SHALL return `"******"` as the `value` for all `skill_params` entries with `type=password`. Entries with `type=text` SHALL return their actual value.

#### Scenario: List skills with password params
- **WHEN** client sends GET request to list or retrieve an LLMSkill that has `skill_params` containing a `type=password` entry
- **THEN** response contains `"value": "******"` for that entry, not the encrypted or plaintext value

#### Scenario: List skills with text params
- **WHEN** client sends GET request to list or retrieve an LLMSkill that has `skill_params` containing a `type=text` entry
- **THEN** response contains the actual plaintext value for that entry

### Requirement: Password params preserved on update
When updating LLMSkill, if a `skill_params` entry has `type=password` and `value=="******"`, the system SHALL preserve the existing encrypted value from the database for that key. New password values (not `"******"`) SHALL be encrypted before storage.

#### Scenario: Update without changing password
- **WHEN** client sends PUT with `skill_params` containing `{"key": "password", "value": "******", "type": "password"}`
- **THEN** system keeps the previously stored encrypted value for key `"password"` unchanged

#### Scenario: Update with new password value
- **WHEN** client sends PUT with `skill_params` containing `{"key": "password", "value": "newpass", "type": "password"}`
- **THEN** system encrypts `"newpass"` and stores the new encrypted value

#### Scenario: Update text param normally
- **WHEN** client sends PUT with `skill_params` containing `{"key": "username", "value": "newuser", "type": "text"}`
- **THEN** system stores `"newuser"` as plaintext

### Requirement: Prompt param substitution on execution
When LLMSkill is executed, the system SHALL resolve all `{{key}}` placeholders in `skill_prompt` by replacing them with the actual (decrypted) values from `skill_params`. This substitution SHALL occur before the prompt enters any downstream template engine.

#### Scenario: Direct skill execution with params
- **WHEN** skill executes with `skill_prompt="登陆 xxx，输入帐号 {{username}}，密码 {{password}}"` and `skill_params=[{"key":"username","value":"admin","type":"text"},{"key":"password","value":"<encrypted>","type":"password"}]`
- **THEN** the prompt sent to LLM is `"登陆 xxx，输入帐号 admin，密码 123"` (password decrypted and substituted)

#### Scenario: Execution with no params defined
- **WHEN** skill executes with `skill_params=[]` and `skill_prompt` contains `{{something}}`
- **THEN** the prompt is sent as-is with `{{something}}` unresolved (no error raised)

#### Scenario: Execution with param defined but not referenced in prompt
- **WHEN** skill executes with `skill_params=[{"key":"unused","value":"val","type":"text"}]` and `skill_prompt` does not contain `{{unused}}`
- **THEN** the prompt is sent unchanged (no error raised)

### Requirement: Workflow AgentNode param substitution
When an LLMSkill is invoked through a workflow AgentNode, the system SHALL read the skill's `skill_params` and perform the same `{{key}}` → value substitution on `skill_prompt` before passing it to the chat service.

#### Scenario: AgentNode executes skill with params
- **WHEN** a workflow AgentNode selects an LLMSkill that has `skill_params` with password entries
- **THEN** the `skill_prompt` passed to the chat service has all `{{key}}` placeholders replaced with decrypted values

### Requirement: Intent classifier node unaffected
IntentClassifierNode SHALL NOT be affected by this change. It does not use LLMSkill and constructs its own prompt independently.

#### Scenario: Intent classifier node operates normally
- **WHEN** a workflow uses IntentClassifierNode with a directly configured LLM model and prompt
- **THEN** node behavior is unchanged; no param substitution logic is applied
