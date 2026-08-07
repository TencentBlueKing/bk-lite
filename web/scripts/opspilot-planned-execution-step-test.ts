import assert from 'node:assert/strict';

import {
  applyPlannedExecutionStep,
  attachToolCallToCurrentStep,
  createPlannedExecutionState,
  finalizePlannedExecutionSteps,
  isToolAssignedToPlannedStep,
  shouldExpandPlannedStep,
} from '../src/app/opspilot/components/custom-chat-sse/plannedExecutionState';
import { processHistoryMessageWithExtras } from '../src/app/opspilot/components/custom-chat-sse/historyMessageProcessor';

let state = createPlannedExecutionState();

state = applyPlannedExecutionStep(state, {
  phase: 'start',
  step_index: 1,
  total_steps: 3,
  objective: '获取集群现状',
  tools: ['list_namespaces'],
});

assert.equal(state.currentStepIndex, 1);
assert.equal(state.steps.length, 1);
assert.equal(state.steps[0].objective, '获取集群现状');
assert.equal(state.steps[0].status, 'running');
assert.equal(shouldExpandPlannedStep(state.steps[0], true), true);
assert.equal(shouldExpandPlannedStep(state.steps[0], false), false);

state = attachToolCallToCurrentStep(state, 'tool-a');
state = attachToolCallToCurrentStep(state, 'tool-a'); // idempotent
assert.deepEqual(state.steps[0].toolCallIds, ['tool-a']);
assert.equal(isToolAssignedToPlannedStep(state, 'tool-a'), true);
assert.equal(isToolAssignedToPlannedStep(state, 'tool-orphan'), false);

state = applyPlannedExecutionStep(state, {
  phase: 'end',
  step_index: 1,
  total_steps: 3,
  objective: '获取集群现状',
});
assert.equal(state.steps[0].status, 'done');
assert.equal(state.currentStepIndex, null);

state = applyPlannedExecutionStep(state, {
  phase: 'start',
  step_index: 2,
  total_steps: 3,
  objective: '定位异常 Pod',
});
state = attachToolCallToCurrentStep(state, 'tool-b');
assert.equal(state.steps.length, 2);
assert.deepEqual(state.steps[1].toolCallIds, ['tool-b']);
assert.equal(shouldExpandPlannedStep(state.steps[0], true), false);
assert.equal(shouldExpandPlannedStep(state.steps[1], true), true);

state = finalizePlannedExecutionSteps(state);
assert.equal(state.currentStepIndex, null);
assert.ok(state.steps.every((step) => step.status === 'done'));

// 完全无步骤时工具不挂组
const orphan = attachToolCallToCurrentStep(createPlannedExecutionState(), 'tool-x');
assert.equal(orphan.steps.length, 0);
assert.equal(orphan.currentStepIndex, null);

// 步骤已 end 后晚到的工具挂到最近一步
let lateState = createPlannedExecutionState();
lateState = applyPlannedExecutionStep(lateState, {
  phase: 'start',
  step_index: 1,
  total_steps: 1,
  objective: '获取当前时间',
  tools: ['get_current_time'],
});
lateState = applyPlannedExecutionStep(lateState, {
  phase: 'end',
  step_index: 1,
  total_steps: 1,
  objective: '获取当前时间',
});
assert.equal(lateState.currentStepIndex, null);
lateState = attachToolCallToCurrentStep(lateState, 'tool-late');
assert.deepEqual(lateState.steps[0].toolCallIds, ['tool-late']);

// 非法事件不破坏状态
const unchanged = applyPlannedExecutionStep(state, null as any);
assert.equal(unchanged.steps.length, state.steps.length);

// 历史回放：步骤边界 + 工具挂组，结束后默认非流式
const history = processHistoryMessageWithExtras(
  [
    { type: 'RUN_STARTED' },
    {
      type: 'CUSTOM',
      name: 'planned_execution_step',
      value: {
        phase: 'start',
        step_index: 1,
        total_steps: 2,
        objective: '获取集群现状',
        tools: ['list_namespaces'],
      },
    },
    { type: 'TOOL_CALL_START', toolCallId: 'tc-1', toolCallName: 'list_namespaces' },
    { type: 'TOOL_CALL_ARGS', toolCallId: 'tc-1', delta: '{"limit":10}' },
    { type: 'TOOL_CALL_RESULT', toolCallId: 'tc-1', content: 'ok' },
    { type: 'TOOL_CALL_END', toolCallId: 'tc-1' },
    {
      type: 'CUSTOM',
      name: 'planned_execution_step',
      value: {
        phase: 'end',
        step_index: 1,
        total_steps: 2,
        objective: '获取集群现状',
        tools: ['list_namespaces'],
      },
    },
    { type: 'TEXT_MESSAGE_CONTENT', delta: '最终结论' },
    { type: 'RUN_FINISHED' },
  ],
  'bot'
);

assert.equal(history.content.includes('最终结论'), true);
assert.equal(history.content.includes('<!--TOOL_CALLS:'), false, 'planned tools should not stay as flat TOOL_CALLS markers');
assert.ok(history.plannedExecutionSteps);
assert.equal(history.plannedExecutionSteps?.length, 1);
assert.equal(history.plannedExecutionSteps?.[0].objective, '获取集群现状');
assert.deepEqual(history.plannedExecutionSteps?.[0].toolCallIds, ['tc-1']);
assert.equal(history.plannedExecutionSteps?.[0].status, 'done');
assert.equal(history.isStreamingTools, false);
assert.equal(history.toolCalls?.find((t) => t.id === 'tc-1')?.name, 'list_namespaces');

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(process.cwd(), 'src/app/opspilot/components/custom-chat-sse');
const handler = readFileSync(join(root, 'aguiMessageHandler.ts'), 'utf8');
const ui = readFileSync(join(root, 'index.tsx'), 'utf8');
assert.match(handler, /planned_execution_step/);
assert.match(handler, /handlePlannedExecutionStep/);
assert.match(ui, /PlannedExecutionSteps/);

console.log('planned execution step state tests passed');
