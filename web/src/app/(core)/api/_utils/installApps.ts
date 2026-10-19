import fs from 'fs/promises';

const ALWAYS_ON_APPS = ['module-link'];

const parseInstallApps = (value?: string) => {
  return (value || '')
    .split(',')
    .map((app) => app.trim())
    .filter(Boolean);
};

const discoverInstallApps = async (appRoot: string) => {
  try {
    const entries = await fs.readdir(appRoot, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .filter((name) => !name.startsWith('(') && !name.startsWith('.') && name !== 'api');
  } catch {
    return [];
  }
};

export const getInstallApps = async (appRoots: string[]) => {
  const configuredApps = parseInstallApps(process.env.NEXTAPI_INSTALL_APP);
  if (configuredApps.length > 0) {
    return Array.from(new Set([...configuredApps, ...ALWAYS_ON_APPS]));
  }

  const discoveredApps = await Promise.all(appRoots.map(discoverInstallApps));
  return Array.from(new Set(discoveredApps.flat()));
};
