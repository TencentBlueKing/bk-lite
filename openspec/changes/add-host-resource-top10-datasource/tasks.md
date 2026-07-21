## 1. Establish Failing Service Contracts

- [x] 1.1 Add focused service tests for `metric_type` validation, fixed Top10 limit, stable tie ordering, rank assignment, and successful empty results.
- [x] 1.2 Add visibility tests proving unauthorized high-usage hosts are filtered before ranking and permission/CMDB resolution fails closed.
- [x] 1.3 Add Linux, Windows, and mixed-platform fixtures covering all six resource metric names and duplicate-platform resolution by original sample timestamp.
- [x] 1.4 Add freshness tests for per-host `2 × collection_interval`, the invalid/missing-period 5-minute fallback, and exclusion of malformed, non-finite, and out-of-range values.
- [x] 1.5 Add disk tests for fresh-filesystem filtering, per-host maximum selection, deterministic equal-value selection, and one final row per host.
- [x] 1.6 Add response-contract tests for every required field, display-name fallback, null CPU/memory filesystem fields, disk metadata, two-decimal numeric usage, and timezone-aware `sampled_at`.

## 2. Implement the Host Resource Ranking Service

- [x] 2.1 Create an isolated host-resource Top10 service with typed constants/data structures for supported resource types, platform metric mappings, normalized candidates, and response rows.
- [x] 2.2 Integrate the existing current-user/current-organization CMDB visibility path to resolve an exact authorized `instance_id` allowlist plus host name, IP, and collection interval metadata.
- [x] 2.3 Implement VictoriaMetrics candidate retrieval that preserves original sample timestamps, bounds the requested lookback by authorized-host freshness windows, and safely narrows the query when feasible.
- [x] 2.4 Normalize Linux and Windows CPU/memory candidates, enforce the authorization allowlist and value validation, apply per-host freshness, and resolve duplicate platform series by latest sample time.
- [x] 2.5 Normalize Linux and Windows disk candidates and filesystem labels, apply authorization/value/freshness filters, and select each host's highest-usage filesystem deterministically.
- [x] 2.6 Implement stable cross-host sorting, fixed Top10 truncation, rank assignment, CMDB enrichment, display-name fallback, and the unified response-row formatter.
- [x] 2.7 Add sanitized aggregate logging for discarded candidate categories and dependency failures without emitting unauthorized host identifiers, full queries, connection details, or credentials.

## 3. Expose the NATS Operation

- [ ] 3.1 Add failing NATS contract tests for all supported `metric_type` values, invalid/missing values, service success, service failure, and empty data.
- [x] 3.2 Register the thin `monitor/get_host_resource_top` NATS handler, delegate to the ranking service using injected `user_info`, and return the established `{result, data, message}` envelope.
- [ ] 3.3 Verify CMDB/permission and VictoriaMetrics failures return no partial ranking while an individual malformed series does not fail otherwise valid results.

## 4. Register the Operations-Analysis Data Source

- [ ] 4.1 Add a failing initialization test for an idempotent built-in data source with `rest_api=monitor/get_host_resource_top` and `chart_type=[topN, table]`.
- [x] 4.2 Add the required string `metric_type` parameter with default `cpu`, a component-switching static selector, and CPU/memory/disk options.
- [x] 4.3 Add the complete field schema for `rank`, `display_name`, `usage_percent`, `instance_id`, `host_name`, `ip`, `metric_type`, `mount`, `path`, `fstype`, and `sampled_at`.
- [x] 4.4 Add focused compatibility assertions that `topN` can map `display_name`/`usage_percent` and table rendering can consume the same untransformed rows.

## 5. Verification and Operational Handoff

- [ ] 5.1 Run the focused monitor service, NATS contract, and operations-analysis data-source initialization test suites.
- [ ] 5.2 Run affected backend lint/format/type checks and inspect the final diff for secrets, unrelated changes, unsafe raw SQL, and unbounded diagnostic output.
- [ ] 5.3 Preview the initialized data source for `cpu`, `memory`, and `disk`, confirming Linux/Windows merging, permission scope, newness filtering, stable Top10 order, and both `topN` and `table` consumption.
- [ ] 5.4 Document deployment and rollback verification: the initialization path remains idempotent, no database migration is required, and disabling/removing the built-in data source leaves existing monitor interfaces unchanged.
