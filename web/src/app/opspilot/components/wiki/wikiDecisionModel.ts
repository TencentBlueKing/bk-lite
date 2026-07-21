import type {
  CheckDecisionAction,
  CheckItem,
  DecisionListView,
  FetchDecisionItemsParams,
  WikiDecisionRule,
  WikiDecisionType,
} from '@/app/opspilot/types/wiki';

export interface WikiDecisionSnapshot {
  id?: number;
  title: string;
  pageType: string;
  body: string;
  sourceLabel: string;
  contribution: string;
  sourceCount?: number;
  relationCount?: number;
  versionLabel: string;
}

export interface WikiDecisionViewModel {
  kind: WikiDecisionType;
  title: string;
  summary: string;
  reason: string;
  triggerSource: string;
  impactScope: string;
  recoverability: string;
  current: WikiDecisionSnapshot;
  incoming: WikiDecisionSnapshot;
  identitySource?: 'frozen' | 'legacy_display';
}

type UnknownRecord = Record<string, unknown>;

const DECISION_KIND_BY_CHECK_TYPE: Record<string, WikiDecisionType> = {
  cannot_merge: 'knowledge_conflict',
  material_update: 'knowledge_conflict',
  duplicate: 'page_identity',
  conflict: 'page_identity',
};

const asRecord = (value: unknown): UnknownRecord =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};

const asString = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number' ? String(value) : '';

const asNumber = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

const firstString = (records: UnknownRecord[], keys: string[]): string => {
  for (const record of records) {
    for (const key of keys) {
      const value = asString(record[key]);
      if (value) return value;
    }
  }
  return '';
};

const firstRecord = (record: UnknownRecord, keys: string[]): UnknownRecord => {
  for (const key of keys) {
    const value = asRecord(record[key]);
    if (Object.keys(value).length) return value;
  }
  return {};
};

const getMaterialLabels = (related: UnknownRecord): string[] => {
  const materials = related.materials;
  if (!Array.isArray(materials)) return [];
  return materials
    .map((material) => {
      const record = asRecord(material);
      return firstString([record], ['name', 'title', 'source_label']);
    })
    .filter(Boolean);
};

const buildSnapshot = (
  page: Partial<CheckItem['related_pages'][number]> | undefined,
  snapshot: UnknownRecord,
  fallback: Partial<WikiDecisionSnapshot>,
): WikiDecisionSnapshot => {
  const pageRecord = asRecord(page);
  const currentVersion = page?.current_version;
  return {
    id: asNumber(snapshot.page_id) ?? asNumber(snapshot.id) ?? page?.id,
    title:
      firstString([snapshot, pageRecord], ['title']) || fallback.title || '',
    pageType:
      firstString([snapshot, pageRecord], ['page_type', 'pageType']) ||
      fallback.pageType ||
      '',
    body:
      firstString([snapshot, pageRecord], ['body', 'content']) ||
      fallback.body ||
      '',
    sourceLabel:
      firstString(
        [snapshot, pageRecord],
        ['source_label', 'sourceLabel', 'source'],
      ) ||
      fallback.sourceLabel ||
      '',
    contribution:
      firstString([snapshot, pageRecord], ['contribution', 'update_method']) ||
      fallback.contribution ||
      '',
    sourceCount:
      asNumber(snapshot.source_count) ??
      page?.source_count ??
      fallback.sourceCount,
    relationCount:
      asNumber(snapshot.relation_count) ??
      page?.relation_count ??
      fallback.relationCount,
    versionLabel:
      firstString([snapshot, pageRecord], ['version_label', 'versionLabel']) ||
      (currentVersion ? `v${currentVersion}` : '') ||
      fallback.versionLabel ||
      '',
  };
};

const hasCompleteFrozenKnowledgeConflictContext = (item: CheckItem): boolean => {
  const context = asRecord(item.decision_context);
  const participants = Array.isArray(context.participants)
    ? context.participants.map(asRecord)
    : [];
  const incoming = asRecord(context.incoming);
  const pageIdentity = asRecord(context.page_identity);
  const incomingMaterialId = asNumber(incoming.material_id);
  const incomingContentHash = asString(incoming.content_hash).trim();
  const candidateVersionId = asNumber(context.candidate_version_id);
  const lockedCurrentVersionId = asNumber(context.locked_current_version_id);
  const participantsComplete =
    participants.length > 0 &&
    participants.every(
      (participant) =>
        asNumber(participant.material_id) !== undefined &&
        Boolean(asString(participant.content_hash).trim()),
    );
  const incomingIsParticipant = participants.some(
    (participant) =>
      asNumber(participant.material_id) === incomingMaterialId &&
      asString(participant.content_hash).trim() === incomingContentHash,
  );

  return Boolean(
    item.decision_key &&
    item.candidate_version &&
    candidateVersionId === item.candidate_version &&
    context.decision_type === 'knowledge_conflict' &&
    asString(context.subject_key).trim() &&
    asString(context.schema_fingerprint).trim() &&
    lockedCurrentVersionId !== undefined &&
    asString(context.current_body_hash).trim() &&
    asString(context.candidate_body_hash).trim() &&
    asNumber(pageIdentity.page_id) !== undefined &&
    incomingMaterialId !== undefined &&
    incomingContentHash &&
    participantsComplete &&
    incomingIsParticipant
  );
};

