'use client';

import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from 'react';

import type { FilterOptionLabelStore } from '@/app/ops-analysis/context/filterOptionLabelStore';
import { useParamInputOptions } from '@/app/ops-analysis/hooks/useParamInputOptions';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import { useShareOrganization } from '@/app/ops-analysis/context/shareOrganization';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { Group } from '@/types/index';
import { UserInfoContext } from '@/context/userInfo';
import { useTimeRangeList } from '@/constants/shared';
import { useTranslation } from '@/utils/i18n';
import {
  mapOptionLabels,
  type FilterTemplateLabels,
} from '@/app/ops-analysis/utils/filterTemplate';
import { getParamInputConfigKey } from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import { isDynamicOptionFilter } from '@/app/ops-analysis/utils/optionBackedFilterValue';
import { isOrganizationFilterDefinition } from '@/app/ops-analysis/utils/unifiedFilterState';

const EMPTY_OPTION_LABELS: Record<string, Record<string, string> | undefined> = {};
const EMPTY_TIME_LABELS: Record<number, string> = {};
const EMPTY_DATE_LABELS: Record<string, string> = {};

const subscribeNop = () => () => {};

const collectOrgNames = (groups: Group[] | undefined) => {
  const names: Record<string, string> = {};
  const visit = (nodes: Group[] | undefined) => {
    nodes?.forEach((group) => {
      if (group?.id != null && group.name) {
        names[String(group.id)] = group.name;
        const numeric = Number(group.id);
        if (Number.isFinite(numeric)) names[String(numeric)] = group.name;
      }
      visit(group.subGroups);
      visit(group.children);
    });
  };
  visit(groups);
  return names;
};

const hasPublishedLabels = (
  labelsByFilterId: Record<string, Record<string, string> | undefined>,
  filterId: string,
) => Object.prototype.hasOwnProperty.call(labelsByFilterId, filterId);

/**
 * 筛选栏已经渲染并声明覆盖的筛选不再自己请求。
 * 等布局阶段登记完成后再决定，避免和筛选栏抢同一轮请求。
 * 标签被 invalidate 清掉后会重新加载，不能把上一块画布的结果当成当前结果。
 */
const DynamicOptionLabelLoader = ({
  definition,
  store,
}: {
  definition: UnifiedFilterDefinition;
  store: FilterOptionLabelStore;
}) => {
  const [active, setActive] = useState(false);
  const [reloadKey, setReloadKey] = useState('0');

  useEffect(() => {
    const decide = () => {
      const snapshot = store.getSnapshot();
      setReloadKey(String(snapshot.revisions[definition.id] ?? 0));
      const covered = snapshot.coveredIds.has(definition.id);
      const published = hasPublishedLabels(snapshot.labelsByFilterId, definition.id);
      setActive(!covered && !published);
    };
    decide();
    return store.subscribe(decide);
  }, [definition.id, store]);

  const state = useParamInputOptions(definition.inputConfig, {
    suppressErrorNotification: true,
  }, { enabled: active, reloadKey });

  useEffect(() => {
    if (!active) return;
    if (state.status === 'success') {
      store.publish(definition.id, mapOptionLabels(state.options));
      return;
    }
    if (state.status === 'error') {
      store.publish(definition.id, {});
    }
  }, [active, definition.id, state.options, state.status, store]);

  return null;
};

export const FilterDisplayLabelLoaders = ({
  definitions,
  enabled,
  store,
  canvasId = '',
}: {
  definitions: UnifiedFilterDefinition[];
  enabled: boolean;
  store: FilterOptionLabelStore;
  canvasId?: string;
}) => {
  if (!enabled) return null;
  return definitions
    .filter((definition) => definition.enabled && isDynamicOptionFilter(definition))
    .map((definition) => (
      <DynamicOptionLabelLoader
        key={`${canvasId}:${definition.id}:${getParamInputConfigKey(definition.inputConfig)}`}
        definition={definition}
        store={store}
      />
    ));
};

