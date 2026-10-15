'use client';

import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  type MutableRefObject,
  type ReactNode,
} from 'react';

import {
  createFilterOptionLabelStore,
  type FilterOptionLabelStore,
} from '@/app/ops-analysis/context/filterOptionLabelStore';
import {
  FilterDisplayLabelLoaders,
  useFilterDisplayLabels,
} from '@/app/ops-analysis/hooks/useFilterDisplayLabels';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { isDynamicOptionFilter } from '@/app/ops-analysis/utils/optionBackedFilterValue';
import { getParamInputConfigKey } from '@/app/ops-analysis/utils/paramInputOptionsLoader';
import {
  areFilterTemplateLabelsSettled,
  filterTemplateAsyncDependencies,
  resolveFilterTemplate,
  type FilterTemplateLabels,
} from '@/app/ops-analysis/utils/filterTemplate';

export const FILTER_TEMPLATE_READY_TIMEOUT_MS = 8000;

interface FilterTemplateContextValue {
  definitions: UnifiedFilterDefinition[];
  resolveDefinitions: UnifiedFilterDefinition[];
  appliedValues: Record<string, FilterValue>;
  resolveEnabled: boolean;
  labels: FilterTemplateLabels;
  canvasId: string;
}

interface FilterLabelScope {
  canvasId: string;
  filters: Array<[string, string]>;
}

const FilterTemplateContext = createContext<FilterTemplateContextValue | null>(null);
const FilterOptionLabelStoreContext = createContext<FilterOptionLabelStore | null>(null);

const dynamicFilterScope = (definitions: UnifiedFilterDefinition[]) =>
  definitions
    .filter((definition) => definition.enabled && isDynamicOptionFilter(definition))
    .map((definition): [string, string] => [
      definition.id,
      getParamInputConfigKey(definition.inputConfig),
    ])
    .sort((left, right) => left[0].localeCompare(right[0]));

export const useFilterOptionLabelStore = () => useContext(FilterOptionLabelStoreContext);

export const FilterTemplateProvider = ({
  definitions,
  resolveDefinitions,
  appliedValues,
  resolveEnabled,
  canvasId = '',
  children,
}: {
  definitions: UnifiedFilterDefinition[];
  resolveDefinitions?: UnifiedFilterDefinition[];
  appliedValues: Record<string, FilterValue>;
  resolveEnabled: boolean;
  canvasId?: string;
  children: ReactNode;
}) => {
  const source = resolveDefinitions ?? definitions;
  const parentStore = useContext(FilterOptionLabelStoreContext);
  const ownedStoreRef = useRef<FilterOptionLabelStore | null>(null);
  if (parentStore == null && ownedStoreRef.current == null) {
    ownedStoreRef.current = createFilterOptionLabelStore();
  }
  const store = parentStore ?? ownedStoreRef.current!;
  const ownsStore = parentStore == null;
  const { labels } = useFilterDisplayLabels(source, resolveEnabled, store);
  const scope = useMemo<FilterLabelScope>(() => ({
    canvasId,
    filters: dynamicFilterScope(source),
  }), [canvasId, source]);
  const scopeRef = useRef<FilterLabelScope | null>(null);

  useLayoutEffect(() => {
    if (!ownsStore) return;
    const previous = scopeRef.current;
    scopeRef.current = scope;
    if (previous == null) return;
    if (previous.canvasId !== scope.canvasId) {
      store.invalidate(null);
      return;
    }
    const nextConfig = new Map(scope.filters);
    const stale: string[] = [];
    previous.filters.forEach(([id, configKey]) => {
      if (nextConfig.get(id) !== configKey) stale.push(id);
    });
    store.invalidate(stale);
  }, [ownsStore, scope, store]);

  const value = useMemo<FilterTemplateContextValue>(() => ({
    definitions,
    resolveDefinitions: source,
    appliedValues,
    resolveEnabled,
    labels,
    canvasId,
  }), [appliedValues, canvasId, definitions, labels, resolveEnabled, source]);

  return (
    <FilterOptionLabelStoreContext.Provider value={store}>
      <FilterTemplateContext.Provider value={value}>
        <FilterDisplayLabelLoaders
          definitions={source}
          enabled={resolveEnabled}
          store={store}
          canvasId={canvasId}
        />
        {children}
      </FilterTemplateContext.Provider>
    </FilterOptionLabelStoreContext.Provider>
  );
};

export const useFilterTemplateVariables = () => {
  const context = useContext(FilterTemplateContext);
  return context?.definitions ?? [];
};

export const useFilterTemplateSnapshot = () => {
  const context = useContext(FilterTemplateContext);
  return {
    definitions: context?.resolveDefinitions ?? [],
    values: context?.appliedValues ?? {},
  };
};

/** 查看态替换已应用筛选；编辑态、表单和没有提供方时保持模板原文。 */
export const useFilterTemplateText = (text?: string | null) => {
  const resolve = useFilterTemplateResolver();
  return resolve(text);
};

export const useFilterTemplateResolver = () => {
  const context = useContext(FilterTemplateContext);
  return (text?: string | null) => {
    if (!text) return '';
    if (!context?.resolveEnabled) return text;
    return resolveFilterTemplate(
      text,
      context.resolveDefinitions,
      context.appliedValues,
      context.labels,
    );
  };
};

export const FilterTemplateTextBridge = ({
  textRef,
}: {
  textRef: MutableRefObject<(text?: string | null) => string>;
}) => {
  const resolve = useFilterTemplateResolver();
  textRef.current = resolve;
  return null;
};

/** 订阅渲染发 ready 前，等标题里的动态选项和机构树进入终态。超时后也放行。 */
export const FilterTemplateTitleGate = ({
  texts,
  active,
  onSettled,
}: {
  texts: string[];
  active: boolean;
  onSettled: () => void;
}) => {
  const context = useContext(FilterTemplateContext);
  const textKey = texts.join('\0');
  const dependencies = useMemo(
    () => filterTemplateAsyncDependencies(
      textKey ? textKey.split('\0') : [],
      context?.resolveDefinitions ?? [],
    ),
    [context?.resolveDefinitions, textKey],
  );
  const settled = !active
    || !context?.resolveEnabled
    || areFilterTemplateLabelsSettled(dependencies, context.labels);
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  useEffect(() => {
    if (!active) return undefined;
    if (settled) {
      onSettledRef.current();
      return undefined;
    }
    const timer = window.setTimeout(() => {
      onSettledRef.current();
    }, FILTER_TEMPLATE_READY_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [active, settled, textKey]);

  return null;
};
