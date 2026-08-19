import assert from 'node:assert/strict';

import {
  applyPlannedExecutionStep,
  createPlannedExecutionState,
  finalizePlannedExecutionSteps,
  isFailedPlannedStepStatus,
} from '../src/app/opspilot/components/custom-chat-sse/plannedExecutionState';
import { isToolResultErrorContent } from '../src/app/opspilot/components/custom-chat-sse/toolResultStatus';

assert.equal(isFailedPlannedStepStatus('failed_config'), true);
assert.equal(isFailedPlannedStepStatus('done'), false);

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

console.log('planned-execution-failure-display-test: ok');
