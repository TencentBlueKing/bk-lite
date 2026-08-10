import assert from 'node:assert/strict';
import * as decisionModel from '../src/app/opspilot/components/wiki/wikiDecisionModel';
import {
  buildDecisionViewModel,
  buildDecisionLoadPlan,
  createLatestRequestGuard,
  getDecisionInteractionState,
  getDecisionActions,
  getDecisionKind,
  isDecisionRuleRevocable,
  shouldRefreshDecisionListAfterError,
} from '../src/app/opspilot/components/wiki/wikiDecisionModel';
import type { CheckItem } from '../src/app/opspilot/types/wiki';

const knowledgeConflict: CheckItem = {
  id: 11,
  knowledge_base: 7,
  check_type: 'material_update',
  decision_type: 'knowledge_conflict',
  status: 'open',
  decision_key: 'a'.repeat(64),
  related_pages: [
    {
      id: 101,
      title: 'Kubernetes 节点磁盘告警阈值',
      page_type: 'rule',
      body: '磁盘使用率达到 80% 时告警。',
      version_label: 'v12',
    },
  ],
  current_knowledge: {
    id: 101,
    title: 'Kubernetes 节点磁盘告警阈值',
    page_type: 'rule',
    body: 'API 当前知识：磁盘使用率达到 80% 时告警。',
    source_label: 'API 当前资料',
  },
  new_knowledge: {
    id: 101,
    title: 'Kubernetes 节点磁盘告警阈值',
    page_type: 'rule',
    body: 'API 新知识：磁盘使用率达到 85% 时告警。',
    source_label: 'API 新资料',
  },
  candidate: { id: 202, body: '磁盘使用率达到 85% 时告警。' },
  candidate_version: 202,
  decision_context: {
    locked_current_version_id: 201,
    decision_type: 'knowledge_conflict',
    subject_key: 'page::rule::kubernetes-node-disk-alert-threshold',
    schema_fingerprint: 'schema-v1',
    participants: [
      { material_id: 501, material_version_id: 601, content_hash: 'current-hash' },
      { material_id: 502, material_version_id: 602, content_hash: 'incoming-hash' },
    ],
    incoming: {
      material_id: 502,
      material_version_id: 602,
      content_hash: 'incoming-hash',
    },
    current_body_hash: 'current-body-hash',
    candidate_body_hash: 'candidate-body-hash',
    candidate_version_id: 202,
    page_identity: {
      page_id: 101,
      title: 'Kubernetes 节点磁盘告警阈值',
      page_type: 'rule',
    },
    summary: '阈值从 80% 调整为 85%',
    current_source_label: 'Kubernetes 运维手册',
    incoming_source_label: 'SRE 运行标准',
  },
};

const incompleteKnowledgeConflict: CheckItem = {
  ...knowledgeConflict,
  id: 14,
  decision_key: '',
  decision_context: { summary: 'legacy incomplete context' },
};

const pageIdentity: CheckItem = {
  id: 12,
  knowledge_base: 7,
  check_type: 'duplicate',
  decision_type: 'page_identity',
  status: 'open',
  related_pages: [
    { id: 103, title: 'CMDB', page_type: 'entity', body: '配置管理数据库。' },
    { id: 102, title: '配置平台', page_type: 'entity', body: '统一管理资产。' },
  ],
  decision_context: {
    page_identities: [
      { page_id: 103, title: 'CMDB', page_type: 'entity' },
      { page_id: 102, title: '配置平台', page_type: 'entity' },
    ],
    target_identity: { page_id: 102, title: '配置平台', page_type: 'entity' },
  },
};

const frozenPageIdentity: CheckItem = {
  ...pageIdentity,
  current_knowledge: {
    id: 102,
    title: '配置平台',
    page_type: 'entity',
    body: '统一管理资产。',
  },
  new_knowledge: {
    id: 103,
    title: 'CMDB',
    page_type: 'entity',
    body: '配置管理数据库。',
  },
};

