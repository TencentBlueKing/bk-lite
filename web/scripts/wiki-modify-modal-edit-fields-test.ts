import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const modal = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/WikiModifyModal.tsx'), 'utf8');

assert.match(modal, /const isEditing = Boolean\(initialValues\?\.id\);/);
assert.match(modal, /const submitValues = \{ \.\.\.values \};/);

for (const field of ['template_key', 'purpose_md', 'schema_md']) {
  assert.match(modal, new RegExp(`delete submitValues\\.${field};`));
}

assert.match(modal, /!\s*isEditing && \(/);
assert.match(modal, /label=\{t\('wiki\.template'\)\}[\s\S]*name="template_key"/);
assert.match(modal, /label=\{t\('wiki\.purpose'\)\}[\s\S]*name="purpose_md"/);
assert.match(modal, /label=\{t\('wiki\.schema'\)\}[\s\S]*name="schema_md"/);

console.log('wiki modify modal edit-only fields hidden validation passed');
