## ADDED Requirements

### Requirement: Resource type selection
The system SHALL expose a host resource Top10 data-source operation at `monitor/get_host_resource_top` that requires exactly one supported `metric_type` value: `cpu`, `memory`, or `disk`.

#### Scenario: Query a supported resource type
- **WHEN** an authorized data-source request supplies `metric_type=cpu`, `metric_type=memory`, or `metric_type=disk`
- **THEN** the system queries and ranks the corresponding host resource usage

#### Scenario: Reject a missing or unsupported resource type
- **WHEN** `metric_type` is missing, empty, or not one of `cpu`, `memory`, and `disk`
- **THEN** the system returns the standard failure contract with a validation message and does not query host metrics

#### Scenario: Keep the result limit fixed
- **WHEN** a caller requests any supported resource type
- **THEN** the system returns at most 10 rows and does not accept a caller-controlled result limit

### Requirement: Organization-scoped host visibility
The system MUST calculate rankings only from hosts visible to the current user in the current organization according to the injected `user_info`, including the existing child-organization visibility rules.

#### Scenario: Exclude an unauthorized high-usage host
- **WHEN** an unauthorized host has a higher usage value than every authorized host
- **THEN** the unauthorized host does not appear in the result and does not displace an authorized host from the Top10

#### Scenario: Fail closed when visibility resolution fails
- **WHEN** the system cannot resolve the current organization, user permissions, or visible CMDB hosts
- **THEN** the request fails and the system does not fall back to an unrestricted metric ranking

#### Scenario: Do not disclose unauthorized host details
- **WHEN** metric storage contains series for unauthorized hosts
- **THEN** the response and normal diagnostic logs contain no identifiers or metadata from those hosts

### Requirement: Cross-platform metric normalization
The system SHALL combine the supported Linux and Windows WMI metrics into one normalized candidate set for each requested resource type.

#### Scenario: Include Linux and Windows CPU hosts
- **WHEN** authorized Linux hosts report `host_cpu_usage_percent` and authorized Windows hosts report `host_cpu_usage_percent_gauge`
- **THEN** valid fresh values from both operating systems participate in the same CPU ranking

#### Scenario: Include Linux and Windows memory hosts
- **WHEN** authorized Linux hosts report `host_mem_used_percent` and authorized Windows hosts report `host_mem_used_percent_gauge`
- **THEN** valid fresh values from both operating systems participate in the same memory ranking

#### Scenario: Include Linux and Windows disk hosts
- **WHEN** authorized Linux hosts report `host_disk_used_percent` and authorized Windows hosts report `host_disk_used_percent_gauge`
- **THEN** valid fresh filesystem values from both operating systems participate in disk normalization

#### Scenario: Resolve duplicate platform series by sample time
- **WHEN** the same authorized `instance_id` has valid Linux and Windows candidates for CPU or memory
- **THEN** the system keeps the candidate with the later original sample timestamp

### Requirement: Dynamic sample freshness
The system MUST accept a metric candidate only when its original sample age is no greater than twice that host's configured collection interval.

#### Scenario: Accept a fresh sample
- **WHEN** a host has a 5-minute collection interval and its candidate was sampled no more than 10 minutes ago
- **THEN** the candidate remains eligible for ranking

#### Scenario: Reject a stale sample
- **WHEN** a host has a 5-minute collection interval and its candidate was sampled more than 10 minutes ago
- **THEN** the candidate is excluded from ranking

#### Scenario: Use the default interval
- **WHEN** a host's collection interval is missing, unparsable, or not positive
- **THEN** the system treats its collection interval as 5 minutes and accepts only samples no older than 10 minutes

#### Scenario: Use original sample time
- **WHEN** a metric query returns both an execution time and an original sample time
- **THEN** the system evaluates freshness using the original sample time

### Requirement: Valid usage values
The system SHALL rank only finite numeric usage percentages in the inclusive range from 0 through 100.

#### Scenario: Discard malformed and non-finite values
- **WHEN** a candidate value is missing, non-numeric, `NaN`, positive infinity, or negative infinity
- **THEN** the system excludes that candidate without failing otherwise valid rows

#### Scenario: Discard out-of-range values
- **WHEN** a candidate usage percentage is less than 0 or greater than 100
- **THEN** the system excludes that candidate

### Requirement: Per-host disk normalization
For a disk request, the system MUST select one fresh valid filesystem candidate per authorized host before calculating the host Top10.

