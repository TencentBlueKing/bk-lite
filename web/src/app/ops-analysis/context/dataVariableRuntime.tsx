'use client';

import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  collectVariableIds,
  runDataVariables,
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
  const { getSourceDataByApiId } = useDataSourceApi();
  const fetchRowsRef = useRef(getSourceDataByApiId);
  fetchRowsRef.current = getSourceDataByApiId;
  const prepareParamsRef = useRef(prepareParams);
  prepareParamsRef.current = prepareParams;
  const roots = useMemo(
    () => collectVariableIds(referencedValues),
    [referencedValues],
  );
  const requestKey = useMemo(
    () => [JSON.stringify(variables), filterSignature(filterValues), String(reloadKey), String(scopeKey), roots.join('|')].join('\n'),
    [variables, filterValues, reloadKey, scopeKey, roots],
  );
  const [result, setResult] = useState<{ key: string; columns: Record<string, ColumnResult> } | null>(null);
  const ready = roots.length === 0 || result?.key === requestKey;
  const columns = ready && result?.key === requestKey ? result.columns : {};

  useEffect(() => {
    if (roots.length === 0) return undefined;
    let cancelled = false;
    const key = requestKey;
    void runDataVariables({
      variables,
      roots,
      fetchRows: async (variable, params) => {
        const prepare = prepareParamsRef.current;
        const prepared = prepare ? prepare(variable, params) : params;
        if (!prepared) throw new Error('data-variable-request-blocked');
        const response = await fetchRowsRef.current(variable.dataSourceId, prepared, {
          suppressErrorNotification: true,
        });
        return response.data;
      },
    }).then((run) => {
      if (!cancelled) setResult({ key, columns: run.columns });
    }).catch(() => {
      if (!cancelled) setResult({ key, columns: {} });
    });
    return () => {
      cancelled = true;
    };
  }, [requestKey, roots, variables, filterValues]);

  const value = useMemo<DataVariableRuntimeValue>(
    () => ({ ready, columns }),
    [ready, columns],
  );

  return (
    <DataVariableRuntimeContext.Provider value={value}>
      {children}
    </DataVariableRuntimeContext.Provider>
  );
};
