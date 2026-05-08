'use client';

import {
  createContext,
  useContext,
  useState,
  ReactNode,
  useCallback,
  useEffect,
  useRef,
} from 'react';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import { useUserInfoContext } from '@/context/userInfo';
import { addAuthToDataSources } from '@/app/ops-analysis/utils/permissionChecker';
import type {
  TagItem,
  NamespaceItem,
} from '@/app/ops-analysis/types/namespace';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

interface OpsAnalysisContextType {
  tagList: TagItem[];
  tagsLoading: boolean;
  namespaceList: NamespaceItem[];
  namespacesLoading: boolean;
  dataSources: DatasourceItem[];
  dataSourcesLoading: boolean;
  fetchTags: () => Promise<void>;
  fetchNamespaces: () => Promise<void>;
  refreshNamespaces: () => Promise<void>;
  fetchDataSources: () => Promise<void>;
  refreshDataSources: () => Promise<void>;
}

const OpsAnalysisContext = createContext<OpsAnalysisContextType | undefined>(
  undefined
);

export const OpsAnalysisProvider = ({ children }: { children: ReactNode }) => {
  const [tagList, setTagList] = useState<TagItem[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [namespaceList, setNamespaceList] = useState<NamespaceItem[]>([]);
  const [namespacesLoading, setNamespacesLoading] = useState(false);
  const [rawDataSources, setRawDataSources] = useState<DatasourceItem[]>([]);
  const [dataSources, setDataSources] = useState<DatasourceItem[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);

  const hasFetchedTagsRef = useRef(false);
  const tagsRequestingRef = useRef(false);
  const hasFetchedNamespacesRef = useRef(false);
  const namespacesRequestingRef = useRef(false);
  const hasFetchedDataSourcesRef = useRef(false);
  const dataSourcesRequestingRef = useRef(false);

  const { getDataSourceList } = useDataSourceApi();
  const { getTagList, getNamespaceList } = useNamespaceApi();
  const { selectedGroup } = useUserInfoContext();

  const normalizeDataSources = useCallback((response: any): DatasourceItem[] => {
    if (Array.isArray(response)) {
      return response;
    }

    if (Array.isArray(response?.items)) {
      return response.items;
    }

    return [];
  }, []);

  const applyDataSourceAuth = useCallback(
    (list: DatasourceItem[]) =>
      addAuthToDataSources(list || [], selectedGroup?.id),
    [selectedGroup?.id],
  );

  const fetchTags = useCallback(async () => {
    if (hasFetchedTagsRef.current || tagsRequestingRef.current) {
      return;
    }

    try {
      tagsRequestingRef.current = true;
      setTagsLoading(true);
      const response = await getTagList({ page: 1, page_size: 10000 });
      const responseTagList = response?.items || [];
      setTagList(responseTagList);
      hasFetchedTagsRef.current = true;
    } catch (err) {
      console.error('获取标签列表失败:', err);
    } finally {
      tagsRequestingRef.current = false;
      setTagsLoading(false);
    }
  }, [getTagList]);

  const fetchNamespaces = useCallback(async () => {
    if (hasFetchedNamespacesRef.current || namespacesRequestingRef.current) {
      return;
    }

    try {
      namespacesRequestingRef.current = true;
      setNamespacesLoading(true);
      const response = await getNamespaceList({ page: 1, page_size: 10000 });
      const responseNamespaceList = response?.items || [];
      setNamespaceList(responseNamespaceList);
      hasFetchedNamespacesRef.current = true;
    } catch (err) {
      console.error('获取命名空间列表失败:', err);
    } finally {
      namespacesRequestingRef.current = false;
      setNamespacesLoading(false);
    }
  }, [getNamespaceList]);

  const refreshNamespaces = useCallback(async () => {
    if (namespacesRequestingRef.current) {
      return;
    }

    try {
      namespacesRequestingRef.current = true;
      setNamespacesLoading(true);
      const response = await getNamespaceList({ page: 1, page_size: 10000 });
      const responseNamespaceList = response?.items || [];
      setNamespaceList(responseNamespaceList);
      hasFetchedNamespacesRef.current = true;
    } catch (err) {
      console.error('刷新命名空间列表失败:', err);
    } finally {
      namespacesRequestingRef.current = false;
      setNamespacesLoading(false);
    }
  }, [getNamespaceList]);

  const fetchDataSources = useCallback(async () => {
    if (hasFetchedDataSourcesRef.current || dataSourcesRequestingRef.current) {
      return;
    }

    try {
      dataSourcesRequestingRef.current = true;
      setDataSourcesLoading(true);
      const response = await getDataSourceList({
        page: 1,
        page_size: 10000,
      });
      const responseDataSources = normalizeDataSources(response);
      setRawDataSources(responseDataSources);
      setDataSources(applyDataSourceAuth(responseDataSources));
      hasFetchedDataSourcesRef.current = true;
    } catch (err) {
      console.error('获取数据源列表失败:', err);
      setRawDataSources([]);
      setDataSources([]);
    } finally {
      dataSourcesRequestingRef.current = false;
      setDataSourcesLoading(false);
    }
  }, [applyDataSourceAuth, getDataSourceList, normalizeDataSources]);

  const refreshDataSources = useCallback(async () => {
    if (dataSourcesRequestingRef.current) {
      return;
    }

    try {
      dataSourcesRequestingRef.current = true;
      setDataSourcesLoading(true);
      const response = await getDataSourceList({
        page: 1,
        page_size: 10000,
      });
      const responseDataSources = normalizeDataSources(response);
      setRawDataSources(responseDataSources);
      setDataSources(applyDataSourceAuth(responseDataSources));
      hasFetchedDataSourcesRef.current = true;
    } catch (err) {
      console.error('刷新数据源列表失败:', err);
    } finally {
      dataSourcesRequestingRef.current = false;
      setDataSourcesLoading(false);
    }
  }, [applyDataSourceAuth, getDataSourceList, normalizeDataSources]);

  useEffect(() => {
    if (!hasFetchedDataSourcesRef.current) {
      return;
    }

    setDataSources(applyDataSourceAuth(rawDataSources));
  }, [applyDataSourceAuth, rawDataSources]);

  const value: OpsAnalysisContextType = {
    tagList,
    tagsLoading,
    namespaceList,
    namespacesLoading,
    dataSources,
    dataSourcesLoading,
    fetchTags,
    fetchNamespaces,
    refreshNamespaces,
    fetchDataSources,
    refreshDataSources,
  };

  return (
    <OpsAnalysisContext.Provider value={value}>
      {children}
    </OpsAnalysisContext.Provider>
  );
};

export const useOpsAnalysis = (): OpsAnalysisContextType => {
  const context = useContext(OpsAnalysisContext);
  if (context === undefined) {
    throw new Error(
      'useOpsAnalysis must be used within an OpsAnalysisProvider'
    );
  }
  return context;
};
