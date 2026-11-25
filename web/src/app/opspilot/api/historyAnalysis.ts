import { useMemo } from 'react';
import { z } from 'zod';
import useApiClient from '@/utils/request';

const range = z.object({
  scope: z.literal('range'), start: z.string(), end: z.string(),
  person: z.string().optional(), channel_id: z.number().optional(),
});
const sessions = z.object({ scope: z.literal('sessions'), session_ids: z.array(z.string()) });
const scope = z.discriminatedUnion('scope', [range, sessions]);
const objective = z.enum(['overview', 'needs', 'quality']);
const coverage = z.object({ conversation_count: z.number(), question_count: z.number() });
const preview = coverage.extend({ issue: z.string() });
const task = coverage.extend({
  id: z.number(), name: z.string(), objective, scope,
  status: z.enum(['queued', 'running', 'completed', 'failed']),
  failure: z.string(), creator: z.string(), created_at: z.string(),
});
const evidence = z.object({ session_id: z.string(), message_id: z.number() });
const report = task.extend({
  focus: z.string(), findings: z.array(z.object({
    finding: z.string(), suggestion: z.string(), evidence: z.array(evidence),
  })),
});
const taskList = z.object({ items: z.array(task), count: z.number() });

export type AnalysisScope = z.infer<typeof scope>;
export type Objective = z.infer<typeof objective>;
export type AnalysisTask = z.infer<typeof task>;
export type AnalysisReport = z.infer<typeof report>;
export type Evidence = z.infer<typeof evidence>;
export type Preview = z.infer<typeof preview>;
interface CreateConfig {
  name: string;
  objective: Objective;
  focus: string;
  request_id: string;
}

const base = '/opspilot/model_provider_mgmt/skill_channel';
export function useHistoryAnalysisApi(skillId: string) {
  const { get, post } = useApiClient();
  return useMemo(() => {
    const params = { skill_id: skillId };
    return {
      list: async (page: number) => taskList.parse(await get<unknown>(`${base}/analyses/`, { params: { ...params, page } })),
      preview: async (selection: AnalysisScope) => preview.parse(await post<unknown>(`${base}/analysis_preview/`, { ...params, ...selection })),
      create: async (selection: AnalysisScope, config: CreateConfig) =>
        task.parse(await post<unknown>(`${base}/analyses/`, { ...params, ...selection, ...config })),
      retry: async (id: number) => task.parse(await post<unknown>(`${base}/analysis_retry/`, { ...params, task_id: id })),
      report: async (id: number) => report.parse(await get<unknown>(`${base}/analysis_report/`, { params: { ...params, task_id: id } })),
      pdf: (id: number) => get<Blob>(`${base}/analysis_report/`, { params: { ...params, task_id: id, download: 'pdf' }, responseType: 'blob' }),
    };
  }, [skillId, get, post]);
}
export type HistoryAnalysisApi = ReturnType<typeof useHistoryAnalysisApi>;
