export const DEFAULT_WINRM_CERTIFICATE_VALIDATION = false;

interface NodeIdentityDraft {
  ip?: string | null;
  node_name?: string | null;
}

export function applyIpAsDefaultNodeName<T extends NodeIdentityDraft>(
  row: T,
  nextIp: string
) {
  const shouldSyncNodeName =
    row.node_name === undefined ||
    row.node_name === null ||
    row.node_name === '' ||
    row.node_name === row.ip;

  return {
    ...row,
    ip: nextIp,
    ...(shouldSyncNodeName ? { node_name: nextIp } : {})
  };
}

export function applyWinrmCertificateValidation<T extends object>(
  rows: T[],
  enabled: boolean
): Array<T & { winrm_cert_validation: boolean }> {
  return rows.map((row) => ({
    ...row,
    winrm_cert_validation: enabled
  }));
}