const maintenanceDiagnostic: CheckItem = {
  id: 13,
  knowledge_base: 7,
  check_type: 'orphan',
  // 后端异常或旧数据即使误带 decision_type，也不能升级为人工合并决策。
  decision_type: 'page_identity',
  status: 'open',
  related_pages: [
    {
      id: 104,
      title: '孤立知识页',
      page_type: 'guide',
      body: '没有来源的维护诊断。',
    },
  ],
};

assert.equal(getDecisionKind(knowledgeConflict), 'knowledge_conflict');
assert.deepEqual(getDecisionActions(knowledgeConflict), [
  'keep_current',
  'edit_accept',
  'use_new',
]);
assert.equal(getDecisionKind(incompleteKnowledgeConflict), null);
assert.deepEqual(getDecisionActions(incompleteKnowledgeConflict), []);
assert.equal(buildDecisionViewModel(incompleteKnowledgeConflict), null);
assert.equal(getDecisionInteractionState(incompleteKnowledgeConflict).canDecide, false);

const conflictView = buildDecisionViewModel(knowledgeConflict);
assert.equal(conflictView.current.title, 'Kubernetes 节点磁盘告警阈值');
assert.equal(
  conflictView.current.body,
  'API 当前知识：磁盘使用率达到 80% 时告警。',
);
assert.equal(conflictView.current.sourceLabel, 'API 当前资料');
assert.equal(
  conflictView.incoming.body,
  'API 新知识：磁盘使用率达到 85% 时告警。',
);
assert.equal(conflictView.incoming.sourceLabel, 'API 新资料');

assert.equal(getDecisionKind(pageIdentity), null);
assert.deepEqual(getDecisionActions(pageIdentity), []);
const legacyMergeView = buildDecisionViewModel(pageIdentity);
assert.equal(legacyMergeView, null);
const legacyInteraction = getDecisionInteractionState(pageIdentity, null, null);
assert.equal(legacyInteraction.requiresContextRefresh, false);
assert.equal(legacyInteraction.canDecide, false);

assert.equal(getDecisionKind(frozenPageIdentity), 'page_identity');
assert.deepEqual(getDecisionActions(frozenPageIdentity), [
  'keep_separate',
  'merge',
]);
const mergeView = buildDecisionViewModel(frozenPageIdentity);
assert.equal(mergeView.current.title, '配置平台');
assert.equal(mergeView.incoming.title, 'CMDB');
assert.equal(mergeView.current.id, 102);
assert.equal(mergeView.incoming.id, 103);
assert.equal(mergeView.identitySource, 'frozen');
const readyInteraction = getDecisionInteractionState(
  frozenPageIdentity,
  null,
  null,
);
assert.equal(readyInteraction.canDecide, true);

assert.equal(
  getDecisionKind(maintenanceDiagnostic),
  null,
  'maintenance checks must fail closed instead of becoming page identity decisions',
);
assert.deepEqual(getDecisionActions(maintenanceDiagnostic), []);
assert.equal(buildDecisionViewModel(maintenanceDiagnostic), null);
assert.equal(
  getDecisionInteractionState(maintenanceDiagnostic, null, null).canDecide,
  false,
);

const failClosedModel = decisionModel as unknown as {
  filterDecisionItems?: (items: CheckItem[]) => CheckItem[];
};
assert.equal(
  typeof failClosedModel.filterDecisionItems,
  'function',
  'decision responses must be filtered again before rendering',
);
assert.deepEqual(
  failClosedModel.filterDecisionItems!([
    maintenanceDiagnostic,
    knowledgeConflict,
    frozenPageIdentity,
  ]).map((item) => item.id),
  [knowledgeConflict.id, frozenPageIdentity.id],
);

const submittingInteraction = getDecisionInteractionState(
  frozenPageIdentity,
  { checkId: frozenPageIdentity.id, action: 'merge' },
  null,
);
assert.equal(submittingInteraction.isSubmitting, true);
assert.equal(submittingInteraction.canDecide, false);
assert.equal(submittingInteraction.canEditSubmit, false);

