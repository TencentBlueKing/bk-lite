#!/usr/bin/env node
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs-extra';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webRoot = path.resolve(__dirname, '..');
const enterpriseWebLink = path.resolve(webRoot, 'enterprise');
const enterpriseWebRoot = fs.existsSync(enterpriseWebLink) ? fs.realpathSync(enterpriseWebLink) : enterpriseWebLink;
const routesManifestPath = path.join(enterpriseWebRoot, 'manifests', 'routes.json');
const appRoot = path.join(webRoot, 'src', 'app');
const enterpriseAppRoot = path.join(enterpriseWebRoot, 'src', 'app');

const createJunction = (linkPath, targetPath) => {
  if (process.platform === 'win32') {
    execSync(`cmd /c mklink /J "${linkPath}" "${targetPath}"`, { stdio: 'ignore' });
  } else {
    fs.symlinkSync(targetPath, linkPath, 'dir');
  }
};

/* ── cleanup ── */

const cleanupGenerated = async () => {
  // Remove legacy top-level (enterprise) route group
  await fs.remove(path.join(appRoot, '(enterprise)'));

  if (!(await fs.pathExists(appRoot))) return;
  const appEntries = await fs.readdir(appRoot, { withFileTypes: true });
  for (const entry of appEntries) {
    if (!entry.isDirectory() || entry.name.startsWith('(')) continue;
    // Remove (enterprise) junctions inside each module
    await fs.remove(path.join(appRoot, entry.name, '(enterprise)'));
    // Remove (enterprise) route shims inside each module's (pages)
    await fs.remove(path.join(appRoot, entry.name, '(pages)', '(enterprise)'));
  }
  // Remove generated monitor dashboard overlay files.
  await fs.remove(path.join(appRoot, 'monitor', 'dashboards', 'objects', '(enterprise)'));
  await fs.remove(path.join(appRoot, 'monitor', 'dashboards', 'objects', '(enterprise)-registry.ts'));
};

/* ── public assets: copy enterprise icons into the served CE public tree ── */

export const prepareEnterprisePublicAssets = async ({
  webRoot: targetWebRoot = webRoot,
  enterpriseWebRoot: sourceEnterpriseWebRoot = enterpriseWebRoot,
} = {}) => {
  const sourceIconsRoot = path.join(sourceEnterpriseWebRoot, 'public', 'assets', 'icons');
  const targetIconsRoot = path.join(targetWebRoot, 'public', 'assets', 'icons');

  if (!(await fs.pathExists(sourceIconsRoot))) return [];

  await fs.ensureDir(targetIconsRoot);

  const copiedIconNames = [];
  const entries = await fs.readdir(sourceIconsRoot, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith('.svg')) continue;
    const sourceIcon = path.join(sourceIconsRoot, entry.name);
    const targetIcon = path.join(targetIconsRoot, entry.name);
    if (await fs.pathExists(targetIcon)) continue;
    await fs.copy(sourceIcon, targetIcon, {
      dereference: true,
      overwrite: false,
    });
    copiedIconNames.push(entry.name);
  }

  return copiedIconNames;
};

/* ── routes: copy EE page source into CE route tree ── */