export const getDecisionKind = (item: CheckItem): WikiDecisionType | null => {
  const expectedKind = DECISION_KIND_BY_CHECK_TYPE[item.check_type];
  if (!expectedKind) return null;
  if (item.decision_type && item.decision_type !== expectedKind) return null;
  if (item.status === 'open' && expectedKind === 'knowledge_conflict') {
    if (
      !hasCompleteFrozenKnowledgeConflictContext(item) ||
      !item.candidate_version ||
      !item.candidate ||
      !item.current_knowledge ||
      !item.new_knowledge
    ) {
      return null;
    }
  }
  if (item.status === 'open' && expectedKind === 'page_identity') {
    const context = asRecord(item.decision_context);
    const identities = Array.isArray(context.page_identities)
      ? context.page_identities.filter(
        (identity) => Object.keys(asRecord(identity)).length,
      )
      : [];
    if (
      identities.length !== 2 ||
      !Object.keys(asRecord(context.target_identity)).length
    ) {
      return null;
    }
    if (!item.current_knowledge || !item.new_knowledge) return null;
  }
  return expectedKind;
};

export const filterDecisionItems = (items: CheckItem[]): CheckItem[] =>
  items.filter((item) => getDecisionKind(item) !== null);

export const getDecisionActions = (item: CheckItem): CheckDecisionAction[] => {
  const kind = getDecisionKind(item);
  if (kind === 'knowledge_conflict')
    return ['keep_current', 'edit_accept', 'use_new'];
  if (kind === 'page_identity') return ['keep_separate', 'merge'];
  return [];
};

export const isDecisionRuleRevocable = (
  rule?: WikiDecisionRule | null,
): boolean => rule?.status === 'active';

export interface DecisionRevokedReasonPresentation {
  translationKey: string | null;
  fallback: string;
}

const REVOKED_REASON_TRANSLATION_KEYS: Record<string, string> = {
  material_deleted: 'wiki.decisionRevokedReasonMaterialDeleted',
  material_physically_deleted: 'wiki.decisionRevokedReasonMaterialDeleted',
  资料已物理删除: 'wiki.decisionRevokedReasonMaterialDeleted',
  资料删除: 'wiki.decisionRevokedReasonMaterialDeleted',
  page_archived_by_rebuild: 'wiki.decisionRevokedReasonPageArchivedByRebuild',
  知识库重建归档页面: 'wiki.decisionRevokedReasonPageArchivedByRebuild',
  重建归档页面: 'wiki.decisionRevokedReasonPageArchivedByRebuild',
  page_identity_changed: 'wiki.decisionRevokedReasonPageIdentityChanged',
  identity_changed: 'wiki.decisionRevokedReasonPageIdentityChanged',
  页面身份已发生变化: 'wiki.decisionRevokedReasonPageIdentityChanged',
  页面身份变化: 'wiki.decisionRevokedReasonPageIdentityChanged',
  page_deleted: 'wiki.decisionRevokedReasonPageDeleted',
  source_page_deleted: 'wiki.decisionRevokedReasonPageDeleted',
  页面已物理删除: 'wiki.decisionRevokedReasonPageDeleted',
  页面已删除: 'wiki.decisionRevokedReasonPageDeleted',
  manual_revoke: 'wiki.decisionRevokedReasonManual',
  用户主动撤销: 'wiki.decisionRevokedReasonManual',
  手动撤销: 'wiki.decisionRevokedReasonManual',
};

const normalizeRevokedReason = (reason: string): string =>
  reason
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');

export const resolveDecisionRevokedReason = (
  reason?: string | null,
): DecisionRevokedReasonPresentation => {
  const fallback = (reason || '').trim();
  if (!fallback) return { translationKey: null, fallback: '' };
  return {
    translationKey:
      REVOKED_REASON_TRANSLATION_KEYS[normalizeRevokedReason(fallback)] ||
      REVOKED_REASON_TRANSLATION_KEYS[fallback] ||
      null,
    fallback,
  };
};

