import type { ConductorDefinition, ConductorTask } from './types';

export interface ApprovalConfiguration {
  title: string;
  description?: string;
  candidates: string[];
  publicContext: Record<string, string>;
  timeoutSeconds?: number;
}

export interface ApprovalDecisionPair {
  approval: ConductorTask;
  decision: ConductorTask;
}

function isApprovalDecision(approval: ConductorTask, decision: ConductorTask | undefined): decision is ConductorTask {
  return Boolean(
    approval.type === 'HUMAN'
    && decision?.type === 'SWITCH'
    && decision.name === 'approval_decision'
    && decision.inputParameters?.decision === `\${${approval.taskReferenceName}.output.approved}`,
  );
}

/** Locate the Conductor SWITCH implementation hidden behind each user-facing approval node. */
export function approvalDecisionPairs(tasks: ConductorTask[]): ApprovalDecisionPair[] {
  const pairs: ApprovalDecisionPair[] = [];
  const visit = (items: ConductorTask[]) => {
    items.forEach((task, index) => {
      const decision = items[index + 1];
      if (isApprovalDecision(task, decision)) pairs.push({ approval: task, decision });
      for (const branch of task.forkTasks || []) visit(branch);
      for (const branch of Object.values(task.decisionCases || {})) visit(branch);
      visit(task.defaultCase || []);
    });
  };
  visit(tasks);
  return pairs;
}

export function approvalDecisionReference(tasks: ConductorTask[], approvalReference: string): string | undefined {
  return approvalDecisionPairs(tasks).find(({ approval }) => approval.taskReferenceName === approvalReference)?.decision.taskReferenceName;
}

function mapNested(task: ConductorTask, configure: (tasks: ConductorTask[]) => ConductorTask[]): ConductorTask {
  return {
    ...task,
    ...(task.forkTasks ? { forkTasks: task.forkTasks.map(configure) } : {}),
    ...(task.decisionCases ? { decisionCases: Object.fromEntries(Object.entries(task.decisionCases).map(([key, branch]) => [key, configure(branch)])) } : {}),
    ...(task.defaultCase ? { defaultCase: configure(task.defaultCase) } : {}),
  };
}

export function configureApprovalTask(
  definition: ConductorDefinition,
  reference: string,
  config: ApprovalConfiguration,
): ConductorDefinition {
  let found = false;
  const configure = (tasks: ConductorTask[]): ConductorTask[] => tasks.map((task, index) => {
    if (task.taskReferenceName !== reference) return mapNested(task, configure);
    if (task.type !== 'HUMAN') throw new Error('选中的节点不是人工审批节点');
    const decision = tasks[index + 1];
    if (!decision || decision.type !== 'SWITCH') throw new Error('审批节点缺少固定决策分支');
    found = true;
    const inputParameters: Record<string, unknown> = {
      ...(task.inputParameters || {}),
      interactionType: 'APPROVAL',
      title: config.title,
      description: config.description || '',
      candidates: config.candidates,
      publicContext: config.publicContext,
    };
    if (config.timeoutSeconds) inputParameters.timeoutSeconds = config.timeoutSeconds;
    else delete inputParameters.timeoutSeconds;
    return { ...task, inputParameters };
  }).map((task, index, configured) => {
    if (index === 0 || configured[index - 1].taskReferenceName !== reference || task.type !== 'SWITCH') {
      return mapNested(task, configure);
    }
    const decisionCases = { ...(task.decisionCases || {}) };
    if (config.timeoutSeconds) {
      decisionCases.timeout = [];
    } else {
      delete decisionCases.timeout;
    }
    return { ...task, decisionCases };
  });

  const tasks = configure(definition.tasks);
  if (!found) throw new Error('找不到审批节点');
  return { ...definition, tasks };
}