const generateRouteShims = async (routes) => {
  for (const [routePath, config] of Object.entries(routes)) {
    if (!routePath.startsWith('/')) {
      throw new Error(`enterprise route must start with "/": ${routePath}`);
    }

    const source = typeof config === 'string' ? config : config?.source;
    if (!source) {
      throw new Error(`enterprise route "${routePath}" is missing a source`);
    }

    const sourcePath = path.resolve(enterpriseWebRoot, source);
    if (!(await fs.pathExists(sourcePath))) {
      throw new Error(`enterprise route source not found for "${routePath}": ${sourcePath}`);
    }

    // Map route path to CE file: /system-manager/settings/portal
    // → src/app/system-manager/(pages)/(enterprise)/settings/portal/page.tsx
    const segments = routePath.replace(/^\/+|\/+$/g, '').split('/');
    const appName = segments[0]; // e.g. "system-manager"
    const rest = segments.slice(1); // e.g. ["settings", "portal"]
    const shimFile = path.join(appRoot, appName, '(pages)', '(enterprise)', ...rest, 'page.tsx');

    await fs.ensureDir(path.dirname(shimFile));
    let sourceContent = await fs.readFile(sourcePath, 'utf8');

    // Rewrite EE-internal imports: @/app/{appName}/xxx → @/app/{appName}/(enterprise)/xxx
    // Only rewrite if the referenced module exists in EE but NOT in CE
    const eeImportPattern = new RegExp(`(['"])@/app/${appName}/([^'"]+)`, 'g');
    sourceContent = sourceContent.replace(eeImportPattern, (match, quote, subpath) => {
      // Resolve the full import to a directory or file in CE vs EE
      const ceCandidate = path.join(appRoot, appName, subpath);
      const eeCandidate = path.join(enterpriseAppRoot, appName, subpath);
      // Check CE: try as-is, with .ts, .tsx, or as dir with index
      const ceExists = fs.existsSync(ceCandidate)
        || fs.existsSync(ceCandidate + '.ts')
        || fs.existsSync(ceCandidate + '.tsx')
        || fs.existsSync(path.join(ceCandidate, 'index.ts'))
        || fs.existsSync(path.join(ceCandidate, 'index.tsx'));
      const eeExists = fs.existsSync(eeCandidate)
        || fs.existsSync(eeCandidate + '.ts')
        || fs.existsSync(eeCandidate + '.tsx')
        || fs.existsSync(path.join(eeCandidate, 'index.ts'))
        || fs.existsSync(path.join(eeCandidate, 'index.tsx'));
      if (eeExists && !ceExists) {
        return `${quote}@/app/${appName}/(enterprise)/${subpath}`;
      }
      return match;
    });

    await fs.writeFile(shimFile, `/* Generated by scripts/prepare-enterprise.mjs */\n\n${sourceContent}`, 'utf8');
    console.log(`  📄 Route: ${routePath} → ${path.relative(webRoot, shimFile)}`);
  }
};

/* ── junctions: link EE app dirs into {module}/(enterprise)/ ── */

/* ── monitor dashboards: link (enterprise) subtree + generate -registry shim ── */

const monitorDashboardsEnterpriseSrc = path.join(
  enterpriseAppRoot, 'monitor', 'dashboards', 'objects', '(enterprise)'
);
const monitorDashboardsObjectsRoot = path.join(
  appRoot, 'monitor', 'dashboards', 'objects'
);
const monitorDashboardsEnterpriseDst = path.join(
  monitorDashboardsObjectsRoot, '(enterprise)'
);
const monitorDashboardsRegistryShimPath = path.join(
  monitorDashboardsObjectsRoot, '(enterprise)-registry.ts'
);

const linkMonitorDashboardsEnterprise = async () => {
  if (!(await fs.pathExists(monitorDashboardsEnterpriseSrc))) return false;

  await fs.ensureDir(monitorDashboardsObjectsRoot);

  // Junction: src/app/monitor/dashboards/objects/(enterprise)/
  //   -> <enterprise>/src/app/monitor/dashboards/objects/(enterprise)/
  if (await fs.pathExists(monitorDashboardsEnterpriseDst)) {
    await fs.remove(monitorDashboardsEnterpriseDst);
  }
  createJunction(monitorDashboardsEnterpriseDst, monitorDashboardsEnterpriseSrc);
  console.log(`  🔗 Junction: monitor/dashboards/objects/(enterprise)/ → enterprise/src/app/monitor/dashboards/objects/(enterprise)/`);
  return true;
};

const dashboardsManifestPath = path.join(enterpriseWebRoot, 'manifests', 'dashboards.json');

const buildMonitorDashboardsRegistryContent = (importLines = [], exportEntries = []) => `/* Generated by scripts/prepare-enterprise.mjs -- DO NOT EDIT BY HAND */

import type { ProfessionalDashboardRegistryItem } from '../shared/types';

${importLines.join('\n')}

export const ENTERPRISE_PROFESSIONAL_DASHBOARDS: ProfessionalDashboardRegistryItem[] = [
${exportEntries.join(',\n')}
];
`;

const writeMonitorDashboardsRegistry = async (content) => {
  await fs.ensureDir(monitorDashboardsObjectsRoot);
  await fs.writeFile(monitorDashboardsRegistryShimPath, content, 'utf8');
  console.log(`  📄 Dashboard registry: ${path.relative(webRoot, monitorDashboardsRegistryShimPath)}`);
};

const writeEmptyMonitorDashboardsRegistry = async () => {
  await writeMonitorDashboardsRegistry(buildMonitorDashboardsRegistryContent());
};

