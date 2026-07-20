import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const buildRecordTab = fs.readFileSync(
  path.join(root, 'src/app/opspilot/components/wiki/BuildRecordTab.tsx'),
  'utf8'
);
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');

assert.match(wikiTypes, /export interface BuildAffectedPage/);
assert.match(wikiTypes, /affected_page_details\?: BuildAffectedPage\[\]/);
assert.match(buildRecordTab, /renderAffectedPages/);
assert.match(buildRecordTab, /detail\.affected_page_details/);
assert.match(buildRecordTab, /AFFECTED_PAGES_MAX_HEIGHT\s*=\s*'calc\(100vh - 400px\)'/);
assert.match(buildRecordTab, /maxHeight:\s*AFFECTED_PAGES_MAX_HEIGHT/);
assert.doesNotMatch(buildRecordTab, /max-h-\[320px\]/);
assert.doesNotMatch(buildRecordTab, /\(detail\.affected_pages \|\| \[\]\)\.join\(', '\)/);

console.log('wiki build record affected pages validation passed');
