export const toMonitorNodeOption = (
  node: Record<string, any>,
  configuredReason: string,
  unknownReason: string
) => {
  const disabledReason =
    node.deployment_state === 'configured'
      ? configuredReason
      : node.deployment_state === 'unknown'
        ? unknownReason
        : undefined;
  return {
    ...node,
    label: `${node.name} (${node.ip})`,
    value: node.id,
    disabled: Boolean(disabledReason),
    disabledReason
  };
};
