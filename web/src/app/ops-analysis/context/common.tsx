'use client';

import {
  createContext,
  useContext,
  useState,
  ReactNode,
  useCallback,
} from 'react';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import type { TagItem } from '@/app/ops-analysis/types/namespace';

interface OpsAnalysisContextType {
  tagList: TagItem[];
  tagsLoading: boolean;
  fetchTags: () => Promise<void>;
}

const OpsAnalysisContext = createContext<OpsAnalysisContextType | undefined>(
  undefined
);

export const OpsAnalysisProvider = ({ children }: { children: ReactNode }) => {
  const [tagList, setTagList] = useState<TagItem[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [hasFetchedTags, setHasFetchedTags] = useState(false);

  const { getTagList } = useNamespaceApi();

  const fetchTags = useCallback(async () => {
    // 如果已经获取过数据，直接返回（即使为空）
    if (hasFetchedTags) {
      return;
    }

    try {
      setTagsLoading(true);
      const response = await getTagList({ page: 1, page_size: 10000 });
      const responseTagList = response?.items || [];
      setTagList(responseTagList);
      setHasFetchedTags(true);
    } catch (err) {
      console.error('获取标签列表失败:', err);
    } finally {
      setTagsLoading(false);
    }
  }, [getTagList, hasFetchedTags]);

  const value: OpsAnalysisContextType = {
    tagList,
    tagsLoading,
    fetchTags,
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
