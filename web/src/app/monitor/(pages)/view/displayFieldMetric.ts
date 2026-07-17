interface DisplayMetric {
  name: string;
  monitor_plugin_name?: string;
}

interface DisplayMetricBinding {
  plugin?: string;
  metric?: string;
}

export const resolveDisplayMetric = <T extends DisplayMetric>(
  metrics: T[],
  binding: DisplayMetricBinding,
): T | undefined => {
  if (!binding.metric) return undefined;

  if (binding.plugin) {
    return metrics.find(
      (metric) =>
        metric.name === binding.metric &&
        metric.monitor_plugin_name === binding.plugin,
    );
  }

  return metrics.find((metric) => metric.name === binding.metric);
};
