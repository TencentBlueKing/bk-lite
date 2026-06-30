export interface K8sInstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  interval?: number;
}

export function resolveK8sCurrentInstanceOption(
  options: K8sInstanceOption[],
  instanceId: string,
  idValues: string[],
  instanceName?: string
) {
  const normalizedInstanceId = String(instanceId || '');
  const normalizedName = String(instanceName || '');
  return options.find((option) => (
    option.value === normalizedInstanceId
    || option.instanceIdValues.join('|') === idValues.join('|')
    || option.instanceIdValues.includes(normalizedInstanceId)
    || (normalizedName && option.label === normalizedName)
  ));
}