const generateMonitorDashboardsRegistry = async () => {
  if (!(await fs.pathExists(dashboardsManifestPath))) {
    await writeEmptyMonitorDashboardsRegistry();
    return;
  }

  if (!(await fs.pathExists(monitorDashboardsEnterpriseDst)) &&
      !(await fs.pathExists(monitorDashboardsEnterpriseSrc))) {
    await writeEmptyMonitorDashboardsRegistry();
    return;
  }

  const manifest = await fs.readJSON(dashboardsManifestPath);
  const entries = manifest?.['monitor/dashboards'];
  if (!Array.isArray(entries) || entries.length === 0) {
    await writeEmptyMonitorDashboardsRegistry();
    return;
  }

  // Required field validation
  for (const entry of entries) {
    if (!entry.key || typeof entry.key !== 'string') {
      throw new Error(`manifests/dashboards.json: entry missing "key"`);
    }
    if (!entry.source || typeof entry.source !== 'string') {
      throw new Error(`manifests/dashboards.json: entry "${entry.key}" missing "source"`);
    }
    if (!entry.groupKey || !entry.objectName || !entry.objectDisplayName) {
      throw new Error(`manifests/dashboards.json: entry "${entry.key}" missing one of groupKey/objectName/objectDisplayName`);
    }
    const entryAbsPath = path.resolve(enterpriseWebRoot, entry.source);
    if (!(await fs.pathExists(path.join(entryAbsPath, 'dashboard.tsx')))) {
      throw new Error(`manifests/dashboards.json: entry "${entry.key}" source has no dashboard.tsx at ${entryAbsPath}`);
    }
  }

  // Resolve object directory name from source path (handles trailing slashes via path.basename)
  const entryToImportName = (entry) => path.basename(entry.source);

  const importLines = entries.map((entry) => {
    const importName = `${entry.key.charAt(0).toUpperCase() + entry.key.slice(1).replace(/-([a-z])/g, (_, c) => c.toUpperCase())}Dashboard`;
    return `import ${importName} from './(enterprise)/${entryToImportName(entry)}';`;
  });

  const exportEntries = entries.map((entry) => {
    const importName = `${entry.key.charAt(0).toUpperCase() + entry.key.slice(1).replace(/-([a-z])/g, (_, c) => c.toUpperCase())}Dashboard`;
    const props = [
      `key: ${JSON.stringify(entry.key)}`,
      `groupKey: ${JSON.stringify(entry.groupKey)}`,
      `objectName: ${JSON.stringify(entry.objectName)}`,
      `objectDisplayName: ${JSON.stringify(entry.objectDisplayName)}`,
      `inheritedPermissionPath: ${JSON.stringify(entry.inheritedPermissionPath || '/monitor/view')}`,
      `component: ${importName}`
    ];
    if (entry.aliases && entry.aliases.length > 0) {
      props.push(`aliases: ${JSON.stringify(entry.aliases)}`);
    }
    return `  {\n    ${props.join(',\n    ')},\n  }`;
  });

  await writeMonitorDashboardsRegistry(
    buildMonitorDashboardsRegistryContent(importLines, exportEntries)
  );

  // Smoke test: every generated import path must resolve to a real file.
  // Catches broken path templates (e.g. extra 'objects/' segment) at build time
  // instead of letting the bug surface as silent EE dashboard degradation.
  const shimDir = path.dirname(monitorDashboardsRegistryShimPath);
  for (const importLine of importLines) {
    const match = importLine.match(/from\s+['"]([^'"]+)['"]/);
    if (!match) continue;
    const importTarget = match[1].replace(/^\.\//, '');
    const resolvedPath = path.join(shimDir, importTarget);
    if (!(await fs.pathExists(resolvedPath))) {
      throw new Error(
        `Generated shim import does not resolve: ${importLine}\n` +
        `Expected at: ${resolvedPath}\n` +
        `Check the template string in generateMonitorDashboardsRegistry.`
      );
    }
  }
};

const generateEnterpriseJunctions = async () => {
  if (!(await fs.pathExists(enterpriseAppRoot))) return [];

  const linkedModules = [];

  // Non-route directories that should be linked (api, types, utils, etc.)
  // Route directories (containing page.tsx) are handled by generateRouteShims
  const isRouteDir = async (dirPath) => {
    const hasPage = await fs.pathExists(path.join(dirPath, 'page.tsx'))
      || await fs.pathExists(path.join(dirPath, 'page.ts'))
      || await fs.pathExists(path.join(dirPath, 'page.jsx'))
      || await fs.pathExists(path.join(dirPath, 'page.js'));
    if (hasPage) return true;
    // Recursively check subdirectories
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory() && await isRouteDir(path.join(dirPath, entry.name))) {
        return true;
      }
    }
    return false;
  };

  const appEntries = await fs.readdir(enterpriseAppRoot, { withFileTypes: true });
  for (const appEntry of appEntries) {
    if (!appEntry.isDirectory()) continue;

    const appSourcePath = path.join(enterpriseAppRoot, appEntry.name);
    // Target is now inside the CE module: src/app/{module}/(enterprise)/
    const enterpriseDir = path.join(appRoot, appEntry.name, '(enterprise)');
    let hasLinked = false;

    // Link sub-directories individually, skipping those that contain route files
    await fs.ensureDir(enterpriseDir);
    const subEntries = await fs.readdir(appSourcePath, { withFileTypes: true });
    for (const sub of subEntries) {
      if (!sub.isDirectory()) continue;
      const subSource = path.join(appSourcePath, sub.name);
      const subTarget = path.join(enterpriseDir, sub.name);
      if (await isRouteDir(subSource)) {
        console.log(`  ⏭️ Skipped route dir: ${appEntry.name}/(enterprise)/${sub.name}/`);
        continue;
      }
      createJunction(subTarget, subSource);
      hasLinked = true;
      console.log(`  🔗 Junction: ${appEntry.name}/(enterprise)/${sub.name}/ → enterprise/src/app/${appEntry.name}/${sub.name}/`);
    }
    if (hasLinked) linkedModules.push(appEntry.name);
  }
  return linkedModules;
};

