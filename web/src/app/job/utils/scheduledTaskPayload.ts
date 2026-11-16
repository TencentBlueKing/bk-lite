import type { JobType, ScheduledTaskConcurrencyPolicy, ScheduledTaskFormData } from '../types';

export type CronTemplateType = 'script' | 'playbook';

export function resolveScheduledTaskConcurrencyPolicy(
  value: unknown,
): ScheduledTaskConcurrencyPolicy {
  if (value === 'skip' || value === 'run' || value === 'queue') {
    return value;
  }
  return 'skip';
}

export interface BuildScheduledTaskTemplateInput {
  jobType: JobType;
  templateType: CronTemplateType;
  script?: number | null;
  playbook?: number | null;
}

export function buildScheduledTaskTemplatePayload(
  input: BuildScheduledTaskTemplateInput,
): Pick<ScheduledTaskFormData, 'job_type' | 'script' | 'playbook'> {
  if (input.jobType === 'file') {
    return { job_type: 'file' };
  }

  if (input.templateType === 'playbook') {
    return {
      job_type: 'playbook',
      script: null,
      playbook: input.playbook ?? null,
    };
  }

  return {
    job_type: 'script',
    script: input.script ?? null,
    playbook: null,
  };
}

export interface TemplateParamDefinition {
  name: string;
  default?: string;
}

export interface TemplateParamPayloadItem {
  name: string;
  value: string;
  is_modified: boolean;
}

export function buildTemplateParamsPayload(
  params: TemplateParamDefinition[],
  values: Record<string, unknown>,
  edited: Record<string, boolean> = {},
): TemplateParamPayloadItem[] {
  return params.map((param) => {
    const currentValue = String(values[`param_${param.name}`] ?? '');
    const defaultValue = param.default ?? '';
    return {
      name: param.name,
      value: currentValue,
      is_modified: currentValue !== defaultValue || !!edited[param.name],
    };
  });
}

export function restoreScheduledTaskTemplateUi(task: {
  job_type?: JobType | string | null;
}): { jobType: JobType; templateType: CronTemplateType } {
  if (task.job_type === 'playbook') {
    return { jobType: 'script', templateType: 'playbook' };
  }
  if (task.job_type === 'file') {
    return { jobType: 'file', templateType: 'script' };
  }
  return { jobType: 'script', templateType: 'script' };
}
