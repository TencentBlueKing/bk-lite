export function hasAppAccess(
  apps: Array<{ name?: string | null }> | null | undefined,
  appName: string
): boolean {
  return Boolean(apps?.some((app) => app.name === appName));
}

export function listAuthorizedCapabilityApps(
  authorizedNames: Iterable<string>,
  catalogNames: readonly string[]
): string[] {
  const allowed = new Set(authorizedNames);
  return catalogNames.filter((name) => allowed.has(name));
}
