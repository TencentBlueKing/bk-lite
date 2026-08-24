export const WINRM_HTTP_PORT = 5985;
export const WINRM_HTTPS_PORT = 5986;

export type WinrmScheme = 'http' | 'https';

export const defaultWinrmPort = (scheme: WinrmScheme = 'https') =>
  scheme === 'http' ? WINRM_HTTP_PORT : WINRM_HTTPS_PORT;

export const syncWinrmPort = (
  currentPort: number | undefined,
  nextScheme: WinrmScheme
) => {
  const previousDefault =
    nextScheme === 'http' ? WINRM_HTTPS_PORT : WINRM_HTTP_PORT;
  if (!currentPort || currentPort === previousDefault) {
    return defaultWinrmPort(nextScheme);
  }
  return currentPort;
};

export const isWinrmSchemePortMismatch = (
  scheme: WinrmScheme | undefined,
  port?: number
) => {
  if (!scheme || !port) {
    return false;
  }
  return (
    (scheme === 'https' && port === WINRM_HTTP_PORT) ||
    (scheme === 'http' && port === WINRM_HTTPS_PORT)
  );
};

export const applyWinrmScheme = <T extends object>(
  rows: T[],
  scheme: WinrmScheme
): T[] =>
  rows.map((row) => ({
    ...row,
    winrm_scheme: scheme,
    port: syncWinrmPort((row as { port?: number }).port, scheme),
    ...(scheme === 'http' ? { winrm_cert_validation: false } : {})
  }));
