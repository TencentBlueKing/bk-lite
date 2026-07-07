import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const wikiFormat = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/wikiFormat.ts'), 'utf8');
const pageTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/PageTab.tsx'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

assert.match(wikiFormat, /indexing:\s*'wiki\.indexStatusIndexing'/);
assert.match(pageTab, /indexing:\s*'blue'/);
assert.equal(zh.wiki.indexStatusIndexing, '索引中');
assert.equal(en.wiki.indexStatusIndexing, 'Indexing');

console.log('wiki page index running status validation passed');
