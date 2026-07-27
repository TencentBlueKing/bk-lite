'use client';

import {
  createContext,
  useContext,
  useState,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import { useUserInfoContext } from '@/context/userInfo';
import { addAuthToDataSources } from '@/app/ops-analysis/utils/permissionChecker';
import { useSharedDataSourceQuery } from '@/app/ops-analysis/context/shareDataSource';
import type {
  NamespaceItem,
} from '@/app/ops-analysis/types/namespace';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

interface OpsAnalysisContextType {
  namespaceList: NamespaceItem[];
  namespacesLoading: boolean;
  dataSources: DatasourceItem[];
  dataSourcesLoading: boolean;
  fetchNamespaces: (ids?: Array<number | string>) => Promise<NamespaceItem[]>;
  loadCanvasNamespaces: (ids?: Array<number | string>) => Promise<NamespaceItem[]>;
  refreshNamespaces: () => Promise<void>;
  fetchDataSources: (ids?: Array<number | string>) => Promise<DatasourceItem[]>;
  loadCanvasDataSources: (ids?: Array<number | string>) => Promise<DatasourceItem[]>;
}

const OpsAnalysisContext = createContext<OpsAnalysisContextType | undefined>(
  undefined
);

export const OpsAnalysisProvider = ({ children }: { children: ReactNode }) => {
  const sharedAccess = useSharedDataSourceQuery();
  const [rawNamespaces, setRawNamespaces] = useState<NamespaceItem[]>([]);
  const [namespacesLoading, setNamespacesLoading] = useState(false);
  const [rawDataSources, setRawDataSources] = useState<DatasourceItem[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);

  const namespaceRequestCountRef = useRef(0);
  const dataSourceRequestCountRef = useRef(0);
  const canvasNamespaceRequestIdRef = useRef(0);
  const canvasDataSourceRequestIdRef = useRef(0);
  const canvasNamespaceKeyRef = useRef('');
  const namespacesRequestingRef = useRef(false);
  const dataSourcesRequestingRef = useRef(false);
  const rawNamespacesRef = useRef<NamespaceItem[]>([]);
  const rawDataSourcesRef = useRef<DatasourceItem[]>([]);

  const { getDataSourceDetails } = useDataSourceApi();
  const { getNamespaceList } = useNamespaceApi();
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

  const normalizeIds = useCallback((ids: Array<number | string> = []) => {
    return Array.from(
      new Set(
        ids
          .map((id) => (typeof id === 'string' ? parseInt(id, 10) : id))
          .filter((id) => Number.isFinite(id))
      )
    ) as number[];
  }, []);

  const buildStableIdsKey = useCallback((ids: number[]) => {
    return [...ids].sort((a, b) => a - b).join(',');
  }, []);

  const applyDataSourceAuth = useCallback(
    (list: DatasourceItem[]) =>
      sharedAccess
        ? (list || []).map((item) => ({ ...item, hasAuth: true }))
        : addAuthToDataSources(list || [], selectedGroup?.id),
    [selectedGroup?.id, sharedAccess],
  );

  const mergeDataSources = useCallback((incoming: DatasourceItem[]) => {
    setRawDataSources((prev) => {
      const nextMap = new Map<number, DatasourceItem>();
      prev.forEach((item) => nextMap.set(item.id, item));
      incoming.forEach((item) => nextMap.set(item.id, item));
      return Array.from(nextMap.values());
    });
  }, []);

  useEffect(() => {
    rawNamespacesRef.current = rawNamespaces;
  }, [rawNamespaces]);

  useEffect(() => {
    rawDataSourcesRef.current = rawDataSources;
  }, [rawDataSources]);

  const mergeNamespaces = useCallback((incoming: NamespaceItem[]) => {
    setRawNamespaces((prev) => {
      const nextMap = new Map<number, NamespaceItem>();
      prev.forEach((item) => nextMap.set(item.id, item));
      incoming.forEach((item) => nextMap.set(item.id, item));
      return Array.from(nextMap.values());
    });
  }, []);

  const finishNamespaceRequest = useCallback(() => {
    namespaceRequestCountRef.current = Math.max(0, namespaceRequestCountRef.current - 1);
    namespacesRequestingRef.current = namespaceRequestCountRef.current > 0;
    setNamespacesLoading(namespaceRequestCountRef.current > 0);
  }, []);

  const finishDataSourceRequest = useCallback(() => {
    dataSourceRequestCountRef.current = Math.max(0, dataSourceRequestCountRef.current - 1);
    dataSourcesRequestingRef.current = dataSourceRequestCountRef.current > 0;
    setDataSourcesLoading(dataSourceRequestCountRef.current > 0);
  }, []);

  const fetchNamespaces = useCallback(async (ids: Array<number | string> = []) => {
    const requestedIds = Array.isArray(ids) ? ids : [];
    const normalizedIds = normalizeIds(requestedIds);

    if (normalizedIds.length === 0) {
      return [];
    }

    const currentNamespaces = rawNamespacesRef.current;
    const existingIds = new Set(currentNamespaces.map((item) => item.id));
    const missingIds = normalizedIds.filter((id) => !existingIds.has(id));
    if (missingIds.length === 0) {
      return currentNamespaces.filter((item) => normalizedIds.includes(item.id));
    }

    // 分享态禁止打普通 namespace 接口；缺失项从已加载数据源元数据拼装
    if (sharedAccess) {
      const namespaceMap = new Map<number, NamespaceItem>();
      currentNamespaces.forEach((item) => namespaceMap.set(item.id, item));
      rawDataSourcesRef.current.forEach((dataSource) => {
        (dataSource.namespace_options || []).forEach((namespace) => {
          if (normalizedIds.includes(namespace.id)) {
            namespaceMap.set(namespace.id, namespace as NamespaceItem);
          }
        });
      });
      const sharedNamespaces = normalizedIds
        .map((id) => namespaceMap.get(id))
        .filter((item): item is NamespaceItem => Boolean(item));
      mergeNamespaces(sharedNamespaces);
      return sharedNamespaces;
    }

    try {
      namespaceRequestCountRef.current += 1;
      namespacesRequestingRef.current = true;
      setNamespacesLoading(true);
      const response = await getNamespaceList({ ids: missingIds.join(',') });
      const responseNamespaceList = Array.isArray(response) ? response : [];
      mergeNamespaces(responseNamespaceList);
      return normalizedIds
        .map((id) => {
          return (
            currentNamespaces.find((item) => item.id === id) ||
            responseNamespaceList.find((item) => item.id === id)
          );
        })
        .filter((item): item is NamespaceItem => Boolean(item));
    } catch (err) {
      console.error('获取命名空间列表失败:', err);
      return [];
    } finally {
      finishNamespaceRequest();
    }
  }, [finishNamespaceRequest, getNamespaceList, mergeNamespaces, normalizeIds, sharedAccess]);

  const loadCanvasNamespaces = useCallback(async (ids: Array<number | string> = []) => {
    const requestedIds = Array.isArray(ids) ? ids : [];
    const normalizedIds = normalizeIds(requestedIds);
    const normalizedKey = buildStableIdsKey(normalizedIds);
    const requestId = canvasNamespaceRequestIdRef.current + 1;

    if (normalizedIds.length === 0) {
      canvasNamespaceKeyRef.current = '';
      setRawNamespaces([]);
      return [];
    }

    if (sharedAccess) {
      const namespaceMap = new Map<number, NamespaceItem>();
      rawDataSourcesRef.current.forEach((dataSource) => {
        (dataSource.namespace_options || []).forEach((namespace) => {
          if (normalizedIds.includes(namespace.id)) {
            namespaceMap.set(namespace.id, namespace as NamespaceItem);
          }
        });
      });
      const sharedNamespaces = normalizedIds
        .map((id) => namespaceMap.get(id))
        .filter((item): item is NamespaceItem => Boolean(item));
      canvasNamespaceKeyRef.current = normalizedKey;
      setRawNamespaces(sharedNamespaces);
      return sharedNamespaces;
    }

    const currentNamespaces = rawNamespacesRef.current;
    const currentIds = currentNamespaces.map((item) => item.id);
    const currentKey = buildStableIdsKey(currentIds);
    if (canvasNamespaceKeyRef.current === normalizedKey && currentKey === normalizedKey) {
      return currentNamespaces;
    }

    canvasNamespaceRequestIdRef.current = requestId;
    canvasNamespaceKeyRef.current = normalizedKey;

    try {
      namespaceRequestCountRef.current += 1;
      namespacesRequestingRef.current = true;
      setNamespacesLoading(true);
      const response = await getNamespaceList({ ids: normalizedIds.join(',') });
      const responseNamespaceList = Array.isArray(response) ? response : [];
      if (canvasNamespaceRequestIdRef.current === requestId) {
        setRawNamespaces(responseNamespaceList);
      }
      return responseNamespaceList;
    } catch (err) {
      console.error('加载画布命名空间失败:', err);
      if (canvasNamespaceRequestIdRef.current === requestId) {
        canvasNamespaceKeyRef.current = currentKey;
        setRawNamespaces([]);
      }
      return [];
    } finally {
      finishNamespaceRequest();
    }
  }, [buildStableIdsKey, finishNamespaceRequest, getNamespaceList, normalizeIds, sharedAccess]);

  const refreshNamespaces = useCallback(async () => {
    // 分享态不允许枚举目标租户 namespace
    if (sharedAccess || namespacesRequestingRef.current) {
      return;
    }

    try {
      namespaceRequestCountRef.current += 1;
      namespacesRequestingRef.current = true;
      setNamespacesLoading(true);
      const response = await getNamespaceList({ page_size: -1 });
      const responseNamespaceList = Array.isArray(response) ? response : [];
      setRawNamespaces(responseNamespaceList);
    } catch (err) {
      console.error('刷新命名空间列表失败:', err);
    } finally {
      finishNamespaceRequest();
    }
  }, [finishNamespaceRequest, getNamespaceList, sharedAccess]);

  const fetchDataSources = useCallback(async (ids: Array<number | string> = []) => {
    const requestedIds = Array.isArray(ids) ? ids : [];
    const normalizedIds = normalizeIds(requestedIds);

    if (normalizedIds.length === 0) {
      return [];
    }

    const currentDataSources = rawDataSourcesRef.current;
    const existingIds = new Set(currentDataSources.map((item) => item.id));
    const missingIds = normalizedIds.filter((id) => !existingIds.has(id));
    if (missingIds.length === 0) {
      return applyDataSourceAuth(
        currentDataSources.filter((item) => normalizedIds.includes(item.id))
      );
    }

    try {
      dataSourceRequestCountRef.current += 1;
      dataSourcesRequestingRef.current = true;
      setDataSourcesLoading(true);
      const response = await getDataSourceDetails(missingIds);
      const responseDataSources = normalizeDataSources(response);
      const mergedRequestedDataSources = normalizedIds
        .map((id) => {
          return (
            currentDataSources.find((item) => item.id === id) ||
            responseDataSources.find((item) => item.id === id)
          );
        })
        .filter((item): item is DatasourceItem => Boolean(item));
      mergeDataSources(responseDataSources);
      return applyDataSourceAuth(mergedRequestedDataSources);
    } catch (err) {
      console.error('获取数据源详情失败:', err);
      return [];
    } finally {
      finishDataSourceRequest();
    }
  }, [applyDataSourceAuth, finishDataSourceRequest, getDataSourceDetails, mergeDataSources, normalizeDataSources, normalizeIds]);

  const loadCanvasDataSources = useCallback(async (ids: Array<number | string> = []) => {
    const requestedIds = Array.isArray(ids) ? ids : [];
    const normalizedIds = normalizeIds(requestedIds);
    const requestId = canvasDataSourceRequestIdRef.current + 1;
    canvasDataSourceRequestIdRef.current = requestId;

    if (normalizedIds.length === 0) {
      rawDataSourcesRef.current = [];
      setRawDataSources([]);
      return [];
    }

    const currentDataSources = rawDataSourcesRef.current;
    const currentMap = new Map<number, DatasourceItem>();
    currentDataSources.forEach((item) => currentMap.set(item.id, item));
    const missingIds = normalizedIds.filter((id) => !currentMap.has(id));

    if (missingIds.length === 0) {
      const scopedDataSources = normalizedIds
        .map((id) => currentMap.get(id))
        .filter((item): item is DatasourceItem => Boolean(item));
      rawDataSourcesRef.current = scopedDataSources;
      setRawDataSources(scopedDataSources);
      return applyDataSourceAuth(scopedDataSources);
    }

    try {
      dataSourceRequestCountRef.current += 1;
      dataSourcesRequestingRef.current = true;
      setDataSourcesLoading(true);
      const response = await getDataSourceDetails(missingIds);
      const responseDataSources = normalizeDataSources(response);
      const nextMap = new Map<number, DatasourceItem>(currentMap);
      responseDataSources.forEach((item) => nextMap.set(item.id, item));
      const scopedDataSources = normalizedIds
        .map((id) => nextMap.get(id))
        .filter((item): item is DatasourceItem => Boolean(item));
      if (canvasDataSourceRequestIdRef.current === requestId) {
        rawDataSourcesRef.current = scopedDataSources;
        setRawDataSources(scopedDataSources);
      }
      return applyDataSourceAuth(scopedDataSources);
    } catch (err) {
      console.error('加载画布数据源详情失败:', err);
      if (canvasDataSourceRequestIdRef.current === requestId) {
        setRawDataSources([]);
      }
      return [];
    } finally {
      finishDataSourceRequest();
    }
  }, [applyDataSourceAuth, finishDataSourceRequest, getDataSourceDetails, normalizeDataSources, normalizeIds]);

  const dataSources = useMemo(
    () => applyDataSourceAuth(rawDataSources),
    [applyDataSourceAuth, rawDataSources],
  );

  const namespaceList = useMemo(
    () => rawNamespaces,
    [rawNamespaces],
  );

  const value: OpsAnalysisContextType = {
    namespaceList,
    namespacesLoading,
    dataSources,
    dataSourcesLoading,
    fetchNamespaces,
    loadCanvasNamespaces,
    refreshNamespaces,
    fetchDataSources,
    loadCanvasDataSources,
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
