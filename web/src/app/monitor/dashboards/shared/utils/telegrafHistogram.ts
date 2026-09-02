/**
 * Telegraf inputs.prometheus (metric_version=1) flattens Prometheus histogram
 * buckets into separate series `{base}_<le>` and `{base}_+Inf`, plus `_count`/`_sum`.
 *
 * VictoriaMetrics drops `__name__` from `rate()` by default, which collapses all buckets
 * into duplicate timeseries. Use `keep_metric_names`, then restore `le` via
 * `label_replace`. Prefer the real `+Inf` series — do NOT synthesize +Inf from
 * `_count` (that yields bogus quantiles near the largest finite bucket).
 */
export const telegrafHistogramQuantile = (base: string, quantile: string, groupBy = 'instance_id') =>
  `histogram_quantile(${quantile}, sum by (${groupBy}, le) (` +
  `label_replace(rate({__name__=~"${base}_[0-9.]+", __$labels__}[5m]) keep_metric_names, ` +
  `"le", "$1", "__name__", "${base}_(.+)") ` +
  `or label_replace(rate({__name__="${base}_+Inf", __$labels__}[5m]) keep_metric_names, ` +
  `"le", "+Inf", "__name__", ".*")` +
  `))`;
