import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const scriptsRoot = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptsRoot, '..');
const buildConfigPath = path.join(webRoot, 'tsconfig.build.json');
const nextConfig = (await import('../next.config.mjs')).default;

assert.equal(nextConfig.typescript?.tsconfigPath, 'tsconfig.build.json');

const loadedConfig = ts.readConfigFile(buildConfigPath, ts.sys.readFile);
assert.equal(
  loadedConfig.error,
  undefined,
  loadedConfig.error
    ? ts.flattenDiagnosticMessageText(loadedConfig.error.messageText, '\n')
    : undefined
);

const parsedConfig = ts.parseJsonConfigFileContent(
  loadedConfig.config,
  ts.sys,
  webRoot,
  undefined,
  buildConfigPath
);
assert.deepEqual(parsedConfig.errors, []);

const relativeFiles = new Set(
  parsedConfig.fileNames.map(fileName => path.relative(webRoot, fileName))
);

assert.ok(relativeFiles.has('src/context/locale.tsx'));
assert.ok(!relativeFiles.has('src/stories/ai-editor.stories.tsx'));
assert.ok(
  !relativeFiles.has(
    'src/app/monitor/dashboards/shared/utils/__tests__/format.test.ts'
  )
);
assert.ok(!relativeFiles.has('e2e/app-shell.spec.ts'));

assert.ok(loadedConfig.config.include.includes('.next/types/**/*.ts'));
assert.ok(!loadedConfig.config.include.includes('.next/dev/types/**/*.ts'));

console.log('production type-check scope excludes stories and tests');
