export interface PolicyGroupAccessRule {
  name: string;
  plugin_id: number | string;
  metric_name?: string;
}

export type PolicyGroupAccessNote =
  | { kind: 'none' }
  | { kind: 'no-plugin-rules' }
  | { kind: 'missing'; names: string[] };

export const policyGroupAccessNotes = (
  rules: PolicyGroupAccessRule[] | undefined,
  pluginId: number | string,
  pluginMetricNames: string[],
): PolicyGroupAccessNote => {
  const mine = (rules || []).filter(
    (rule) => String(rule.plugin_id) === String(pluginId),
  );
  if (!mine.length) return { kind: 'no-plugin-rules' };
  if (!pluginMetricNames.length) return { kind: 'none' };
  const names = mine
    .filter(
      (rule) =>
        Boolean(rule.metric_name) &&
        !pluginMetricNames.includes(rule.metric_name || ''),
    )
    .map((rule) => rule.name);
  if (!names.length) return { kind: 'none' };
  return { kind: 'missing', names };
};
