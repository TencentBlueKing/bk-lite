import { useEffect, useState } from 'react';
import { message } from 'antd';
import useApiClient from '@/utils/request';
import { ConfigDataProps } from '@/app/opspilot/types/knowledge';

interface FormData {
  name?: string;
  introduction?: string;
  team?: string[];
}

const useFetchConfigData = (id: string | null) => {
  const { get } = useApiClient();
  const [formData, setFormData] = useState<FormData>({});
  const [configData, setConfigData] = useState<ConfigDataProps>({
    rerankModel: false,
    selectedRerankModel: null,
    selectedEmbedModel: null,
    resultCount: 100,
    rerankTopK: 10,
    enableNaiveRag: false,
    enableQaRag: false,
    enableGraphRag: false,
    ragSize: 0,
    qaSize: 0,
    graphSize: 0,
    searchType: 'similarity_score_threshold',
    scoreThreshold: 0.3,
    ragRecallMode: 'chunk'
  });
  const [loading, setLoading] = useState(true);
  const [knowledgeBasePermissions, setKnowledgeBasePermissions] = useState<string[]>([]);

  useEffect(() => {
    const fetchConfigData = async () => {
      try {
        const data = await get(`/opspilot/knowledge_mgmt/knowledge_base/${id}/`);

        setFormData({
          name: data.name || '',
          introduction: data.introduction || '',
          team: data.team || []
        });

        setConfigData({
          rerankModel: data.enable_rerank || false,
          selectedRerankModel: data.rerank_model || null,
          selectedEmbedModel: data.embed_model || null,
          resultCount: data.result_count || 100,
          rerankTopK: data.rerank_top_k || 10,
          enableNaiveRag: data.enable_naive_rag || false,
          enableQaRag: data.enable_qa_rag || false,
          enableGraphRag: data.enable_graph_rag || false,
          ragSize: data.rag_size || 0,
          qaSize: data.qa_size || 0,
          graphSize: data.graph_size || 0,
          searchType: data.search_type || 'similarity_score_threshold',
          scoreThreshold: data.score_threshold || 0.3,
          ragRecallMode: data.rag_recall_mode || 'chunk'
        });
        setKnowledgeBasePermissions(data.permissions || []);
      } catch (error) {
        message.error('Failed to fetch config data.');
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    if (id) {
      fetchConfigData();
    }
  }, [get, id]);

  return { formData, configData, setFormData, setConfigData, loading, knowledgeBasePermissions };
};

export default useFetchConfigData;