/* ── tsconfig: dynamically update paths for enterprise modules ── */

const TSCONFIG_PATH = path.join(webRoot, 'tsconfig.json');

const updateTsconfigPaths = async (moduleNames) => {
  const tsconfig = await fs.readJSON(TSCONFIG_PATH);
  const paths = tsconfig.compilerOptions?.paths || {};

  // Only add missing enterprise path entries, never remove existing ones.
  // Existing paths have enterpriseStub.ts fallback so they are safe to keep
  // even when the enterprise module is not present.
  let changed = false;
  for (const moduleName of moduleNames) {
    const key = `@/app/${moduleName}/(enterprise)/*`;
    if (!paths[key]) {
      paths[key] = [
        `./src/app/${moduleName}/(enterprise)/*`,
        './src/lib/enterpriseStub.ts',
      ];
      changed = true;
      console.log(`  📝 tsconfig path: ${key}`);
    }
  }

  if (changed) {
    tsconfig.compilerOptions.paths = paths;
    await fs.writeJSON(TSCONFIG_PATH, tsconfig, { spaces: 2 });
  }
};

/* ── main ── */

export const prepareEnterpriseRoutes = async () => {
  if (!(await fs.pathExists(enterpriseWebRoot))) {
    await cleanupGenerated();
    await writeEmptyMonitorDashboardsRegistry();
    await updateTsconfigPaths([]);
    console.log('ℹ️ No web/enterprise link found, skipping enterprise preparation.');
    return;
  }

  await cleanupGenerated();

  // 0.5) Copy EE public icons into CE public, because Next.js only serves
  // assets from the current app's public/ directory.
  const copiedIconNames = await prepareEnterprisePublicAssets();
  if (copiedIconNames.length) {
    console.log(`  🖼️ Public icons: ${copiedIconNames.length} enterprise icons copied`);
  }

  // 1) Junctions for api/types/etc under {module}/(enterprise)/
  const linkedModules = await generateEnterpriseJunctions();

  // 1.5) Link monitor dashboards (enterprise) subtree
  await linkMonitorDashboardsEnterprise();

  // 1.6) Generate monitor dashboards registry shim
  await generateMonitorDashboardsRegistry();

  // 2) Route shims: copy page source into CE route tree
  if (await fs.pathExists(routesManifestPath)) {
    const routes = await fs.readJSON(routesManifestPath);
    if (routes && typeof routes === 'object' && !Array.isArray(routes)) {
      await generateRouteShims(routes);
    }
  }

  // 3) Update tsconfig.json paths for enterprise modules
  await updateTsconfigPaths(linkedModules);

  console.log('✅ Enterprise modules prepared successfully.');
};

if (process.argv[1] === __filename) {
  prepareEnterpriseRoutes().catch((error) => {
    console.error('Failed to prepare enterprise:', error);
    process.exitCode = 1;
  });
}
