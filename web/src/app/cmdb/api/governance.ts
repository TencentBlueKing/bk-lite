import useApiClient from '@/utils/request';

export interface GovernanceOverview {
  snapshot_date: string | null;
  total_count: number;
  fully_healthy_count: number;
  total_health_score: number | null;
  completeness_score: number | null;
  freshness_score: number | null;
  duplicate_group_count: number;
  island_instance_count: number;
  uniqueness_conflict_group_count: number;
}

export interface GovernanceMember {
  id: number;
  inst_uuid: string;
  inst_name: string;
  organization: string[];
}

export interface GovernanceProblem {
  id: number;
  problem_type: string;
  model_id: string;
  model_name?: string;
  rule_id: string;
  title: string;
  detail: string;
  members: GovernanceMember[];
  hidden_member_count: number;
  can_ignore: boolean;
  field_ids: string[];
  snapshot_date: string;
}

export const useGovernanceApi = () => {
  const { get, post } = useApiClient();

  const getGovernanceOverview = (params: { model_id?: string; organization_id?: string }) => {
    const query = new URLSearchParams();
    if (params.model_id) query.set('model_id', params.model_id);
    if (params.organization_id) query.set('organization_id', params.organization_id);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return get(`/cmdb/api/governance/overview/${suffix}`) as Promise<GovernanceOverview>;
  };

  const getGovernanceProblems = (params: {
    path?: string;
    model_id?: string;
    organization_id?: string;
    rule_id?: string;
    q?: string;
    page?: number;
    page_size?: number;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value));
    });
    return get(`/cmdb/api/governance/problems/?${query.toString()}`) as Promise<{
      count: number;
      page: number;
      page_size: number;
      items: GovernanceProblem[];
      snapshot_date: string | null;
    }>;
  };

  const ignoreGovernanceProblem = (problemId: number) =>
    post(`/cmdb/api/governance/problems/${problemId}/ignore/`, {});

  const confirmGovernanceProblem = (problemId: number) =>
    post(`/cmdb/api/governance/problems/${problemId}/confirm/`, {});

  const createGovernanceRelation = (problemId: number, dstInstId: number) =>
    post(`/cmdb/api/governance/problems/${problemId}/relation/`, { dst_inst_id: dstInstId });

  const batchConfirmGovernanceProblems = (problemIds: number[]) =>
    post('/cmdb/api/governance/problems/batch_confirm/', { problem_ids: problemIds });

  const refreshGovernance = (params: { model_id?: string }) =>
    post('/cmdb/api/governance/refresh/', { model_id: params.model_id || '' });

  return {
    getGovernanceOverview,
    getGovernanceProblems,
    refreshGovernance,
    ignoreGovernanceProblem,
    confirmGovernanceProblem,
    createGovernanceRelation,
    batchConfirmGovernanceProblems,
  };
};
