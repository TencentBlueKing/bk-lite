'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

interface KnowledgeInfo {
  name: string;
  introduction: string;
}

interface KnowledgeContextType {
  knowledgeInfo: KnowledgeInfo;
  isLoading: boolean;
  refreshKnowledgeInfo: () => Promise<void>;
}

const KnowledgeContext = createContext<KnowledgeContextType | null>(null);

export const KnowledgeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const searchParams = useSearchParams();
  const id = searchParams?.get('id') || '';
  const { fetchKnowledgeBaseDetails } = useKnowledgeApi();

  const [knowledgeInfo, setKnowledgeInfo] = useState<KnowledgeInfo>({
    name: searchParams?.get('name') || '',
    introduction: searchParams?.get('desc') || '',
  });
  const [isLoading, setIsLoading] = useState(true);

  const refreshKnowledgeInfo = useCallback(async () => {
    if (!id) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      const data = await fetchKnowledgeBaseDetails(Number(id));
      setKnowledgeInfo({
        name: data.name,
        introduction: data.introduction,
      });
    } catch (error) {
      console.error('Failed to fetch knowledge info:', error);
    } finally {
      setIsLoading(false);
    }
  }, [id, fetchKnowledgeBaseDetails]);

  useEffect(() => {
    refreshKnowledgeInfo();
  }, [id]);

  return (
    <KnowledgeContext.Provider value={{ knowledgeInfo, isLoading, refreshKnowledgeInfo }}>
      {children}
    </KnowledgeContext.Provider>
  );
};

export const useKnowledge = () => {
  const context = useContext(KnowledgeContext);
  if (!context) {
    throw new Error('useKnowledge must be used within a KnowledgeProvider');
  }
  return context;
};
