import useApiClient from '@/utils/request';
import { KnowledgeBase } from '@/app/opspilot/types/skill';

export const useSkillApi = () => {
  const { get, post, patch, del, put } = useApiClient();

  /**
   * Fetches invocation logs for a specific skill.
   * @param params - Query parameters for fetching logs.
   */
  const fetchInvocationLogs = async (params: any): Promise<any> => {
    return get('/opspilot/model_provider_mgmt/skill_log/', { params });
  };

  const fetchSkill = async (params: any): Promise<any> => {
    return get('/opspilot/model_provider_mgmt/llm/', { params });
  };

  /**
   * Fetches skill details by ID.
   * @param id - Skill ID.
   */
  const fetchSkillDetail = async (id: string | null): Promise<any> => {
    return get(`/opspilot/model_provider_mgmt/llm/${id}/`);
  };

  /**
   * Fetches all knowledge bases.
   */
  const fetchKnowledgeBases = async (): Promise<KnowledgeBase[]> => {
    return get('/opspilot/knowledge_mgmt/knowledge_base/');
  };

  /**
   * Sends a PATCH request to update a rule.
   * @param key - Rule key.
   * @param postData - Data to be sent in the request.
   */
  const updateRule = async (key: string, postData: any): Promise<void> => {
    await patch(`/opspilot/model_provider_mgmt/rule/${key}/`, postData);
  };

  /**
   * Sends a POST request to create a new rule.
   * @param postData - Data to be sent in the request.
   */
  const createRule = async (postData: any): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/rule/', postData);
  };

  /**
   * Fetches skill rules with optional query parameters.
   * @param params - Query parameters for fetching rules.
   */
  const fetchRules = async (params: any): Promise<any> => {
    return get('/opspilot/model_provider_mgmt/rule/', { params });
  };

  /**
   * Deletes a rule by ID.
   * @param id - Rule ID.
   */
  const deleteRule = async (id: number): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/rule/${id}/`);
  };

  /**
   * Fetches all LLM models.
   */
  const fetchLlmModels = async (): Promise<any[]> => {
    return get('/opspilot/model_provider_mgmt/llm_model/', { params: { enabled: 1 } });
  };

  /**
   * Saves skill details.
   * @param id - Skill ID.
   * @param payload - Data to be saved.
   */
  const saveSkillDetail = async (id: string | null, payload: any): Promise<void> => {
    await put(`/opspilot/model_provider_mgmt/llm/${id}/`, payload);
  };

  /**
   * Executes the LLM with the given payload.
   * @param payload - Data to be sent in the request.
   */
  const executeLlm = async (payload: any): Promise<any> => {
    return post('/opspilot/model_provider_mgmt/llm/execute/', payload);
  };

  /**
   * Fetches the list of skill tools.
   */
  const fetchSkillTools = async (): Promise<any[]> => {
    return get('/opspilot/model_provider_mgmt/skill_tools/');
  };

  /**
   * Fetches the list of skill templates.
   * @param params - Query parameters including is_template.
   */
  const fetchSkillTemplates = async (): Promise<any[]> => {
    return get('/opspilot/model_provider_mgmt/llm/get_template_list/');
  };

  /**
   * Creates a new skill.
   * @param payload - Data to be sent in the request.
   */
  const createSkill = async (payload: { name: string; introduction: string; team: any[]; skill_type: number }): Promise<any> => {
    return post('/opspilot/model_provider_mgmt/llm/', payload);
  };

  return {
    fetchInvocationLogs,
    fetchSkill,
    fetchSkillDetail,
    fetchKnowledgeBases,
    updateRule,
    createRule,
    fetchRules,
    deleteRule,
    fetchLlmModels,
    saveSkillDetail,
    executeLlm,
    fetchSkillTools,
    fetchSkillTemplates,
    createSkill,
  };
};
