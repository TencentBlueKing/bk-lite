'use client';

import { useState, useCallback, useEffect } from 'react';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

interface KnowledgeBaseCounts {
  file_count: number;
  web_page_count: number;
  manual_count: number;
  qa_count: number;
  graph_count: number;
  document_count: number;
}

interface UseKnowledgeBaseCountsParams {
  knowledgeBaseId: string | null;
}

interface UseKnowledgeBaseCountsReturn {
  counts: KnowledgeBaseCounts;
  permissions: string[];
  fetchCounts: () => Promise<void>;
}

const DEFAULT_COUNTS: KnowledgeBaseCounts = {
  file_count: 0,
  web_page_count: 0,
  manual_count: 0,
  qa_count: 0,
  graph_count: 0,
  document_count: 0,
};

export const useKnowledgeBaseCounts = ({
  knowledgeBaseId,
}: UseKnowledgeBaseCountsParams): UseKnowledgeBaseCountsReturn => {
  const [counts, setCounts] = useState<KnowledgeBaseCounts>(DEFAULT_COUNTS);
  const [permissions, setPermissions] = useState<string[]>([]);

  const { fetchKnowledgeBaseDetails: fetchKnowledgeBaseDetailsApi } = useKnowledgeApi();

  const fetchCounts = useCallback(async () => {
    if (!knowledgeBaseId) return;

    try {
      const details = await fetchKnowledgeBaseDetailsApi(Number(knowledgeBaseId));
      setPermissions(details.permissions || []);
      setCounts({
        file_count: details.file_count || 0,
        web_page_count: details.web_page_count || 0,
        manual_count: details.manual_count || 0,
        qa_count: details.qa_count || 0,
        graph_count: details.graph_count || 0,
        document_count: details.document_count || 0,
      });
    } catch (error) {
      console.error('Failed to fetch knowledge base details:', error);
      setPermissions([]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [knowledgeBaseId]);

  useEffect(() => {
    fetchCounts();
  }, [fetchCounts]);

  return {
    counts,
    permissions,
    fetchCounts,
  };
};
