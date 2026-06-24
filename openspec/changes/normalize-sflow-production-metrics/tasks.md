## 1. Test Coverage

- [x] 1.1 Add monitor plugin tests that assert sFlow bytes/packets queries do not multiply by `effective_sampling_rate` or `sflow_sampling_rate`.
- [x] 1.2 Update shared Flow metric tests so NetFlow still requires sampling-rate normalization while sFlow explicitly forbids second-pass normalization.
- [x] 1.3 Add monitor plugin tests that assert sFlow endpoint metrics group by `src_ip` and `dst_ip`, not `src` and `dst`.
- [x] 1.4 Add monitor plugin tests that assert sFlow protocol and conversation metrics use `header_protocol`, not `protocol`.
- [x] 1.5 Add monitor plugin tests that assert sFlow interface metrics use `input_ifindex` and `output_ifindex`.

## 2. sFlow Plugin Metrics

- [x] 2.1 Update switch sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.2 Update router sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.3 Update firewall sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.4 Update load balancer sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.5 Rewrite sFlow endpoint metrics to group by `src_ip` and `dst_ip`.
- [x] 2.6 Rewrite sFlow protocol metrics to group by `header_protocol`.
- [x] 2.7 Rewrite sFlow conversation metrics to group by `src_ip`, `dst_ip`, `header_protocol`, and `dst_port`.
- [x] 2.8 Review sFlow interface metrics so ingress uses `input_ifindex` and egress uses `output_ifindex`.
- [x] 2.9 Decide whether to add `sflow_drops` and/or `sflow_frame_length` as sFlow diagnostic metrics.

## 3. Descriptions and Translations

- [x] 3.1 Update sFlow metric descriptions so they no longer imply query-time sampling-rate normalization.
- [x] 3.2 Update bilingual metric translations for any renamed or newly added sFlow diagnostic metrics.
- [x] 3.3 Keep existing user-facing Flow plugin names and low-cardinality default indicators unless a metric is intentionally added or removed.

## 4. Validation and Rollout Notes

- [x] 4.1 Validate all changed sFlow `metrics.json` files remain valid JSON.
- [x] 4.2 Run targeted monitor plugin metric tests.
- [x] 4.3 Confirm Flow onboarding, access guide, and asset-mapping tests still pass without schema changes.
- [x] 4.4 Document the operational refresh path for built-in monitor plugin templates after deployment.
- [x] 4.5 Add and run a local sFlow production contract script that checks the screenshot sample math, production labels, and no second-pass sampling normalization.
