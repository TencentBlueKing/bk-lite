export interface ProxyTargets {
  targetUrl: string;
  logTarget: string;
}

export function buildProxyTargets(targetServer: string, targetPath: string, search: string): ProxyTargets {
  const logTarget = `${targetServer}${targetPath}`;
  return {
    targetUrl: `${logTarget}${search}`,
    logTarget,
  };
}
