import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const previewSource = readFileSync('.storybook/preview.tsx', 'utf8');
const mainSource = readFileSync('.storybook/main.ts', 'utf8');

assert.match(
  previewSource,
  /import AuthProvider from ['"]\.\/mocks\/auth['"];?/,
  'Storybook must mount its mock AuthProvider directly so production session recovery cannot run',
);
assert.doesNotMatch(
  previewSource,
  /import AuthProvider from ['"]@\/context\/auth['"];?/,
  'Storybook preview must not rely on webpack aliases to isolate the root AuthProvider',
);
assert.ok(
  mainSource.includes("name: '@/context/auth'") && mainSource.includes('onlyModule: true'),
  'Storybook stories must resolve application auth hooks through the exact mock alias',
);
assert.ok(
  mainSource.includes('StorybookExactMockPlugin') && mainSource.includes('normalModuleFactory'),
  'Storybook must replace mock imports before Next.js tsconfig path resolution can bypass webpack aliases',
);

console.log('storybook auth isolation contract ok');
