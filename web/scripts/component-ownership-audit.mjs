import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE_EXTENSIONS = new Set(['.js', '.jsx', '.mjs', '.ts', '.tsx']);
const INVALID_CLASSIFICATIONS = new Set([
  'app-local',
  'story-only-review',
  'unused',
  'invalid-reverse-dependency',
]);

const normalize = (value) => value.split(path.sep).join('/');

const walkSourceFiles = async (directory) => {
  const files = [];
  let entries = [];
  try {
    entries = await fs.readdir(directory, { withFileTypes: true });
  } catch {
    return files;
  }
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await walkSourceFiles(fullPath));
    } else if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
};

const extractImports = (source) => {
  const imports = [];
  const patterns = [
    /\b(?:import|export)\s+(?:type\s+)?(?:[^'";]*?\s+from\s+)?['"]([^'"]+)['"]/g,
    /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g,
    /\brequire\(\s*['"]([^'"]+)['"]\s*\)/g,
  ];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) imports.push(match[1]);
  }
  return [...new Set(imports)];
};

const componentFromFile = (file, componentsRoot) => {
  const relative = path.relative(componentsRoot, file);
  if (relative.startsWith('..')) return null;
  return relative.split(path.sep)[0] || null;
};

const appFromFile = (file, appRoot) => {
  const relative = path.relative(appRoot, file);
  if (relative.startsWith('..')) return null;
  return relative.split(path.sep)[0] || null;
};

const componentFromImport = (specifier, importer, componentsRoot, knownComponents) => {
  if (specifier.startsWith('@/components/')) {
    const component = specifier.slice('@/components/'.length).split('/')[0];
    return knownComponents.has(component) ? component : null;
  }
  if (!specifier.startsWith('.')) return null;
  const resolved = path.resolve(path.dirname(importer), specifier);
  const component = componentFromFile(resolved, componentsRoot);
  return component && knownComponents.has(component) ? component : null;
};

const flattenAllowlist = (allowlist) => new Map(
  Object.entries(allowlist || {}).flatMap(([category, entries]) =>
    (entries || []).map((entry) => [entry.component, { ...entry, category }])
  )
);

const validateAllowlist = (allowlist) => {
  for (const [category, entries] of Object.entries(allowlist || {})) {
    if (!Array.isArray(entries)) throw new Error(`allowlist category ${category} must be an array`);
    for (const entry of entries) {
      for (const field of ['component', 'reason', 'contractStory']) {
        if (!entry?.[field]) throw new Error(`allowlist ${category} entry is missing ${field}`);
      }
    }
  }
};

