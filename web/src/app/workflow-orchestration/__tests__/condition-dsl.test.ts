import { describe, expect, it } from 'vitest';

import { configureConditionTask } from '../lib/condition-dsl';
import type { ConductorDefinition } from '../lib/types';

const definition: ConductorDefinition = {
  name: 'condition', version: 1, schemaVersion: 2,
  tasks: [{ name: 'condition', taskReferenceName: 'condition', type: 'SWITCH', decisionCases: { true: [], false: [] } }],
};

describe('结构化条件节点', () => {
  it('生成 Conductor 原生 SWITCH 定义而不保存自由表达式', () => {
    const configured = configureConditionTask(definition, 'condition', {
      logic: 'ALL',
      rules: [
        { left: '${scan.output.cpu}', operator: 'GTE', rightKind: 'literal', right: 80 },
        { left: '${workflow.input.region}', operator: 'EQ', rightKind: 'reference', right: '${target.output.region}' },
      ],
    });
    expect(configured.tasks[0]).toMatchObject({
      evaluatorType: 'javascript',
      inputParameters: { left_0: '${scan.output.cpu}', right_0: 80, left_1: '${workflow.input.region}', right_1: '${target.output.region}' },
      decisionCases: { true: [], false: [] },
    });
    expect(configured.tasks[0].expression).toBe("($.left_0 >= $.right_0 && $.left_1 == $.right_1) ? 'true' : 'false'");
  });

  it('拒绝非结构化引用', () => {
    expect(() => configureConditionTask(definition, 'condition', {
      logic: 'ANY', rules: [{ left: 'scan.cpu', operator: 'EQ', rightKind: 'literal', right: 80 }],
    })).toThrow('结构化');
  });

  it('允许字段引用在用户选择右值前保持空草稿', () => {
    const configured = configureConditionTask(definition, 'condition', {
      logic: 'ANY', rules: [{ left: '${system.execution_id}', operator: 'EQ', rightKind: 'reference', right: '' }],
    });

    expect(configured.tasks[0].inputParameters).toEqual({ left_0: '${system.execution_id}', right_0: '' });
  });

  it('仍然拒绝非空的非结构化右值引用', () => {
    expect(() => configureConditionTask(definition, 'condition', {
      logic: 'ANY', rules: [{ left: '${system.execution_id}', operator: 'EQ', rightKind: 'reference', right: 'scan.output.id' }],
    })).toThrow('结构化');
  });

  it('包含操作不引入隐式字符串转换', () => {
    const configured = configureConditionTask(definition, 'condition', {
      logic: 'ALL', rules: [{ left: '${scan.output.message}', operator: 'CONTAINS', rightKind: 'literal', right: 'error' }],
    });

    expect(configured.tasks[0].expression).toBe("($.left_0.indexOf($.right_0) >= 0) ? 'true' : 'false'");
  });

  it.each([
    ['NOT_CONTAINS', "($.left_0.indexOf($.right_0) < 0) ? 'true' : 'false'"],
    ['STARTS_WITH', "($.left_0.indexOf($.right_0) == 0) ? 'true' : 'false'"],
    ['ENDS_WITH', "($.left_0.slice($.left_0.length - $.right_0.length) == $.right_0) ? 'true' : 'false'"],
  ] as const)('支持 %s 字符串操作', (operator, expression) => {
    const configured = configureConditionTask(definition, 'condition', {
      logic: 'ALL', rules: [{ left: '${workflow.input.message}', operator, rightKind: 'literal', right: 'error' }],
    });

    expect(configured.tasks[0].expression).toBe(expression);
  });
});
