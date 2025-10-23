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

  const { getTagList } = useNamespaceApi();

  const fetchTags = useCallback(async () => {
    // 如果已经有数据，直接返回
    if (tagList.length > 0) {
      return;
    }

    try {
      setTagsLoading(true);
      const response = await getTagList({ page: 1, page_size: 10000 });
      const responseTagList = response?.items || [];
      setTagList(responseTagList);
    } catch (err) {
      console.error('获取标签列表失败:', err);
    } finally {
      setTagsLoading(false);
    }
  }, [getTagList, tagList.length]);

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
