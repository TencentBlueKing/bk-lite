export const DEFAULT_WINRM_CERTIFICATE_VALIDATION = false;

export function applyWinrmCertificateValidation<T extends object>(
  rows: T[],
  enabled: boolean
): Array<T & { winrm_cert_validation: boolean }> {
  return rows.map((row) => ({
    ...row,
    winrm_cert_validation: enabled
  }));
}