export const buildDecisionViewModel = (
  item: CheckItem,
): WikiDecisionViewModel | null => {
  const kind = getDecisionKind(item);
  if (!kind) return null;
  const context = asRecord(item.decision_context);
  const related = asRecord(item.related);
  const pages = item.related_pages || [];
  const pageIdentities = Array.isArray(context.page_identities)
    ? context.page_identities
      .map(asRecord)
      .filter((identity) => Object.keys(identity).length)
    : [];
  const targetIdentity = asRecord(context.target_identity);
  const targetPageId =
    asNumber(targetIdentity.page_id) ?? asNumber(targetIdentity.id);
  const serializedCurrent = asRecord(item.current_knowledge);
  const serializedIncoming = asRecord(item.new_knowledge);
  const sourceIdentity =
    pageIdentities.find((identity) => {
      const pageId = asNumber(identity.page_id) ?? asNumber(identity.id);
      return pageId !== undefined && pageId !== targetPageId;
    }) || {};
  const sourcePageId =
    asNumber(sourceIdentity.page_id) ?? asNumber(sourceIdentity.id);
  const serializedCurrentId =
    asNumber(serializedCurrent.page_id) ?? asNumber(serializedCurrent.id);
  const serializedIncomingId =
    asNumber(serializedIncoming.page_id) ?? asNumber(serializedIncoming.id);
  const hasFrozenIdentity =
    kind === 'page_identity' &&
    targetPageId !== undefined &&
    sourcePageId !== undefined &&
    serializedCurrentId === targetPageId &&
    serializedIncomingId === sourcePageId;
  const currentRecord = Object.keys(serializedCurrent).length
    ? { ...(hasFrozenIdentity ? targetIdentity : {}), ...serializedCurrent }
    : hasFrozenIdentity
      ? targetIdentity
      : firstRecord(context, ['current_knowledge', 'current_page', 'current']);
  const incomingRecord = Object.keys(serializedIncoming).length
    ? { ...(hasFrozenIdentity ? sourceIdentity : {}), ...serializedIncoming }
    : hasFrozenIdentity
      ? sourceIdentity
      : firstRecord(context, [
        'new_knowledge',
        'incoming_page',
        'new_page',
        'incoming',
        'candidate',
      ]);
  const pageForIdentity = (identity: UnknownRecord) => {
    const pageId = asNumber(identity.page_id) ?? asNumber(identity.id);
    return pages.find((page) => page.id === pageId);
  };
  // related_pages 顺序只用于旧数据展示；合并提交始终只发送语义 action，不携带目标页面。
  const currentPage = hasFrozenIdentity
    ? pageForIdentity(currentRecord)
    : pages[0];
  const incomingPage =
    kind === 'page_identity'
      ? hasFrozenIdentity
        ? pageForIdentity(incomingRecord)
        : pages[1]
      : undefined;
  const materialLabels = getMaterialLabels(related);

  const currentSource =
    firstString(
      [currentRecord, context, related],
      ['source_label', 'current_source_label', 'current_source'],
    ) ||
    materialLabels[0] ||
    '';
  const incomingSource =
    firstString(
      [incomingRecord, context, related],
      [
        'source_label',
        'incoming_source_label',
        'new_source_label',
        'trigger_source',
      ],
    ) ||
    materialLabels.at(-1) ||
    '';

  const current = buildSnapshot(currentPage, currentRecord, {
    sourceLabel: currentSource,
  });
  const incoming = buildSnapshot(incomingPage, incomingRecord, {
    title: incomingPage?.title || current.title,
    pageType: incomingPage?.page_type || current.pageType,
    body: item.candidate?.body || incomingPage?.body || '',
    sourceLabel: incomingSource,
    versionLabel: item.candidate_version ? `v${item.candidate_version}` : '',
  });

  return {
    kind,
    identitySource:
      kind === 'page_identity'
        ? hasFrozenIdentity
          ? 'frozen'
          : 'legacy_display'
        : undefined,
    title:
      firstString([context, related], ['title']) ||
      current.title ||
      incoming.title,
    summary: firstString([context, related], ['summary', 'description']),
    reason: firstString(
      [context, related],
      ['reason', 'decision_reason', 'why'],
    ),
    triggerSource:
      firstString([context, related], ['trigger_source', 'source_label']) ||
      incoming.sourceLabel,
    impactScope: firstString([context, related], ['impact_scope', 'impact']),
    recoverability: firstString(
      [context, related],
      ['recoverability', 'recovery'],
    ),
    current,
    incoming,
  };
};