const outdatedInteraction = getDecisionInteractionState(
  knowledgeConflict,
  null,
  knowledgeConflict.id,
);
assert.equal(outdatedInteraction.isOutdated, true);
assert.equal(outdatedInteraction.canDecide, false);
assert.equal(outdatedInteraction.canEditSubmit, false);
assert.equal(
  shouldRefreshDecisionListAfterError(
    '审批上下文已失效，系统已自动关闭该待决策项',
  ),
  true,
  '自动关闭的 409 决策必须触发列表刷新',
);
assert.equal(shouldRefreshDecisionListAfterError('decision is stale'), true);
assert.equal(
  shouldRefreshDecisionListAfterError('请求失败，请稍后重试'),
  false,
);

const loadPlan = buildDecisionLoadPlan('pending', 3, 20);
assert.deepEqual(loadPlan.primary, { view: 'pending', page: 3, page_size: 20 });
assert.deepEqual(loadPlan.companion, {
  view: 'processed',
  page: 1,
  page_size: 1,
});

type DecisionScopeState = {
  items: CheckItem[];
  total: number;
  counts: { pending: number; processed: number };
  activeId: number | null;
  error: string;
  loadedScopeKey: string;
};

const scopeModel = decisionModel as unknown as {
  createDecisionScopeState?: () => DecisionScopeState;
  decisionScopeReducer?: (
    state: DecisionScopeState,
    action: Record<string, unknown>,
  ) => DecisionScopeState;
  getVisibleDecisionScopeState?: (
    state: DecisionScopeState,
    scopeKey: string,
  ) => DecisionScopeState;
};
assert.equal(
  typeof scopeModel.createDecisionScopeState,
  'function',
  'decision scope must expose an executable empty-state factory',
);
assert.equal(
  typeof scopeModel.decisionScopeReducer,
  'function',
  'decision scope must expose an executable reducer',
);
assert.equal(
  typeof scopeModel.getVisibleDecisionScopeState,
  'function',
  'decision scope must hide a previous knowledge base before effects run',
);

const createDecisionScopeState = scopeModel.createDecisionScopeState!;
const decisionScopeReducer = scopeModel.decisionScopeReducer!;
const getVisibleDecisionScopeState = scopeModel.getVisibleDecisionScopeState!;
const loadedScope = decisionScopeReducer(createDecisionScopeState(), {
  type: 'load_succeeded',
  scopeKey: '7:pending:1:20',
  items: [knowledgeConflict],
  total: 9,
  counts: { pending: 9, processed: 4 },
});
const resetForAnotherKb = decisionScopeReducer(loadedScope, { type: 'reset' });
assert.deepEqual(resetForAnotherKb.items, []);
assert.equal(resetForAnotherKb.activeId, null);
assert.equal(resetForAnotherKb.total, 0);
assert.deepEqual(resetForAnotherKb.counts, { pending: 0, processed: 0 });
assert.equal(resetForAnotherKb.error, '');
assert.equal(resetForAnotherKb.loadedScopeKey, '');

const failedNewScope = decisionScopeReducer(loadedScope, {
  scopeKey: '8:pending:1:20',
  type: 'load_failed',
  error: 'new knowledge base failed to load',
});
assert.deepEqual(failedNewScope.items, []);
assert.equal(failedNewScope.activeId, null);
assert.equal(failedNewScope.total, 0);
assert.deepEqual(failedNewScope.counts, { pending: 0, processed: 0 });
assert.equal(failedNewScope.error, 'new knowledge base failed to load');
assert.equal(failedNewScope.loadedScopeKey, '8:pending:1:20');