#### Scenario: Select the fullest filesystem for a host
- **WHEN** one host has fresh valid filesystems at 61%, 92%, and 74% usage
- **THEN** that host participates in the disk ranking with the 92% filesystem and its filesystem metadata

#### Scenario: Ignore a stale fuller filesystem
- **WHEN** one host has a stale filesystem at 95% and a fresh filesystem at 80%
- **THEN** that host participates with the fresh 80% filesystem

#### Scenario: Resolve equal filesystem usage deterministically
- **WHEN** one host has multiple fresh filesystems with the same highest usage percentage
- **THEN** the system selects one deterministically by normalized `mount`, then `path`, then `fstype` in ascending order

#### Scenario: Return at most one disk row per host
- **WHEN** an authorized host has multiple valid filesystem series
- **THEN** the final disk result contains at most one row for that `instance_id`

### Requirement: Stable Top10 ranking
The system SHALL sort normalized host candidates by usage percentage descending, then by display name ascending, then by instance ID ascending, return at most the first 10, and assign one-based ranks after truncation.

#### Scenario: Rank more than ten eligible hosts
- **WHEN** more than 10 authorized hosts have fresh valid normalized candidates
- **THEN** the system returns exactly the first 10 according to the stable ordering with ranks 1 through 10

#### Scenario: Rank equal usage values stably
- **WHEN** multiple eligible hosts have the same usage percentage
- **THEN** their relative order is determined by display name and then instance ID in ascending order

#### Scenario: Return fewer than ten hosts
- **WHEN** fewer than 10 authorized hosts have eligible candidates
- **THEN** the system returns all eligible hosts with contiguous ranks beginning at 1

#### Scenario: Return an empty successful result
- **WHEN** no authorized host has an eligible candidate
- **THEN** the system returns a successful response with an empty data array

### Requirement: Unified leaderboard and table response
The system SHALL return each ranked host as one structured row containing `rank`, `display_name`, `usage_percent`, `instance_id`, `host_name`, `ip`, `metric_type`, `mount`, `path`, `fstype`, and `sampled_at`.

#### Scenario: Build the display name
- **WHEN** both host name and IP are available
- **THEN** `display_name` is formatted as `host_name (ip)`

#### Scenario: Fall back when display metadata is incomplete
- **WHEN** host name or IP is unavailable
- **THEN** `display_name` falls back in order to host name, IP, and finally instance ID

#### Scenario: Return CPU or memory rows
- **WHEN** the requested type is `cpu` or `memory`
- **THEN** `mount`, `path`, and `fstype` are null and all other required fields are present

#### Scenario: Return a disk row
- **WHEN** the requested type is `disk`
- **THEN** the row contains the selected filesystem's normalized mount, path, and filesystem type

#### Scenario: Format value and time fields
- **WHEN** a ranked row is returned
- **THEN** `usage_percent` is a numeric value rounded to two decimal places and `sampled_at` is a timezone-aware ISO 8601 string

### Requirement: Operations-analysis data-source definition
The system SHALL provide an idempotently initialized operations-analysis data source for the host resource Top10 operation with `topN` and `table` chart types, a required component-switching `metric_type` selector, and a field schema for every response field.

#### Scenario: Configure the metric selector
- **WHEN** the built-in data source is initialized
- **THEN** its `metric_type` parameter defaults to `cpu` and offers static CPU, memory, and disk options mapped to `cpu`, `memory`, and `disk`

#### Scenario: Configure the leaderboard
- **WHEN** the data source is used by a `topN` component
- **THEN** the component can map its label field to `display_name` and its value field to `usage_percent`

#### Scenario: Configure the table
- **WHEN** the data source is used by a table component
- **THEN** the table can select columns from the complete response field schema without transforming the response

### Requirement: Failure isolation
The system SHALL use the existing NATS result envelope and distinguish request-level dependency failures from malformed individual metric series.

#### Scenario: Fail when VictoriaMetrics is unavailable
- **WHEN** the metric query fails or returns an unsuccessful storage response
- **THEN** the operation returns the standard failure contract without partial ranked data

#### Scenario: Continue after one malformed series
- **WHEN** one metric series is malformed but other authorized series are valid
- **THEN** the malformed series is discarded and the valid series are still ranked

#### Scenario: Avoid exposing internal diagnostics
- **WHEN** the operation returns an error
- **THEN** the response omits credentials, connection addresses, full query expressions, stack traces, and unauthorized host identifiers
