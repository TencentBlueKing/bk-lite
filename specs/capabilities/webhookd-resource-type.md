## ADDED Requirements

### Requirement: webhookd accepts type=resource
`kubernetes.sh` SHALL accept `type=resource` in addition to existing `metric` and `log` values.

#### Scenario: Valid resource type
- **WHEN** a request is sent with `"type": "resource"`
- **THEN** kubernetes.sh validates successfully and proceeds to render

#### Scenario: Invalid type rejected
- **WHEN** a request is sent with `"type": "invalid"`
- **THEN** kubernetes.sh returns an error: "Invalid type: must be 'metric', 'log' or 'resource'"

### Requirement: webhookd renders resource-collector template
When `type=resource`, kubernetes.sh SHALL load `bk-lite-resource-collector.yaml` as the template, render it with the Secret, and return the combined YAML.

#### Scenario: Resource template rendered with Secret
- **WHEN** a request is sent with `"type": "resource"` and valid NATS credentials
- **THEN** the response `yaml` field contains the resource collector template concatenated with the rendered Secret

### Requirement: API documentation updated
`infra/API.md` SHALL document `resource` as a valid value for the `type` parameter.

#### Scenario: API docs reflect new type
- **WHEN** a developer reads `infra/API.md`
- **THEN** the type parameter description lists `metric`, `log`, and `resource` as valid values
