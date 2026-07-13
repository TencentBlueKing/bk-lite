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
  'resolutionResult',
  'suggestedQueries',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

const expectedCheckTypes: Record<string, string> = {
  ambiguous_link: 'checkAmbiguousLink',
  conflict: 'checkConflict',
  duplicate: 'checkDuplicate',
  stale: 'checkStale',
  orphan: 'checkOrphan',
  broken_relation: 'checkBrokenRelation',
  no_source: 'checkNoSource',
  all_sources_invalid: 'checkAllSourcesInvalid',
  low_confidence: 'checkLowConfidence',
  cannot_merge: 'checkCannotMerge',
  bridge_node: 'checkBridgeNode',
  sparse_community: 'checkSparseCommunity',
  cross_community_edge: 'checkCrossCommunityEdge',
  surprise_link: 'checkSurpriseLink',
  schema_violation: 'checkSchemaViolation',
  schema_changed: 'checkSchemaChanged',
  missing: 'checkMissing',
  material_update: 'checkMaterialUpdate',
  source_invalid: 'checkSourceInvalid',
  qa_answer_candidate: 'checkQaAnswerCandidate',
};

for (const [checkType, localeKey] of Object.entries(expectedCheckTypes)) {
  assert.ok(zh.wiki[localeKey], `missing zh wiki.${localeKey}`);
  assert.ok(en.wiki[localeKey], `missing en wiki.${localeKey}`);
  assert.match(checkTab, new RegExp(`${checkType}:\\s*'wiki\\.${localeKey}'`));
}
assert.match(checkTab, /const CHECK_STATUS_KEY/);
assert.match(checkTab, /open:\s*'wiki\.checkStatusOpen'/);
assert.match(checkTab, /resolved:\s*'wiki\.checkStatusResolved'/);
assert.match(checkTab, /dismissed:\s*'wiki\.checkStatusDismissed'/);
assert.doesNotMatch(checkTab, />\{s\}<\/Tag>/);
assert.match(checkTab, /const \[statusFilter,\s*setStatusFilter\] = useState\('open'\)/);
assert.match(checkTab, /fetchCheckItems\(kbId,\s*\{[\s\S]*status:\s*statusFilter \|\| undefined/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/\$\{id\}\/accept\/`, \{\}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/\$\{id\}\/reject\/`, \{\}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/batch_accept\/`, \{ ids \}\)/);
assert.match(wikiApi, /post\(`\$\{BASE\}\/check_item\/batch_reject\/`, \{ ids \}\)/);
assert.match(checkTab, /t\('wiki\.resolutionResult'\)/);
assert.doesNotMatch(checkTab, /mergeDuplicateCheck|resolveCheck|batchResolveChecks/);
assert.doesNotMatch(checkTab, /t\('wiki\.(mergeDuplicate|markResolved|batchResolve)'\)/);
assert.doesNotMatch(wikiApi, /check_item\/\$\{id\}\/(merge|resolve)\//);
assert.doesNotMatch(wikiApi, /check_item\/batch_resolve\//);
assert.match(checkTab, /suggested_queries/);
assert.match(checkTab, /t\('wiki\.suggestedQueries'\)/);

console.log('wiki check review i18n/default-status validation passed');
