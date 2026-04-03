'use client';

import {
  createContext,
  useContext,
  useState,
  ReactNode,
  useCallback,
  useRef,
} from 'react';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import type {
  TagItem,
  NamespaceItem,
} from '@/app/ops-analysis/types/namespace';

interface OpsAnalysisContextType {
  tagList: TagItem[];
  tagsLoading: boolean;
  namespaceList: NamespaceItem[];
  namespacesLoading: boolean;
  fetchTags: () => Promise<void>;
  fetchNamespaces: () => Promise<void>;
  refreshNamespaces: () => Promise<void>;
}

const OpsAnalysisContext = createContext<OpsAnalysisContextType | undefined>(
  undefined
);

export const OpsAnalysisProvider = ({ children }: { children: ReactNode }) => {
  const [tagList, setTagList] = useState<TagItem[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [namespaceList, setNamespaceList] = useState<NamespaceItem[]>([]);
  const [namespacesLoading, setNamespacesLoading] = useState(false);

  const hasFetchedTagsRef = useRef(false);
  const tagsRequestingRef = useRef(false);
  const hasFetchedNamespacesRef = useRef(false);
  const namespacesRequestingRef = useRef(false);

  const { getTagList, getNamespaceList } = useNamespaceApi();

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

  const value: OpsAnalysisContextType = {
    tagList,
    tagsLoading,
    namespaceList,
    namespacesLoading,
    fetchTags,
    fetchNamespaces,
    refreshNamespaces,
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
