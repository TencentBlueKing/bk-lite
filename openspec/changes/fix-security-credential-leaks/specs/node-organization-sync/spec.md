## ADDED Requirements

### Requirement: Existing nodes MUST sync organization memberships on update

The sidecar service SHALL synchronize node organization memberships when processing node update callbacks. Organization changes in node tags MUST be reflected in the `NodeOrganization` table.

#### Scenario: Node gains new organization membership
- **WHEN** a node update callback includes a new organization in `GROUP_TAG` that the node is not currently a member of
- **THEN** a new `NodeOrganization` record SHALL be created for that node-organization pair
- **AND** the change SHALL be logged

#### Scenario: Node loses organization membership
- **WHEN** a node update callback excludes an organization from `GROUP_TAG` that the node is currently a member of
- **THEN** the corresponding `NodeOrganization` record SHALL be deleted
- **AND** the change SHALL be logged

#### Scenario: Node organization membership unchanged
- **WHEN** a node update callback includes the same organizations as currently stored
- **THEN** no database changes SHALL occur
- **AND** no unnecessary delete/create operations SHALL be performed

### Requirement: Organization sync MUST use incremental updates

The organization synchronization logic SHALL calculate the difference between current and expected memberships, applying only the necessary changes rather than full replacement.

#### Scenario: Incremental sync with mixed changes
- **WHEN** a node currently has organizations [1, 2, 3] and update specifies [2, 3, 4]
- **THEN** organization 1 SHALL be removed
- **AND** organization 4 SHALL be added
- **AND** organizations 2 and 3 SHALL remain unchanged

### Requirement: New nodes MUST continue to receive initial organization assignment

The existing behavior for new node creation SHALL be preserved. New nodes SHALL have their organizations set based on the initial callback tags.

#### Scenario: New node receives organizations
- **WHEN** a node is created via sidecar callback with `GROUP_TAG` containing organizations [1, 2]
- **THEN** `NodeOrganization` records SHALL be created for both organizations
- **AND** the `asso_groups` method SHALL be used for initial assignment
