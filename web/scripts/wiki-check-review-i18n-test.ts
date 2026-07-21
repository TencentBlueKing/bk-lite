import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';


// 仅验证生产组件/API/i18n 的接线契约；状态与映射行为由 wiki-decision-center-test.ts 执行。
const root = process.cwd();
const checkTab = fs.readFileSync(path.join(root, 'src/app/opspilot/components/wiki/CheckTab.tsx'), 'utf8');
const decisionCenterPath = path.join(root, 'src/app/opspilot/components/wiki/WikiDecisionCenter.tsx');
const decisionModelPath = path.join(root, 'src/app/opspilot/components/wiki/wikiDecisionModel.ts');
const decisionStoryPath = path.join(root, 'src/stories/wiki-decision-center.stories.tsx');
assert.ok(fs.existsSync(decisionCenterPath), 'production WikiDecisionCenter should exist');
assert.ok(fs.existsSync(decisionModelPath), 'decision view model should exist');
assert.ok(fs.existsSync(decisionStoryPath), 'WikiDecisionCenter Storybook story should exist');
const decisionCenter = fs.readFileSync(decisionCenterPath, 'utf8');
const decisionStory = fs.readFileSync(decisionStoryPath, 'utf8');
const wikiApi = fs.readFileSync(path.join(root, 'src/app/opspilot/api/wiki.ts'), 'utf8');
const wikiTypes = fs.readFileSync(path.join(root, 'src/app/opspilot/types/wiki.ts'), 'utf8');
const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/opspilot/locales/en.json'), 'utf8'));

for (const key of [
  'decisionCenterTitle',
  'decisionCenterSubtitle',
  'decisionPending',
  'decisionProcessed',
  'decisionAutoMaintenance',
  'decisionKnowledgeConflict',
  'decisionPageIdentity',
  'decisionCurrentKnowledge',
  'decisionNewKnowledge',
  'decisionKeepCurrent',
  'decisionUseNew',
  'decisionEditAccept',
  'decisionKeepSeparate',
  'decisionMerge',
  'decisionWhyNeeded',
  'decisionTriggerSource',
  'decisionImpactScope',
  'decisionRecoverability',
  'decisionRuleActive',
  'decisionRuleRevoked',
  'decisionReplayCount',
  'decisionOperator',
  'decisionProcessedAt',
  'decisionSourceCount',
  'decisionRelationCount',
  'decisionRevokeRule',
  'decisionRevokedReason',
  'decisionRevokedReasonMaterialDeleted',
  'decisionRevokedReasonPageArchivedByRebuild',
  'decisionRevokedReasonPageIdentityChanged',
  'decisionRevokedReasonPageDeleted',
  'decisionRevokedReasonManual',
  'decisionOutdated',
  'decisionContextOutdated',
  'decisionRefresh',
  'decisionEmptyPending',
  'decisionEmptyProcessed',
]) {
  assert.ok(zh.wiki[key], `missing zh wiki.${key}`);
  assert.ok(en.wiki[key], `missing en wiki.${key}`);
}

