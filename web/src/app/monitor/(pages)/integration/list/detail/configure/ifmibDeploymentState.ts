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

const PUBLIC_IFMIB_TABLE_OIDS = new Set([
  '1.3.6.1.2.1.2.2',
  '1.3.6.1.2.1.31.1.1',
  'IF-MIB::ifTable',
  'IF-MIB::ifXTable'
]);

const PUBLIC_IFDESCR_OIDS = new Set([
  '1.3.6.1.2.1.2.2.1.2',
  '1.3.6.1.2.1.31.1.1.1.1',
  'IF-MIB::ifDescr'
]);

const isPublicIfmibTable = (table: Record<string, unknown>): boolean => {
  const tableOid = table.oid;
  if (typeof tableOid === 'string' && PUBLIC_IFMIB_TABLE_OIDS.has(tableOid)) {
    return true;
  }
  if ((tableOid != null && tableOid !== '') || table.name !== 'interface') {
    return false;
  }
  const fields = table.field;
  return Array.isArray(fields) && fields.some((field) => (
    typeof field === 'object'
    && field !== null
    && (field as Record<string, unknown>).name === 'ifDescr'
    && typeof (field as Record<string, unknown>).oid === 'string'
    && PUBLIC_IFDESCR_OIDS.has((field as Record<string, unknown>).oid as string)
  ));
};

const hasPublicIfmibTable = (tables: unknown): boolean => (
  Array.isArray(tables)
  && tables.some((table) => (
    typeof table === 'object'
    && table !== null
    && isPublicIfmibTable(table as Record<string, unknown>)
  ))
);

const snmpInputHasInterfaceTable = (input: unknown): boolean => {
  if (typeof input !== 'object' || input === null) return false;
  return hasPublicIfmibTable((input as Record<string, unknown>).table);
};

/**
 * Collect SNMP input objects from child content.
 *
 * ConfigFormat.toml_to_dict stores Telegraf child as:
 *   { plugin, config: <first snmp input>, _toml_document: <full TOML> }
 * Legacy/raw shapes may still expose content.inputs.snmp.
 */
const collectSnmpInputs = (
  content: Record<string, unknown>
): unknown[] | undefined => {
  const document = content._toml_document;
  if (typeof document === 'object' && document !== null) {
    const inputs = (document as Record<string, unknown>).inputs;
    if (typeof inputs === 'object' && inputs !== null) {
      const snmpInputs = (inputs as Record<string, unknown>).snmp;
      if (Array.isArray(snmpInputs)) {
        return snmpInputs;
      }
    }
  }

  const config = content.config;
  if (typeof config === 'object' && config !== null) {
    return [config];
  }

  const inputs = content.inputs;
  if (typeof inputs === 'object' && inputs !== null) {
    const snmpInputs = (inputs as Record<string, unknown>).snmp;
    if (Array.isArray(snmpInputs)) {
      return snmpInputs;
    }
  }

  return undefined;
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

  const snmpInputs = collectSnmpInputs(content as Record<string, unknown>);
  if (snmpInputs === undefined) return undefined;
  return snmpInputs.some(snmpInputHasInterfaceTable);
};
