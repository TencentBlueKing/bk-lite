## ADDED Requirements

### Requirement: Memory extraction
The system SHALL use LLM to extract valuable information from input content based on memory space guidelines.

#### Scenario: Extract with guidelines
- **WHEN** memory service receives content and guidelines
- **THEN** system calls LLM to extract information following the guidelines

#### Scenario: No valuable content
- **WHEN** LLM determines no content worth memorizing
- **THEN** system returns empty result and skips memory write

#### Scenario: Use configured model
- **WHEN** memory space has model configured
- **THEN** system uses the configured model for extraction

### Requirement: Memory merge
The system SHALL merge new memory content with existing memory content using LLM.

#### Scenario: Merge with existing memory
- **WHEN** memory entry already exists for the user/organization
- **THEN** system calls LLM to merge new content with existing content

#### Scenario: Create new memory
- **WHEN** no memory entry exists for the user/organization
- **THEN** system creates new memory entry with extracted content

#### Scenario: Deduplicate content
- **WHEN** merging memories
- **THEN** system removes duplicate information and consolidates related content

### Requirement: Async memory write task
The system SHALL process memory writes asynchronously using Celery.

#### Scenario: Task triggered
- **WHEN** memory write node triggers write
- **THEN** system enqueues Celery task and returns immediately

#### Scenario: Task execution
- **WHEN** Celery task executes
- **THEN** system extracts memory, merges with existing, and saves to database

#### Scenario: Task retry on failure
- **WHEN** Celery task fails
- **THEN** system retries the task according to retry policy

### Requirement: Memory source tracking
The system SHALL track the source of memory writes for auditing.

#### Scenario: Record source workflow
- **WHEN** memory is written
- **THEN** system records source_workflow and source_node fields

#### Scenario: Update timestamp
- **WHEN** memory is updated
- **THEN** system updates the updated_at timestamp