export const useFilterDisplayLabels = (
  definitions: UnifiedFilterDefinition[],
  enabled: boolean,
  store: FilterOptionLabelStore,
): {
  labels: FilterTemplateLabels;
} => {
  const { t } = useTranslation();
  const shareMode = useShareMode();
  const shareOrganization = useShareOrganization();
  const userInfo = useContext(UserInfoContext);
  const timeRanges = useTimeRangeList();
  const subscribe = useCallback((listener: () => void) => (
    enabled ? store.subscribe(listener) : subscribeNop()
  ), [enabled, store]);
  const getSnapshot = useCallback(
    () => (enabled ? store.getSnapshot() : store.getServerSnapshot()),
    [enabled, store],
  );
  const labelSnapshot = useSyncExternalStore(
    subscribe,
    getSnapshot,
    store.getServerSnapshot,
  );

  const timeRangeLabels = useMemo(() => {
    const next: Record<number, string> = {};
    timeRanges.forEach((item) => {
      const minutes = Number(item.value);
      if (minutes > 0 && item.label) next[minutes] = String(item.label);
    });
    return next;
  }, [timeRanges]);

  const dateRangeLabels = useMemo(() => ({
    today: t('dateRange.today'),
    yesterday: t('dateRange.yesterday'),
    this_week: t('dateRange.this_week'),
    last_week: t('dateRange.last_week'),
    this_month: t('dateRange.this_month'),
    last_month: t('dateRange.last_month'),
    last_7_days: t('dateRange.last_7_days'),
    last_30_days: t('dateRange.last_30_days'),
    last_90_days: t('dateRange.last_90_days'),
  }), [t]);

  const separator = t('dashboard.filterTokenSeparator', '、');
  const formatPair = useCallback((left: string, right: string) => (
    `${left}${separator}${right}`
  ), [separator]);
  const formatMultiSelect = useCallback((first: string, count: number) => (
    t('dashboard.filterTokenMulti', '{first} 等 {count} 项', { first, count })
  ), [t]);

  const orgNamesById = useMemo(() => {
    const needsOrg = definitions.some(
      (definition) => definition.enabled && isOrganizationFilterDefinition(definition),
    );
    if (!needsOrg) return {} as Record<string, string>;
    if (shareMode) {
      if (!shareOrganization) return undefined;
      return collectOrgNames(shareOrganization.groupTree);
    }
    if (!userInfo) return undefined;
    if (userInfo.loading && userInfo.groupTree.length === 0) return undefined;
    return collectOrgNames(userInfo.groupTree);
  }, [definitions, shareMode, shareOrganization, userInfo]);

  const optionLabelsByFilterId = useMemo(() => {
    if (!enabled) return EMPTY_OPTION_LABELS;
    const allowed = new Set(
      definitions
        .filter((definition) => definition.enabled && isDynamicOptionFilter(definition))
        .map((definition) => definition.id),
    );
    return Object.entries(labelSnapshot.labelsByFilterId).reduce<
      Record<string, Record<string, string> | undefined>
    >((next, [filterId, labels]) => {
      if (allowed.has(filterId)) next[filterId] = labels;
      return next;
    }, {});
  }, [definitions, enabled, labelSnapshot.labelsByFilterId]);

  const idleLabels = useMemo<FilterTemplateLabels>(() => ({
    optionLabelsByFilterId: EMPTY_OPTION_LABELS,
    orgNamesById: undefined,
    timeRangeLabels: EMPTY_TIME_LABELS,
    dateRangeLabels: EMPTY_DATE_LABELS,
    formatPair,
    formatMultiSelect,
  }), [formatMultiSelect, formatPair]);

  const labels = useMemo<FilterTemplateLabels>(() => {
    if (!enabled) return idleLabels;
    return {
      optionLabelsByFilterId,
      orgNamesById,
      timeRangeLabels,
      dateRangeLabels,
      formatPair,
      formatMultiSelect,
    };
  }, [
    dateRangeLabels,
    enabled,
    formatMultiSelect,
    formatPair,
    idleLabels,
    optionLabelsByFilterId,
    orgNamesById,
    timeRangeLabels,
  ]);

  return { labels };
};