export const auditComponentOwnership = async ({ rootDir, primitiveAllowlist = {} }) => {
  validateAllowlist(primitiveAllowlist);
  const sourceRoot = path.join(rootDir, 'src');
  const componentsRoot = path.join(sourceRoot, 'components');
  const appRoot = path.join(sourceRoot, 'app');
  const storiesRoot = path.join(sourceRoot, 'stories');
  const componentEntries = await fs.readdir(componentsRoot, { withFileTypes: true });
  const components = componentEntries.filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort();
  const knownComponents = new Set(components);
  const allowlist = flattenAllowlist(primitiveAllowlist);
  const directApps = new Map(components.map((name) => [name, new Set()]));
  const stories = new Map(components.map((name) => [name, new Set()]));
  const reverseApps = new Map(components.map((name) => [name, new Set()]));
  const componentEdges = new Map(components.map((name) => [name, new Set()]));

  const files = await walkSourceFiles(sourceRoot);
  for (const file of files) {
    const source = await fs.readFile(file, 'utf8');
    const imports = extractImports(source);
    const ownerComponent = componentFromFile(file, componentsRoot);
    const ownerApp = appFromFile(file, appRoot);
    const isStory = !path.relative(storiesRoot, file).startsWith('..');

    for (const specifier of imports) {
      const targetComponent = componentFromImport(specifier, file, componentsRoot, knownComponents);
      if (targetComponent) {
        if (ownerComponent && ownerComponent !== targetComponent) componentEdges.get(ownerComponent).add(targetComponent);
        if (ownerApp) directApps.get(targetComponent).add(ownerApp);
        if (isStory) stories.get(targetComponent).add(normalize(path.relative(storiesRoot, file)));
      }
      if (ownerComponent && specifier.startsWith('@/app/')) {
        const targetApp = specifier.slice('@/app/'.length).split('/')[0];
        if (targetApp) reverseApps.get(ownerComponent).add(targetApp);
      }
    }
  }

  const transitiveApps = new Map([...directApps].map(([name, apps]) => [name, new Set(apps)]));
  const transitiveStories = new Map([...stories].map(([name, files]) => [name, new Set(files)]));
  let changed = true;
  while (changed) {
    changed = false;
    for (const [consumer, dependencies] of componentEdges) {
      for (const dependency of dependencies) {
        for (const app of transitiveApps.get(consumer)) {
          if (!transitiveApps.get(dependency).has(app)) {
            transitiveApps.get(dependency).add(app);
            changed = true;
          }
        }
        for (const story of transitiveStories.get(consumer)) {
          if (!transitiveStories.get(dependency).has(story)) {
            transitiveStories.get(dependency).add(story);
            changed = true;
          }
        }
      }
    }
  }

  return components.map((component) => {
    const direct = [...directApps.get(component)].sort();
    const transitive = [...transitiveApps.get(component)].sort();
    const storyFiles = [...transitiveStories.get(component)].sort();
    const reverse = [...reverseApps.get(component)].sort();
    let classification;
    let reason;
    if (reverse.length) {
      classification = 'invalid-reverse-dependency';
      reason = `imports app-owned modules from ${reverse.join(', ')}`;
    } else if (transitive.length >= 2) {
      classification = 'shared-cross-app';
      reason = `consumed transitively by ${transitive.length} apps`;
    } else if (allowlist.has(component)) {
      classification = 'shared-primitive';
      reason = `primitive allowlist: ${allowlist.get(component).reason}`;
    } else if (transitive.length === 1) {
      classification = 'app-local';
      reason = `consumed by only ${transitive[0]}`;
    } else if (storyFiles.length) {
      classification = 'story-only-review';
      reason = 'consumed only by Storybook stories';
    } else {
      classification = 'unused';
      reason = 'no app or Storybook consumers';
    }
    return {
      component,
      directApps: direct,
      transitiveApps: transitive,
      stories: storyFiles,
      reverseAppImports: reverse,
      classification,
      reason,
    };
  });
};

const runCli = async () => {
  const currentFile = fileURLToPath(import.meta.url);
  if (process.argv[1] !== currentFile) return;
  const args = process.argv.slice(2);
  const webRoot = path.resolve(path.dirname(currentFile), '..');
  const allowlistPath = path.join(webRoot, 'component-ownership.allowlist.json');
  const manifestPath = path.join(webRoot, 'component-ownership.manifest.json');
  const primitiveAllowlist = JSON.parse(await fs.readFile(allowlistPath, 'utf8'));
  let records = await auditComponentOwnership({ rootDir: webRoot, primitiveAllowlist });
  const classificationArg = args.find((arg) => arg.startsWith('--classification='));
  const domainArg = args.find((arg) => arg.startsWith('--domain='));
  const formatArg = args.find((arg) => arg.startsWith('--format='));
  if (classificationArg) {
    const accepted = new Set(classificationArg.split('=')[1].split(','));
    records = records.filter((record) => accepted.has(record.classification));
  }
  if (domainArg) {
    const domains = domainArg.split('=')[1].split(',');
    records = records.filter((record) => domains.some((domain) => record.component === domain || record.component.startsWith(`${domain}-`)));
  }
  if (args.includes('--check')) {
    const invalid = records.filter((record) => INVALID_CLASSIFICATIONS.has(record.classification));
    if (invalid.length) {
      console.error(`component ownership check failed: ${invalid.length} unresolved records`);
      process.exitCode = 1;
    } else {
      console.log(`component ownership check passed: ${records.length} records`);
    }
    return;
  }
  if (formatArg?.endsWith('paths')) {
    for (const record of records) console.log(`src/components/${record.component}`);
    return;
  }
  await fs.writeFile(manifestPath, `${JSON.stringify(records, null, 2)}\n`);
  const summary = Object.groupBy(records, (record) => record.classification);
  console.log(`wrote ${records.length} records to ${path.basename(manifestPath)}`);
  for (const [classification, items] of Object.entries(summary)) console.log(`${classification}: ${items.length}`);
};

await runCli();