assert.equal(zh.wiki.decisionAutoMaintenance, '结构维护自动执行');
assert.equal(en.wiki.decisionAutoMaintenance, 'Structural maintenance runs automatically');
assert.match(wikiTypes, /export type CheckDecisionAction\s*=/);
assert.match(wikiTypes, /export interface WikiDecisionRule/);
assert.match(wikiTypes, /decision_type\?:\s*WikiDecisionType/);
assert.match(wikiTypes, /decision_rule\?:\s*WikiDecisionRule/);
assert.match(wikiTypes, /decision_operator\?:\s*string/);
assert.match(wikiTypes, /decision_processed_at\?:\s*string/);
assert.match(wikiApi, /const fetchDecisionItems\s*=/);
assert.match(wikiApi, /decision_only:\s*true/);
assert.match(wikiApi, /const decideCheck[\s\S]*CheckDecisionRequest[\s\S]*CheckDecisionResponse/);
assert.match(wikiApi, /const revokeDecisionRule[\s\S]*RevokeDecisionRuleRequest/);
assert.match(wikiApi, /check_item\/\$\{id\}\/revoke_rule\//);

assert.match(checkTab, /<WikiDecisionCenter/);
assert.match(checkTab, /fetchDecisionItems/);
assert.match(checkTab, /shouldRefreshDecisionListAfterError/);
assert.match(
  checkTab,
  /if \(shouldRefresh\) \{\s*const refreshed = await load\(\);\s*if \(refreshed\) setOutdatedItemId\(null\);\s*\}/
);
assert.match(checkTab, /key=\{`\$\{scopeKey\}:\$\{outdatedItemId/);
assert.doesNotMatch(checkTab, /acceptCheck|rejectCheck|batchAcceptChecks|batchRejectChecks/);
assert.match(checkTab, /throw requestError/);
assert.doesNotMatch(checkTab, /manual_revoke/);

assert.equal((decisionCenter.match(/<SwapOutlined/g) || []).length, 1, 'comparison uses one shared swap icon');
assert.doesNotMatch(decisionCenter, /MoreOutlined|more handling/i);
assert.doesNotMatch(decisionCenter, /<Select|mergeTarget|targetPage/);
assert.doesNotMatch(decisionCenter, /CheckCircleOutlined/);
assert.match(decisionCenter, /resolveDecisionRevokedReason/);
assert.match(decisionCenter, /filterDecisionItems/);
assert.match(decisionCenter, /filterDecisionItems\(items\)/);
assert.match(decisionCenter, /wiki\.decisionCurrentKnowledge/);
assert.match(decisionCenter, /wiki\.decisionNewKnowledge/);
assert.match(decisionCenter, /wiki\.decisionOperator/);
assert.match(decisionCenter, /wiki\.decisionProcessedAt/);
assert.match(decisionCenter, /wiki\.decisionSourceCount/);
assert.match(decisionCenter, /wiki\.decisionRelationCount/);
assert.doesNotMatch(
  decisionCenter,
  /unknownSource/,
  'empty source labels should be omitted instead of rendered as an alarming placeholder tag'
);
assert.doesNotMatch(decisionCenter, /DECISION_THEME/, 'decision center should use the shared web theme tokens');
assert.doesNotMatch(decisionCenter, /#[\da-fA-F]{3,8}/, 'decision center should not define a private hex color palette');
assert.doesNotMatch(decisionCenter, /min-h-\[700px\]/, 'decision center should not force a fixed minimum height');
assert.match(
  decisionCenter,
  /<main className="[^"]*min-h-0[^"]*overflow-hidden[^"]*lg:h-full/,
  'decision center should fill the available parent height without growing past it'
);
assert.match(
  decisionCenter,
  /className="min-h-0 flex-1 overflow-y-auto"/,
  'decision list should scroll independently when its content exceeds the available height'
);
assert.match(
  decisionCenter,
  /<aside className="[^"]*bg-\[var\(--color-bg\)\]/,
  'decision list should use the shared page background instead of a tinted panel background'
);

assert.match(decisionStory, /import WikiDecisionCenter from '@\/app\/opspilot\/components\/wiki\/WikiDecisionCenter'/);
assert.doesNotMatch(decisionStory, /#[\da-fA-F]{3,8}/, 'decision center story should use the shared web theme tokens');
assert.match(decisionStory, /current_knowledge:/);
assert.match(decisionStory, /new_knowledge:/);
assert.match(decisionStory, /target_identity:/);
assert.match(decisionStory, /revoked_reason: 'page_identity_changed'/);
for (const story of ['KnowledgeConflict', 'PageIdentityMerge', 'AutomaticReplay', 'RevokedRule']) {
  assert.match(decisionStory, new RegExp(`export const ${story}`));
}

console.log('wiki decision center contract and i18n validation passed');
