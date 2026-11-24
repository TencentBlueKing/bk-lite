'use client';

import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { isTransportCanceled } from '@/utils/requestCancellation';
import {
  collectVariableIds,
  executionOrder,
  runDataVariables,
  variableQueryKey,
  variablesAffectedBy,
  type ColumnResult,
  type DataVariable,
} from '@/app/ops-analysis/utils/dataVariable';

interface DataVariableRuntimeValue {
  ready: boolean;
  columns: Record<string, ColumnResult>;
}

const DataVariableRuntimeContext = createContext<DataVariableRuntimeValue | null>(null);

export const useDataVariableRuntime = (): DataVariableRuntimeValue | null =>
  useContext(DataVariableRuntimeContext);

const filterSignature = (values: Record<string, unknown>): string => {
  try {
    return JSON.stringify(values);
  } catch {
    return '';
  }
};

export const withDatasourceNamespace = (
  params: Record<string, unknown>,
  namespaces: number[] | undefined,
  namespaceId?: number,
): Record<string, unknown> | null => {
  if (!Array.isArray(namespaces) || namespaces.length === 0) return params;
  const resolved = namespaceId ?? namespaces[0];
  if (resolved === undefined) return null;
  return { ...params, namespace_id: resolved };
};

export const DataVariableRuntimeProvider: React.FC<{
  variables: DataVariable[];
  referencedValues: unknown;
  filterValues: Record<string, any>;
  reloadKey?: number;
  scopeKey?: string | number;
  /** 返回 null 时这一步不发请求。调用方在这里套上筛选联动和组织参数。 */
  prepareParams?: (
    variable: DataVariable,
    params: Record<string, unknown>,
  ) => Record<string, unknown> | null;
  children: React.ReactNode;
}> = ({
  variables,
  referencedValues,
  filterValues,
  reloadKey = 0,
  scopeKey = '',
  prepareParams,
  children,
}) => {
  const parent = useDataVariableRuntime();
  const { getSourceDataByApiId } = useDataSourceApi();
  const fetchRowsRef = useRef(getSourceDataByApiId);
  fetchRowsRef.current = getSourceDataByApiId;
  const prepareParamsRef = useRef(prepareParams);
  prepareParamsRef.current = prepareParams;
  const variablesRef = useRef(variables);
  variablesRef.current = variables;
  const contextKey = [
    filterSignature(filterValues),
    String(reloadKey),
    String(scopeKey),
  ].join('\n');
  const requestKey = [
    JSON.stringify(variables),
    contextKey,
    collectVariableIds(referencedValues).join('|'),
  ].join('\n');
  const roots = useMemo(
    () => {
      const rootKey = requestKey.split('\n').pop() ?? '';
      return rootKey ? rootKey.split('|') : [];
    },
    [requestKey],
  );
  const inheritedColumns = useMemo(() => {
    if (!parent?.ready || roots.length === 0) return null;
    const next: Record<string, ColumnResult> = {};
    for (const id of roots) {
      const column = parent.columns[id];
      if (!column) return null;
      next[id] = column;
    }
    return next;
  }, [parent, roots]);
  const [columns, setColumns] = useState<Record<string, ColumnResult>>({});
  const [settled, setSettled] = useState(false);
  const columnsRef = useRef(columns);
  columnsRef.current = columns;
  const queryKeysRef = useRef<Record<string, string>>({});
  const contextRef = useRef('');
  const settledRef = useRef(false);
  const ready = roots.length === 0 || inheritedColumns != null || settled;
  const displayColumns = inheritedColumns ?? columns;

  // 筛选或整页刷新才整批重查。只改一条变量时，重查它和引用它的下游，其余列留着。
  useEffect(() => {
    if (roots.length === 0 || inheritedColumns) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    const list = variablesRef.current;
    const needed = executionOrder(list, roots);
    const nextKeys: Record<string, string> = {};
    needed.forEach((id) => {
      const variable = list.find((item) => item.id === id);
      if (variable) nextKeys[id] = variableQueryKey(variable);
    });
    const contextChanged = contextRef.current !== contextKey || !settledRef.current;
    const changedIds = needed.filter((id) => queryKeysRef.current[id] !== nextKeys[id]);
    const refreshIds = contextChanged
      ? undefined
      : new Set([
        ...variablesAffectedBy(list, changedIds),
        ...needed.filter((id) => !columnsRef.current[id]),
      ]);
    const liveIds = new Set(list.map((variable) => variable.id));
    const prune = (source: Record<string, ColumnResult>) => {
      const next: Record<string, ColumnResult> = {};
      Object.entries(source).forEach(([id, column]) => {
        if (liveIds.has(id)) next[id] = column;
      });
      return next;
    };
    if (refreshIds && refreshIds.size === 0) {
      const pruned = prune(columnsRef.current);
      if (Object.keys(pruned).length !== Object.keys(columnsRef.current).length) {
        columnsRef.current = pruned;
        setColumns(pruned);
      }
      return undefined;
    }
    if (contextChanged) {
      settledRef.current = false;
      setSettled(false);
    }
    void runDataVariables({
      variables: list,
      roots,
      reuse: refreshIds ? columnsRef.current : undefined,
      refreshIds,
      fetchRows: async (variable, params) => {
        const prepare = prepareParamsRef.current;
        const prepared = prepare ? prepare(variable, params) : params;
        if (!prepared) throw new Error('data-variable-request-blocked');
        const response = await fetchRowsRef.current(variable.dataSourceId, prepared, {
          suppressErrorNotification: true,
          signal: controller.signal,
        });
        return response.data;
      },
    }).then((run) => {
      if (cancelled) return;
      const merged = refreshIds
        ? { ...columnsRef.current, ...run.columns }
        : run.columns;
      const nextColumns = prune(merged);
      columnsRef.current = nextColumns;
      queryKeysRef.current = { ...queryKeysRef.current, ...nextKeys };
      contextRef.current = contextKey;
      settledRef.current = true;
      setColumns(nextColumns);
      setSettled(true);
    }).catch((error: unknown) => {
      if (cancelled || controller.signal.aborted || isTransportCanceled(error)) return;
      if (contextChanged) {
        columnsRef.current = {};
        setColumns({});
      }
      settledRef.current = true;
      setSettled(true);
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [requestKey, inheritedColumns, roots, contextKey]);

  const value = useMemo<DataVariableRuntimeValue>(
    () => ({ ready, columns: displayColumns }),
    [ready, displayColumns],
  );

  return (
    <DataVariableRuntimeContext.Provider value={value}>
      {children}
    </DataVariableRuntimeContext.Provider>
  );
};
