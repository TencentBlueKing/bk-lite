import type { ConductorDefinition, ConductorTask } from './types';

export type ConditionLogic = 'ALL' | 'ANY';
export type ConditionOperator = 'EQ' | 'NEQ' | 'GT' | 'GTE' | 'LT' | 'LTE' | 'CONTAINS' | 'NOT_CONTAINS' | 'STARTS_WITH' | 'ENDS_WITH';

export interface ConditionRule {
  left: string;
  operator: ConditionOperator;
  rightKind: 'literal' | 'reference';
  right: unknown;
}

export interface ConditionConfiguration {
  logic: ConditionLogic;
  rules: ConditionRule[];
}

const OPERATOR_EXPRESSION: Record<ConditionOperator, (index: number) => string> = {
  EQ: (index) => `$.left_${index} == $.right_${index}`,
  NEQ: (index) => `$.left_${index} != $.right_${index}`,
  GT: (index) => `$.left_${index} > $.right_${index}`,
  GTE: (index) => `$.left_${index} >= $.right_${index}`,
  LT: (index) => `$.left_${index} < $.right_${index}`,
  LTE: (index) => `$.left_${index} <= $.right_${index}`,
  CONTAINS: (index) => `$.left_${index}.indexOf($.right_${index}) >= 0`,
  NOT_CONTAINS: (index) => `$.left_${index}.indexOf($.right_${index}) < 0`,
  STARTS_WITH: (index) => `$.left_${index}.indexOf($.right_${index}) == 0`,
  ENDS_WITH: (index) => `$.left_${index}.slice($.left_${index}.length - $.right_${index}.length) == $.right_${index}`,
};

function updateTasks(tasks: ConductorTask[], reference: string, config: ConditionConfiguration): [ConductorTask[], boolean] {
  let found = false;
  const visit = (items: ConductorTask[]): ConductorTask[] => items.map((task) => {
    if (task.taskReferenceName === reference) {
      if (task.type !== 'SWITCH') throw new Error('选中的节点不是条件分支');
      if (!config.rules.length || config.rules.length > 10) throw new Error('条件规则必须为 1 到 10 条');
      if (config.rules.some((rule) => {
        const rightReference = String(rule.right ?? '').trim();
        return !/^\$\{[^{}]+}$/.test(rule.left)
          || (rule.rightKind === 'reference' && Boolean(rightReference) && !/^\$\{[^{}]+}$/.test(rightReference));
      })) {
        throw new Error('条件只能使用结构化数据引用');
      }
      found = true;
      const inputParameters = Object.fromEntries(config.rules.flatMap((rule, index) => [
        [`left_${index}`, rule.left],
        [`right_${index}`, rule.right],
      ]));
      const separator = config.logic === 'ALL' ? ' && ' : ' || ';
      const expression = `(${config.rules.map((rule, index) => OPERATOR_EXPRESSION[rule.operator](index)).join(separator)}) ? 'true' : 'false'`;
      return {
        ...task,
        inputParameters,
        evaluatorType: 'javascript' as const,
        expression,
        decisionCases: { true: task.decisionCases?.true || [], false: task.decisionCases?.false || [] },
        defaultCase: [],
      };
    }
    const forkTasks = task.forkTasks?.map(visit);
    const decisionCases = task.decisionCases && Object.fromEntries(Object.entries(task.decisionCases).map(([key, branch]) => [key, visit(branch)]));
    const defaultCase = task.defaultCase && visit(task.defaultCase);
    return { ...task, ...(forkTasks ? { forkTasks } : {}), ...(decisionCases ? { decisionCases } : {}), ...(defaultCase ? { defaultCase } : {}) };
  });
  return [visit(tasks), found];
}

export function configureConditionTask(
  definition: ConductorDefinition,
  reference: string,
  config: ConditionConfiguration,
): ConductorDefinition {
  const [tasks, found] = updateTasks(definition.tasks, reference, config);
  if (!found) throw new Error('找不到条件节点');
  return { ...definition, tasks };
}
