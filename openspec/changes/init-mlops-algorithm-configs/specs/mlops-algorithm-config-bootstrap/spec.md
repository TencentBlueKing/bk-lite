## ADDED Requirements

### Requirement: MLOPS bootstrap command imports default algorithm configs from support-files
The system SHALL provide a management command that loads default `AlgorithmConfig` records from `server/apps/mlops/support-files/algorithm-configs/` using the fixed path pattern `<algorithm_type>/<name>.json`.

#### Scenario: Command scans default algorithm config files
- **WHEN** the bootstrap command is executed
- **THEN** it reads only direct `.json` files under each allowed `algorithm_type` directory in `server/apps/mlops/support-files/algorithm-configs/`
- **THEN** it ignores non-JSON files and deeper nested paths

### Requirement: Bootstrap command only accepts supported algorithm type directories
The bootstrap command SHALL only import files whose parent directory name matches a supported `AlgorithmConfig` algorithm type.

#### Scenario: Unsupported directory is not imported
- **WHEN** a JSON file is placed under a directory that is not a supported `algorithm_type`
- **THEN** the command does not create an `AlgorithmConfig` record from that file
- **THEN** the command ignores that directory during import scanning

### Requirement: Bootstrap command validates the default config file contract
Each imported JSON file SHALL be a top-level object containing exactly `name`, `display_name`, `image`, `scenario_description`, and `form_config`, and `form_config` SHALL be a JSON object.

#### Scenario: Valid default config file is accepted
- **WHEN** a JSON file contains all required fields with valid top-level types
- **THEN** the command treats the file as importable

#### Scenario: Invalid default config file is rejected
- **WHEN** a JSON file cannot be parsed, is not an object, is missing required fields, contains unknown fields, has invalid field types, or has a `name` value that is not exactly equal to the filename stem without the `.json` extension
- **THEN** the command does not create an `AlgorithmConfig` record from that file
- **THEN** the command records the file as invalid in command output and logs

### Requirement: Bootstrap command performs first-write initialization only
The bootstrap command SHALL use `(algorithm_type, name)` as the identity of a default algorithm config and SHALL create a record only when no existing record with the same identity exists.

#### Scenario: Missing algorithm config is created
- **WHEN** a valid default config file is processed and no existing `AlgorithmConfig` record has the same `(algorithm_type, name)`
- **THEN** the command creates a new `AlgorithmConfig` record using the file contents
- **THEN** the created record uses the parent directory name as its `algorithm_type` value
- **THEN** fields not present in the JSON contract use model-level defaults

#### Scenario: Existing algorithm config is preserved
- **WHEN** a valid default config file is processed and an existing `AlgorithmConfig` record already has the same `(algorithm_type, name)`
- **THEN** the command skips creation for that file
- **THEN** the command does not overwrite existing database values

### Requirement: Bootstrap command does not block global batch initialization on file-level failures
File-level import failures SHALL NOT abort the bootstrap command or prevent other valid files from being processed.

#### Scenario: Invalid file does not stop later imports
- **WHEN** one default config file is invalid and another default config file is valid in the same command run
- **THEN** the valid file is still processed after the invalid file
- **THEN** the command completes with a summary of created, skipped existing, and invalid files

### Requirement: Bootstrap command reports import results through command output and MLOPS lifecycle logs
The bootstrap command SHALL emit per-file error details through management command output and SHALL emit a final import summary through management command output plus the MLOPS logger.

#### Scenario: Command reports summary and invalid file reason
- **WHEN** the bootstrap command finishes
- **THEN** it prints a summary including counts for created, skipped existing, and invalid files
- **THEN** each invalid file includes its path and failure reason in command output

### Requirement: Batch initialization provides an MLOPS algorithm config bootstrap entrypoint
The server batch initialization flow SHALL provide an MLOPS initialization step that invokes the algorithm config bootstrap command.

#### Scenario: Batch initialization calls MLOPS bootstrap command
- **WHEN** batch initialization includes the `mlops` module
- **THEN** the batch initialization flow invokes the MLOPS algorithm config bootstrap command as the MLOPS initialization step
