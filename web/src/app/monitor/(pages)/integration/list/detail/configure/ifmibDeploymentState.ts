export const applyIfmibDeploymentState = (
  defaultForm: Record<string, unknown>,
  enableIfmibFromUrl: boolean
) => {
  if (!Object.prototype.hasOwnProperty.call(defaultForm, 'enable_ifmib')) {
    return defaultForm;
  }

  return {
    ...defaultForm,
    enable_ifmib: enableIfmibFromUrl
  };
};

export const getIfmibDeploymentPatch = (
  defaultForm: Record<string, unknown>,
  enableIfmibFromUrl: boolean
) => {
  if (!Object.prototype.hasOwnProperty.call(defaultForm, 'enable_ifmib')) {
    return {};
  }

  return { enable_ifmib: enableIfmibFromUrl };
};

export const getIfmibSnapshotEnabled = (
  configContent: Record<string, unknown>,
  supportsIfmib: boolean
): boolean | undefined => {
  if (!supportsIfmib) return undefined;
  const child = configContent.child;
  if (typeof child !== 'object' || child === null) return undefined;
  const content = (child as Record<string, unknown>).content;
  if (typeof content !== 'object' || content === null) return undefined;
  const inputs = (content as Record<string, unknown>).inputs;
  if (typeof inputs !== 'object' || inputs === null) return undefined;
  const snmpInputs = (inputs as Record<string, unknown>).snmp;
  if (!Array.isArray(snmpInputs)) return undefined;
  return snmpInputs.some((input) => {
    if (typeof input !== 'object' || input === null) return false;
    const tables = (input as Record<string, unknown>).table;
    return Array.isArray(tables) && tables.some((table) => (
      typeof table === 'object'
      && table !== null
      && (table as Record<string, unknown>).name === 'interface'
    ));
  });
};
