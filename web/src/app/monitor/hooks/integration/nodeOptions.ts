export const toMonitorNodeOption = (
  node: Record<string, any>,
  configuredReason: string
) => {
  const disabled = node.deployment_state === 'configured';
  return {
    ...node,
    label: `${node.name} (${node.ip})`,
    value: node.id,
    disabled,
    disabledReason: disabled ? configuredReason : undefined
  };
};
