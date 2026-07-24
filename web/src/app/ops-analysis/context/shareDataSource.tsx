'use client';

import { createContext, useContext } from 'react';

export interface SharedDataSourceAccess {
  queryDataSource: (dataSourceId: number, params?: unknown) => Promise<unknown>;
  getDataSourceDetails: (ids: Array<number | string>) => Promise<unknown>;
}

const ShareDataSourceContext = createContext<SharedDataSourceAccess | null>(null);

export const ShareDataSourceProvider = ShareDataSourceContext.Provider;

export const useSharedDataSourceQuery = () => useContext(ShareDataSourceContext);
