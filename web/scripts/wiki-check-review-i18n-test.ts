import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const checkTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/CheckTab.tsx'), 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of [
  'checkAmbiguousLink',
  'checkStatusOpen',
  'checkStatusResolved',
  'checkStatusDismissed',
  'mergeDuplicate',
  'mergeDuplicateConfirm',
  'markResolved',
  'markResolvedConfirm',
  'resolutionResult',
  'batchResolve',
  'batchResolveConfirm',
  'suggestedQueries',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.match(checkTab, /ambiguous_link:\s*'wiki\.checkAmbiguousLink'/);
assert.match(checkTab, /const CHECK_STATUS_KEY/);
assert.match(checkTab, /open:\s*'wiki\.checkStatusOpen'/);
assert.match(checkTab, /resolved:\s*'wiki\.checkStatusResolved'/);
assert.match(checkTab, /dismissed:\s*'wiki\.checkStatusDismissed'/);
assert.doesNotMatch(checkTab, />\{s\}<\/Tag>/);
assert.match(checkTab, /const \[statusFilter,\s*setStatusFilter\] = useState\('open'\)/);
assert.match(checkTab, /fetchCheckItems\(kbId,\s*\{[\s\S]*status:\s*statusFilter \|\| undefined/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/\$\{id\}\/accept\/`, \{\}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/\$\{id\}\/reject\/`, \{\}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/\$\{id\}\/merge\/`, \{\}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/\$\{id\}\/resolve\/`, \{ note \}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/batch_accept\/`, \{ ids \}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/batch_reject\/`, \{ ids \}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/batch_resolve\/`, \{ ids, note \}\)/);
assert.match(checkTab, /mergeDuplicateCheck/);
assert.match(checkTab, /resolveCheck/);
assert.match(checkTab, /batchResolveChecks/);
assert.match(checkTab, /const canMergeDuplicate = \(r: CheckItem\) =>/);
assert.match(checkTab, /t\('wiki\.mergeDuplicate'\)/);
assert.match(checkTab, /t\('wiki\.mergeDuplicateConfirm'\)/);
assert.match(checkTab, /t\('wiki\.markResolved'\)/);
assert.match(checkTab, /t\('wiki\.markResolvedConfirm'\)/);
assert.match(checkTab, /t\('wiki\.resolutionResult'\)/);
assert.match(checkTab, /t\('wiki\.batchResolve'\)/);
assert.match(checkTab, /t\('wiki\.batchResolveConfirm'\)/);
assert.match(checkTab, /suggested_queries/);
assert.match(checkTab, /t\('wiki\.suggestedQueries'\)/);

console.log('wiki check review i18n/default-status validation passed');
