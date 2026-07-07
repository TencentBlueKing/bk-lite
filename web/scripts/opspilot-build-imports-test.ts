import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const root = path.resolve(__dirname, '..');
const chatPath = path.join(root, 'src/app/opspilot/components/custom-chat-sse/index.tsx');
const chatSource = readFileSync(chatPath, 'utf8');

const removedImports = [
  '../custom-chat/knowledgeBase',
  '../custom-chat/annotationModal',
  '../knowledge/knowledgeGraphView',
  './hooks/useReferenceHandler',
];

for (const importPath of removedImports) {
  assert.equal(
    chatSource.includes(importPath),
    false,
    `custom-chat-sse still imports removed module: ${importPath}`
  );
}

const opsAnalysisScreenCanvas = path.join(
  root,
  'src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx'
);
const rootPackage = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8'));

if (existsSync(opsAnalysisScreenCanvas)) {
  const screenCanvasSource = readFileSync(opsAnalysisScreenCanvas, 'utf8');
  if (screenCanvasSource.includes('react-rnd')) {
    assert.ok(
      rootPackage.dependencies?.['react-rnd'] || rootPackage.devDependencies?.['react-rnd'],
      'root web package.json must declare react-rnd because Next builds from the web package root'
    );
  }
}

console.log('opspilot build import validation passed');
