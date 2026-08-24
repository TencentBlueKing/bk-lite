'use client';

import { createContext, useContext } from 'react';

import type { SourceDataRequestOptions } from '@/app/ops-analysis/api/dataSource';

export interface SharedDataSourceAccess {
  queryDataSource: (
    dataSourceId: number,
    params?: unknown,
    options?: SourceDataRequestOptions,
  ) => Promise<unknown>;
  getDataSourceDetails: (ids: Array<number | string>) => Promise<unknown>;
}

const ShareDataSourceContext = createContext<SharedDataSourceAccess | null>(null);

export const ShareDataSourceProvider = ShareDataSourceContext.Provider;

export const useSharedDataSourceQuery = () => useContext(ShareDataSourceContext);
