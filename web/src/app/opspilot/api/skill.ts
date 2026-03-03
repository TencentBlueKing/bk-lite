import useApiClient from '@/utils/request';
import type {
  KnowledgeBase,
  InvocationLogParams,
  InvocationLogResponse,
  SkillListParams,
  SkillListResponse,
  SkillDetail,
  RuleParams,
  RuleResponse,
  RulePayload,
  LlmModel,
  SkillDetailPayload,
  SkillTool,
  SkillTemplate,
  CreateSkillPayload,
  Skill,
} from '@/app/opspilot/types/skill';

export const useSkillApi = () => {
  const { get, post, patch, del, put } = useApiClient();

  const fetchInvocationLogs = async (params: InvocationLogParams): Promise<InvocationLogResponse> => {
    return get('/opspilot/model_provider_mgmt/skill_log/', { params });
  };

  const fetchSkill = async (params: SkillListParams): Promise<SkillListResponse> => {
    return get('/opspilot/model_provider_mgmt/llm/', { params });
  };

  const fetchSkillDetail = async (id: string | null): Promise<SkillDetail> => {
    return get(`/opspilot/model_provider_mgmt/llm/${id}/`);
  };

  const fetchKnowledgeBases = async (): Promise<KnowledgeBase[]> => {
    return get('/opspilot/knowledge_mgmt/knowledge_base/');
  };

  const updateRule = async (key: string | number, postData: Partial<RulePayload>): Promise<void> => {
    await patch(`/opspilot/model_provider_mgmt/rule/${key}/`, postData);
  };

  const createRule = async (postData: RulePayload): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/rule/', postData);
  };

  const fetchRules = async (params: RuleParams): Promise<RuleResponse> => {
    return get('/opspilot/model_provider_mgmt/rule/', { params });
  };

  const deleteRule = async (id: number): Promise<void> => {
    await del(`/opspilot/model_provider_mgmt/rule/${id}/`);
  };

  const fetchLlmModels = async (): Promise<LlmModel[]> => {
    return get('/opspilot/model_provider_mgmt/llm_model/', { params: { enabled: 1 } });
  };

  const saveSkillDetail = async (id: string | null, payload: SkillDetailPayload): Promise<void> => {
    await put(`/opspilot/model_provider_mgmt/llm/${id}/`, payload);
  };

  const fetchSkillTools = async (): Promise<SkillTool[]> => {
    return get('/opspilot/model_provider_mgmt/skill_tools/');
  };

  const fetchSkillTemplates = async (): Promise<SkillTemplate[]> => {
    return get('/opspilot/model_provider_mgmt/llm/get_template_list/');
  };

  const createSkill = async (payload: CreateSkillPayload): Promise<Skill> => {
    return post('/opspilot/model_provider_mgmt/llm/', payload);
  };

  const togglePin = async (id: string | number): Promise<void> => {
    return post(`/opspilot/model_provider_mgmt/llm/${id}/toggle_pin/`);
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
    fetchSkillTools,
    fetchSkillTemplates,
    createSkill,
    togglePin,
  };
};
