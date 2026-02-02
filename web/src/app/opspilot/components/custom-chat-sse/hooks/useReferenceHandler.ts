/**
 * 参考链接处理 Hook
 */

import { useState, useCallback } from 'react';
import { ReferenceModalState, DrawerContentState } from '@/app/opspilot/types/chat';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import { transformGraphData } from '@/app/opspilot/utils/graphUtils';

export const useReferenceHandler = (t: (key: string) => string) => {
  const [referenceModal, setReferenceModal] = useState<ReferenceModalState>({
    visible: false,
    loading: false,
    title: '',
    content: ''
  });

  const [drawerContent, setDrawerContent] = useState<DrawerContentState>({
    visible: false,
    title: '',
    content: '',
    chunkType: undefined,
    graphData: undefined
  });

  const { getChunkDetail } = useKnowledgeApi();

  const handleReferenceClick = useCallback(
    async (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement;

      let referenceElement = target;
      while (referenceElement && !referenceElement.classList.contains('reference-link')) {
        referenceElement = referenceElement.parentElement as HTMLElement;
      }

      if (referenceElement && referenceElement.classList.contains('reference-link')) {
        const chunkId = referenceElement.getAttribute('data-chunk-id');
        const knowledgeId = referenceElement.getAttribute('data-knowledge-id');
        const chunkType = referenceElement.getAttribute('data-chunk-type') || 'Document';

        if (!knowledgeId) {
          console.warn('Missing knowledge_id in reference link');
          return;
        }

        setDrawerContent({
          visible: true,
          title: `${t('chat.chunkDetails')}`,
          content: '',
          chunkType: chunkType as 'Document' | 'QA' | 'Graph',
          graphData: undefined
        });

        setReferenceModal(prev => ({ ...prev, loading: true }));

        try {
          const data = await getChunkDetail(
            knowledgeId,
            chunkId,
            chunkType as 'Document' | 'QA' | 'Graph' | undefined
          );

          if (chunkType === 'Graph' && data) {
            let graphData: { nodes: any[]; edges: any[] } = { nodes: [], edges: [] };

            if (Array.isArray(data)) {
              graphData = transformGraphData(data);
            } else if (data.content) {
              try {
                const parsedContent = JSON.parse(data.content);
                if (Array.isArray(parsedContent)) {
                  graphData = transformGraphData(parsedContent);
                } else if (parsedContent.nodes && parsedContent.edges) {
                  graphData = parsedContent;
                }
              } catch (e) {
                console.warn('Failed to parse graph data from content:', e);
              }
            }

            setDrawerContent(prev => ({ ...prev, graphData }));
          } else {
            let displayContent = '';

            if (chunkType === 'QA' && data) {
              const question = data.question || '';
              const answer = data.answer || '';
              const docName = data.doc_name || '';
              displayContent = `${t('chat.question')}：${question}\n\n${t('chat.answer')}：${answer}`;
              if (docName) {
                displayContent += `\n\n${t('chat.referenceQASource')}：${docName}`;
              }
            } else {
              displayContent = data?.content || '--';
              const docName = data?.doc_name || '';
              if (docName) {
                displayContent += `\n\n${t('chat.referenceDocSource')}：${docName}`;
              }
            }

            setDrawerContent(prev => ({ ...prev, content: displayContent }));
          }
        } catch (error) {
          console.error('Failed to fetch reference details:', error);
        } finally {
          setReferenceModal(prev => ({ ...prev, loading: false }));
        }
      }
    },
    [getChunkDetail, t]
  );

  const closeDrawer = useCallback(() => {
    setDrawerContent({
      visible: false,
      title: '',
      content: '',
      chunkType: undefined,
      graphData: undefined
    });
  }, []);

  return {
    referenceModal,
    drawerContent,
    handleReferenceClick,
    closeDrawer
  };
};
