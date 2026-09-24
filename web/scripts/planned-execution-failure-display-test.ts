import assert from 'node:assert/strict';

import {
  applyPlannedExecutionStep,
  createPlannedExecutionState,
  finalizePlannedExecutionSteps,
  isFailedPlannedStepStatus,
  isSkippedPlannedStepStatus,
} from '../src/app/opspilot/components/custom-chat-sse/plannedExecutionState';
import { isToolResultErrorContent } from '../src/app/opspilot/components/custom-chat-sse/toolResultStatus';

assert.equal(isFailedPlannedStepStatus('failed_config'), true);
assert.equal(isFailedPlannedStepStatus('missing_params'), true);
assert.equal(isFailedPlannedStepStatus('target_unresolved'), true);
assert.equal(isFailedPlannedStepStatus('skipped_context_overflow'), false);
assert.equal(isFailedPlannedStepStatus('done'), false);
assert.equal(isSkippedPlannedStepStatus('skipped_context_overflow'), true);
assert.equal(isSkippedPlannedStepStatus('failed_config'), false);

let state = createPlannedExecutionState();
state = applyPlannedExecutionStep(state, {
  phase: 'start',
  step_index: 2,
  total_steps: 2,
  objective: '诊断 Pod',
});
assert.equal(state.steps[0]?.status, 'running');

state = applyPlannedExecutionStep(state, {
  phase: 'end',
  step_index: 2,
  total_steps: 2,
  objective: '诊断 Pod',
  status: 'failed_config',
  error: '无法加载 Kubernetes 配置: Invalid base64',
});
assert.equal(state.steps[0]?.status, 'failed');
assert.match(state.steps[0]?.error || '', /无法加载 Kubernetes/);

state = finalizePlannedExecutionSteps(state);
assert.equal(state.steps[0]?.status, 'failed', 'finalize must keep failed steps');

assert.equal(isToolResultErrorContent('无法加载 Kubernetes 配置: Invalid base64'), true);
assert.equal(isToolResultErrorContent('{"phase":"Running"}'), false);

let overflow = createPlannedExecutionState();
overflow = applyPlannedExecutionStep(overflow, {
  phase: 'start',
  step_index: 1,
  total_steps: 2,
  objective: '查日志',
});
overflow = applyPlannedExecutionStep(overflow, {
  phase: 'end',
  step_index: 1,
  total_steps: 2,
  objective: '查日志',
  status: 'skipped_context_overflow',
  tools_invoked: [],
});
assert.equal(overflow.steps[0]?.status, 'skipped');
assert.ok(!overflow.steps[0]?.reusedPriorResult);
overflow = finalizePlannedExecutionSteps(overflow);
assert.equal(overflow.steps[0]?.status, 'skipped', 'finalize must keep skipped steps');

let missing = createPlannedExecutionState();
missing = applyPlannedExecutionStep(missing, {
  phase: 'end',
  step_index: 1,
  total_steps: 1,
  objective: '查指标',
  status: 'missing_params',
  tools_invoked: [],
});
assert.equal(missing.steps[0]?.status, 'failed');
assert.ok(!missing.steps[0]?.reusedPriorResult);

let reused = createPlannedExecutionState();
reused = applyPlannedExecutionStep(reused, {
  phase: 'end',
  step_index: 2,
  total_steps: 2,
  objective: '汇总',
  tools_invoked: [],
  outcome: 'reused_prior_result',
});
assert.equal(reused.steps[0]?.status, 'done');
assert.equal(reused.steps[0]?.reusedPriorResult, true);

let emptyToolsSuccess = createPlannedExecutionState();
emptyToolsSuccess = applyPlannedExecutionStep(emptyToolsSuccess, {
  phase: 'end',
  step_index: 1,
  total_steps: 1,
  objective: '寒暄',
  tools_invoked: [],
});
assert.equal(emptyToolsSuccess.steps[0]?.status, 'done');
assert.ok(!emptyToolsSuccess.steps[0]?.reusedPriorResult);

console.log('planned-execution-failure-display-test: ok');
