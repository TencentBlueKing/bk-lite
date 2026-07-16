import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { auditComponentOwnership } from './component-ownership-audit.mjs';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.join(currentDir, 'fixtures/component-ownership');

const sourceLikeDirectoryLink = path.join(rootDir, 'src/app/source-link.ts');
await fs.symlink(path.join(rootDir, 'src/app/app-a'), sourceLikeDirectoryLink);
let records;
try {
  records = await auditComponentOwnership({
    rootDir,
    primitiveAllowlist: {
      interaction: [{
        component: 'primitive-control',
        reason: '通用交互测试原语',
        contractStory: 'primitive-control.stories.tsx',
      }],
    },
  });
} finally {
  await fs.unlink(sourceLikeDirectoryLink);
}

const byName = new Map(records.map((record) => [record.component, record]));

assert.deepEqual(byName.get('cross-card'), {
  component: 'cross-card',
  directApps: ['app-a', 'app-b'],
  transitiveApps: ['app-a', 'app-b'],
  stories: [],
  reverseAppImports: [],
  classification: 'shared-cross-app',
  reason: 'consumed transitively by 2 apps',
});

assert.equal(byName.get('single-panel').classification, 'app-local');
assert.deepEqual(byName.get('single-panel').transitiveApps, ['app-a']);

assert.equal(byName.get('story-only').classification, 'story-only-review');
assert.deepEqual(byName.get('story-only').stories, ['story-only.stories.tsx']);

assert.equal(byName.get('leaf-card').classification, 'shared-cross-app');
assert.deepEqual(byName.get('leaf-card').directApps, []);
assert.deepEqual(byName.get('leaf-card').transitiveApps, ['app-a', 'app-b']);

assert.equal(byName.get('reverse-card').classification, 'invalid-reverse-dependency');
assert.deepEqual(byName.get('reverse-card').reverseAppImports, ['app-a']);

assert.equal(byName.get('primitive-control').classification, 'shared-primitive');
assert.match(byName.get('primitive-control').reason, /allowlist/);

console.log('component ownership audit fixture tests passed');
