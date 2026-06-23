## ADDED Requirements

### Requirement: Metric range queries expose collection gap intervals
When a monitor metric range query is requested with gap detection enabled and a valid collection interval, the system SHALL return collection gap interval metadata alongside the existing metric range data.

#### Scenario: Gap interval is detected inside a coarse display step
- **WHEN** a metric is collected every 60 seconds and the displayed query step is 3600 seconds
- **AND** the underlying metric series has no reported samples for a continuous 300 second period between two displayed points
- **THEN** the range query response SHALL include a gap interval covering the missing sample period
- **AND** the existing metric `data.result` response shape SHALL remain available for chart rendering

#### Scenario: Gap detection is not requested
- **WHEN** a metric range query does not enable gap detection
- **THEN** the response SHALL preserve the existing range query behavior
- **AND** the system SHALL NOT require callers to handle gap metadata

#### Scenario: Collection interval is invalid or absent
- **WHEN** a metric range query enables gap detection without a positive collection interval
- **THEN** the system SHALL skip fine-grained gap detection
- **AND** the response SHALL remain compatible with existing range query consumers

### Requirement: Gap detection uses collection interval tolerance
The system SHALL determine collection gaps using the metric instance collection interval as the primary tolerance baseline.

#### Scenario: Missing samples exceed tolerance
- **WHEN** consecutive expected collection timestamps are missing for at least the configured gap tolerance
- **THEN** the system SHALL emit a gap interval with start time, end time, duration, and affected series metadata

#### Scenario: Missing samples are below tolerance
- **WHEN** missing samples are shorter than the configured gap tolerance
- **THEN** the system SHALL NOT emit a visible gap interval for that transient absence

#### Scenario: Multiple affected series share overlapping gaps
- **WHEN** multiple result series have overlapping or adjacent gap intervals
- **THEN** the system SHALL merge those intervals for chart display
- **AND** the merged interval metadata SHALL retain enough information to indicate affected series count or identity

### Requirement: Gap detection is bounded for long time ranges
The system SHALL bound fine-grained gap detection work so long-range monitor views do not create unbounded VictoriaMetrics query load.

#### Scenario: Detection work is within limits
- **WHEN** the requested time range and collection interval produce an allowed number of detection points
- **THEN** the system SHALL perform fine-grained gap detection
- **AND** the system SHALL return detected gap intervals in the response

#### Scenario: Detection work exceeds limits
- **WHEN** the requested time range and collection interval exceed the configured detection limit
- **THEN** the system SHALL degrade gracefully without failing the metric chart request
- **AND** the response SHALL indicate that fine-grained gap detection was limited or skipped

### Requirement: Monitor charts highlight gap intervals
Monitor time-series charts SHALL render returned collection gap intervals as visually distinct x-axis background ranges without changing the metric value line semantics.

#### Scenario: Gap metadata exists for a visible chart range
- **WHEN** chart data includes one or more gap intervals within the current x-axis domain
- **THEN** the chart SHALL render each gap interval as a noticeable low-opacity highlighted region between its start and end timestamps
- **AND** the metric lines, threshold lines, and event indicators SHALL remain visible

#### Scenario: User hovers over a highlighted interval
- **WHEN** the user hovers over or focuses a highlighted gap interval
- **THEN** the chart SHALL explain that the interval contains missing collection data
- **AND** the chart SHALL guide the user to narrow the time range to inspect the gap in detail

#### Scenario: No gap metadata exists
- **WHEN** chart data has no returned gap intervals
- **THEN** the chart SHALL render with the existing visual behavior

### Requirement: Gap highlighting is consistent across monitor chart implementations
The system SHALL apply the same gap interval data contract to the Recharts-based monitor line chart and the ECharts-based dashboard line chart.

#### Scenario: Common monitor metric view renders gaps
- **WHEN** a common monitor metric view receives gap interval metadata
- **THEN** the Recharts line chart SHALL render the highlighted intervals using the shared gap data contract

#### Scenario: Object dashboard renders gaps
- **WHEN** an object dashboard line chart receives gap interval metadata
- **THEN** the ECharts line chart SHALL render equivalent highlighted intervals using the shared gap data contract

#### Scenario: Chart library-specific rendering differs internally
- **WHEN** Recharts and ECharts require different rendering primitives for interval backgrounds
- **THEN** both implementations SHALL produce equivalent user-visible gap highlighting from the same gap metadata
