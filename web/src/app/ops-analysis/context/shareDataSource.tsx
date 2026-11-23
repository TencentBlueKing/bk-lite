'use client';

import { createContext, useContext } from 'react';

import type { SourceDataRequestOptions } from '@/app/ops-analysis/api/dataSource';

export interface SharedDataSourceAccess {
  queryDataSource: (
    dataSourceId: number,
    params?: unknown,
    options?: SourceDataRequestOptions,
  ) => Promise<unknown>;
  getDataSourceDetails: (ids: Array<number | string>, signal?: AbortSignal) => Promise<unknown>;
  resolveOptionSource: (body: {
    sourceId?: number;
    builtinKey?: string;
    sourceRef?: string;
  }, signal?: AbortSignal) => Promise<{ status?: string; id?: number }>;
}

const ShareDataSourceContext = createContext<SharedDataSourceAccess | null>(null);

export const ShareDataSourceProvider = ShareDataSourceContext.Provider;

export const useSharedDataSourceQuery = () => useContext(ShareDataSourceContext);