const hiddenPreviousKb = getVisibleDecisionScopeState(
  loadedScope,
  '8:pending:1:20',
);
assert.deepEqual(hiddenPreviousKb.items, []);
assert.equal(hiddenPreviousKb.activeId, null);
assert.deepEqual(hiddenPreviousKb.counts, { pending: 0, processed: 0 });
assert.equal(hiddenPreviousKb.error, '');
const visibleFailedScope = getVisibleDecisionScopeState(
  failedNewScope,
  '8:pending:1:20',
);
assert.deepEqual(visibleFailedScope.counts, { pending: 0, processed: 0 });
assert.equal(visibleFailedScope.error, 'new knowledge base failed to load');
const decisionFailure = decisionScopeReducer(loadedScope, {
  type: 'set_error',
  error: 'decision is outdated',
});
assert.deepEqual(decisionFailure.items, [knowledgeConflict]);
assert.deepEqual(decisionFailure.counts, { pending: 9, processed: 4 });
assert.equal(decisionFailure.error, 'decision is outdated');

const requestGuard = createLatestRequestGuard();
const olderRequest = requestGuard.begin();
const latestRequest = requestGuard.begin();
let committedScope = 'none';
assert.equal(
  requestGuard.commitIfCurrent(olderRequest, () => {
    committedScope = 'old';
  }),
  false,
);
assert.equal(committedScope, 'none');
assert.equal(
  requestGuard.commitIfCurrent(latestRequest, () => {
    committedScope = 'new';
  }),
  true,
);
assert.equal(committedScope, 'new');
requestGuard.invalidate();
assert.equal(requestGuard.isCurrent(latestRequest), false);

assert.equal(
  isDecisionRuleRevocable({
    id: 1,
    status: 'active',
    action: 'keep_current',
    match_snapshot: {},
    result_snapshot: {},
    replay_count: 2,
  }),
  true,
);
assert.equal(
  isDecisionRuleRevocable({
    id: 1,
    status: 'revoked',
    action: 'keep_current',
    match_snapshot: {},
    result_snapshot: {},
    replay_count: 2,
  }),
  false,
);

type RevokedReasonPresentation = {
  translationKey: string | null;
  fallback: string;
};
const reasonModel = decisionModel as unknown as {
  resolveDecisionRevokedReason?: (
    reason?: string | null,
  ) => RevokedReasonPresentation;
};
assert.equal(
  typeof reasonModel.resolveDecisionRevokedReason,
  'function',
  'revoked reasons must be resolved by executable behavior instead of source-text regex',
);
const resolveDecisionRevokedReason = reasonModel.resolveDecisionRevokedReason!;
for (const [reason, translationKey] of [
  ['material_deleted', 'wiki.decisionRevokedReasonMaterialDeleted'],
  ['material deleted', 'wiki.decisionRevokedReasonMaterialDeleted'],
  ['资料已物理删除', 'wiki.decisionRevokedReasonMaterialDeleted'],
  [
    'page_archived_by_rebuild',
    'wiki.decisionRevokedReasonPageArchivedByRebuild',
  ],
  [
    'page archived by rebuild',
    'wiki.decisionRevokedReasonPageArchivedByRebuild',
  ],
  ['知识库重建归档页面', 'wiki.decisionRevokedReasonPageArchivedByRebuild'],
  ['page_identity_changed', 'wiki.decisionRevokedReasonPageIdentityChanged'],
  ['identity changed', 'wiki.decisionRevokedReasonPageIdentityChanged'],
  ['页面身份已发生变化', 'wiki.decisionRevokedReasonPageIdentityChanged'],
  ['page_deleted', 'wiki.decisionRevokedReasonPageDeleted'],
  ['source page deleted', 'wiki.decisionRevokedReasonPageDeleted'],
  ['manual_revoke', 'wiki.decisionRevokedReasonManual'],
  ['manual revoke', 'wiki.decisionRevokedReasonManual'],
] as const) {
  assert.equal(
    resolveDecisionRevokedReason(reason).translationKey,
    translationKey,
  );
}
assert.deepEqual(resolveDecisionRevokedReason('  合规策略调整  '), {
  translationKey: null,
  fallback: '合规策略调整',
});
assert.deepEqual(resolveDecisionRevokedReason(''), {
  translationKey: null,
  fallback: '',
});

console.log('wiki decision center view model validation passed');
