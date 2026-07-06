import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const wikiModifyModal = fs.readFileSync(
  path.join(root, 'src/app/opspilot/components/wiki/WikiModifyModal.tsx'),
  'utf8'
);

assert.match(wikiModifyModal, /<Modal[\s\S]*maskClosable=\{false\}[\s\S]*>/);
assert.match(wikiModifyModal, /onCancel=\{onCancel\}/);

console.log('wiki modal mask close behavior OK');
