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
import type { RedisInstanceFormValue } from '@/app/opspilot/components/skill/redisToolEditor';
import type { MysqlInstanceFormValue } from '@/app/opspilot/components/skill/mysqlToolEditor';
import type { OracleInstanceFormValue } from '@/app/opspilot/components/skill/oracleToolEditor';
import type { MssqlInstanceFormValue } from '@/app/opspilot/components/skill/mssqlToolEditor';
import type { PostgresInstanceFormValue } from '@/app/opspilot/components/skill/postgresToolEditor';
import type { ElasticsearchInstanceFormValue } from '@/app/opspilot/components/skill/elasticsearchToolEditor';
import type { JenkinsInstanceFormValue } from '@/app/opspilot/components/skill/jenkinsToolEditor';
import type { KubernetesInstanceFormValue } from '@/app/opspilot/components/skill/kubernetesToolEditor';

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

  const testRedisConnection = async (instance: Omit<RedisInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_redis_connection/', instance);
  };

  const testMysqlConnection = async (instance: Omit<MysqlInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_mysql_connection/', instance);
  };

  const testOracleConnection = async (instance: Omit<OracleInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_oracle_connection/', instance);
  };

  const testMssqlConnection = async (instance: Omit<MssqlInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_mssql_connection/', instance);
  };

  const testPostgresConnection = async (instance: Omit<PostgresInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_postgres_connection/', instance);
  };

  const testEsConnection = async (instance: Omit<ElasticsearchInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_es_connection/', instance);
  };

  const testJenkinsConnection = async (instance: Omit<JenkinsInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_jenkins_connection/', instance);
  };

  const testKubernetesConnection = async (instance: Omit<KubernetesInstanceFormValue, 'testStatus'>): Promise<void> => {
    await post('/opspilot/model_provider_mgmt/skill_tools/test_kubernetes_connection/', instance);
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
    testRedisConnection,
    testMysqlConnection,
    testOracleConnection,
    testMssqlConnection,
    testPostgresConnection,
    testEsConnection,
    testJenkinsConnection,
    testKubernetesConnection,
    fetchSkillTemplates,
    createSkill,
    togglePin,
  };
};
