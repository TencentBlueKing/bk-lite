import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { dashboardQueryCapabilityId } from '../src/app/monitor/dashboards/shared/utils/query-capability';
import {
  FLOW_SUPPORTED_OBJECT_NAMES,
  resolveInstanceTypeFromObjectName,
  type FlowProtocol,
} from '../src/app/monitor/dashboards/objects/flow-common/constants';
import {
  buildConversationTopQuery,
  buildFlowCollectionStatusQuery,
  buildFlowMetricQueries,
  buildProtocolTopQuery,
} from '../src/app/monitor/dashboards/objects/flow-common/queries';

interface CapabilityEntry {
  id: string;
  object_names: string[];
  template: string;
}

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const objectsRoot = join(webRoot, 'src/app/monitor/dashboards/objects');
const outputPath = resolve(webRoot, '../server/apps/monitor/support-files/dashboard_query_capabilities.json');
const sourceFiles: string[] = [];
const directoryRouteKeys = new Map<string, string>();

const metadataSource = readFileSync(
  join(webRoot, 'src/app/monitor/dashboards/metadata.ts'),
  'utf8',
);
const objectNameByRoute = new Map<string, string>();
for (const match of metadataSource.matchAll(
  /\{\s*key:\s*'([^']+)'[\s\S]*?objectName:\s*'([^']+)'[\s\S]*?\}/g,
)) {
  objectNameByRoute.set(match[1], match[2]);
}

const walk = (directory: string) => {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path);
    if (entry.isFile() && (entry.name === 'config.ts' || entry.name === 'queries.ts')) {
      sourceFiles.push(path);
    }
  }
};

const capabilityMap = new Map<string, { template: string; objectNames: Set<string> }>();

const register = (template: string, objectName: string) => {
  if (!template.includes('__$labels__')) return;
  const selectors = Array.from(template.matchAll(/\{([^{}]*)\}/g), (match) => match[1]);
  if (!selectors.length || selectors.some((selector) => !selector.includes('__$labels__'))) {
    throw new Error(`unscoped dashboard query template for ${objectName}: ${template}`);
  }
  const id = dashboardQueryCapabilityId(template);
  const existing = capabilityMap.get(id);
  if (existing && existing.template !== template) {
    throw new Error(`dashboard query capability collision: ${id}`);
  }
  const value = existing || { template, objectNames: new Set<string>() };
  value.objectNames.add(objectName);
  capabilityMap.set(id, value);
};

const collectTemplates = (
  value: unknown,
  objectName: string,
  seen = new Set<unknown>(),
) => {
  if (typeof value === 'string') {
    register(value, objectName);
    return;
  }
  if (!value || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  if (Array.isArray(value)) {
    value.forEach((item) => collectTemplates(item, objectName, seen));
    return;
  }
  Object.values(value).forEach((item) => collectTemplates(item, objectName, seen));
};

const resolveObjectNameForFile = (file: string) => {
  const relative = file.slice(objectsRoot.length + 1);
  const directory = relative.split('/')[0];
  const routeKey = directoryRouteKeys.get(directory) || directory;
  return objectNameByRoute.get(routeKey);
};

const registerStaticModules = async () => {
  walk(objectsRoot);
  for (const file of sourceFiles.filter((item) => item.endsWith('/config.ts')).sort()) {
    const loadedModule = await import(pathToFileURL(file).href);
    for (const value of Object.values(loadedModule)) {
      if (!value || typeof value !== 'object') continue;
      const candidate = value as { routeKey?: unknown };
      if (typeof candidate.routeKey !== 'string') continue;
      const relative = file.slice(objectsRoot.length + 1);
      directoryRouteKeys.set(relative.split('/')[0], candidate.routeKey);
    }
  }
  for (const file of sourceFiles.sort()) {
    const objectName = resolveObjectNameForFile(file);
    if (!objectName || file.includes('/flow-common/')) continue;
    const loadedModule = await import(pathToFileURL(file).href);
    collectTemplates(loadedModule, objectName);
  }
};

const registerFlowCapabilities = () => {
  const protocols: FlowProtocol[] = ['netflow', 'sflow'];
  for (const objectName of FLOW_SUPPORTED_OBJECT_NAMES) {
    const instanceType = resolveInstanceTypeFromObjectName(objectName);
    if (!instanceType) continue;
    for (const protocol of protocols) {
      register(buildFlowCollectionStatusQuery(instanceType, protocol), objectName);
      register(buildConversationTopQuery(instanceType, protocol), objectName);
      register(buildProtocolTopQuery(instanceType, protocol), objectName);
      Object.values(buildFlowMetricQueries(instanceType, protocol)).forEach((template) => {
        register(template, objectName);
      });
    }
  }
};

const main = async () => {
  await registerStaticModules();
  registerFlowCapabilities();

  const knownObjectNames = new Set(objectNameByRoute.values());
  const capabilities: CapabilityEntry[] = Array.from(capabilityMap, ([id, value]) => ({
    id,
    object_names: Array.from(value.objectNames).sort(),
    template: value.template,
  })).sort((left, right) => left.id.localeCompare(right.id));

  capabilities.forEach((item) => {
    item.object_names.forEach((name) => {
      if (!knownObjectNames.has(name) && !FLOW_SUPPORTED_OBJECT_NAMES.includes(name as never)) {
        throw new Error(`unknown monitor object for capability ${item.id}: ${name}`);
      }
    });
  });

  const content = `${JSON.stringify({ version: 1, capabilities }, null, 2)}\n`;
  if (process.argv.includes('--check')) {
    if (!existsSync(outputPath) || readFileSync(outputPath, 'utf8') !== content) {
      throw new Error('monitor dashboard query capability manifest is stale');
    }
    process.stdout.write(`verified ${capabilities.length} monitor query capabilities\n`);
    return;
  }
  writeFileSync(outputPath, content, 'utf8');
  process.stdout.write(`generated ${capabilities.length} monitor query capabilities\n`);
};

void main();