export interface DecisionSubmittingState {
  checkId: number;
  action: CheckDecisionAction | 'revoke';
}

export interface DecisionInteractionState {
  isSubmitting: boolean;
  isOutdated: boolean;
  requiresContextRefresh: boolean;
  canDecide: boolean;
  canEditSubmit: boolean;
}

export const getDecisionInteractionState = (
  item: CheckItem,
  submitting?: DecisionSubmittingState | null,
  outdatedItemId?: number | null,
): DecisionInteractionState => {
  const isSubmitting = submitting?.checkId === item.id;
  const isOutdated = outdatedItemId === item.id;
  const model = buildDecisionViewModel(item);
  if (!model) {
    return {
      isSubmitting,
      isOutdated,
      requiresContextRefresh: false,
      canDecide: false,
      canEditSubmit: false,
    };
  }
  const requiresContextRefresh =
    item.status === 'open' &&
    model.kind === 'page_identity' &&
    model.identitySource !== 'frozen';
  const canDecide =
    item.status === 'open' &&
    !isSubmitting &&
    !isOutdated &&
    !requiresContextRefresh;

  return {
    isSubmitting,
    isOutdated,
    requiresContextRefresh,
    canDecide,
    canEditSubmit: canDecide && model.kind === 'knowledge_conflict',
  };
};

export interface DecisionLoadPlan {
  primary: FetchDecisionItemsParams;
  companion: FetchDecisionItemsParams;
}

export const buildDecisionLoadPlan = (
  view: DecisionListView,
  page: number,
  pageSize: number,
): DecisionLoadPlan => ({
  primary: { view, page, page_size: pageSize },
  companion: {
    view: view === 'pending' ? 'processed' : 'pending',
    page: 1,
    page_size: 1,
  },
});

export interface DecisionScopeState {
  items: CheckItem[];
  total: number;
  counts: Record<DecisionListView, number>;
  activeId: number | null;
  error: string;
  loadedScopeKey: string;
}

export type DecisionScopeAction =
  | { type: 'reset' }
  | {
      type: 'load_succeeded';
      scopeKey: string;
      items: CheckItem[];
      total: number;
      counts: Record<DecisionListView, number>;
    }
  | { type: 'load_failed'; scopeKey: string; error: string }
  | { type: 'set_error'; error: string }
  | { type: 'select'; activeId: number | null };

export const createDecisionScopeState = (): DecisionScopeState => ({
  items: [],
  total: 0,
  counts: { pending: 0, processed: 0 },
  activeId: null,
  error: '',
  loadedScopeKey: '',
});

export const decisionScopeReducer = (
  state: DecisionScopeState,
  action: DecisionScopeAction,
): DecisionScopeState => {
  if (action.type === 'reset') return createDecisionScopeState();
  if (action.type === 'load_failed') {
    return {
      ...createDecisionScopeState(),
      error: action.error,
      loadedScopeKey: action.scopeKey,
    };
  }
  if (action.type === 'set_error') {
    return { ...state, error: action.error };
  }
  if (action.type === 'select') {
    return { ...state, activeId: action.activeId };
  }
  if (action.type === 'load_succeeded') {
    const activeId = action.items.some((item) => item.id === state.activeId)
      ? state.activeId
      : (action.items[0]?.id ?? null);
    return {
      items: action.items,
      total: action.total,
      counts: action.counts,
      activeId,
      error: '',
      loadedScopeKey: action.scopeKey,
    };
  }
  return state;
};

export const getVisibleDecisionScopeState = (
  state: DecisionScopeState,
  scopeKey: string,
): DecisionScopeState =>
  state.loadedScopeKey === scopeKey ? state : createDecisionScopeState();
export const shouldRefreshDecisionListAfterError = (message: string): boolean =>
  /失效|过期|outdated|stale/i.test(message);

export interface LatestRequestGuard {
  begin: () => number;
  invalidate: () => void;
  isCurrent: (requestId: number) => boolean;
  commitIfCurrent: (requestId: number, commit: () => void) => boolean;
}

export const createLatestRequestGuard = (): LatestRequestGuard => {
  let currentRequestId = 0;

  const isCurrent = (requestId: number) => requestId === currentRequestId;

  return {
    begin: () => {
      currentRequestId += 1;
      return currentRequestId;
    },
    invalidate: () => {
      currentRequestId += 1;
    },
    isCurrent,
    commitIfCurrent: (requestId, commit) => {
      if (!isCurrent(requestId)) return false;
      commit();
      return true;
    },
  };
};
