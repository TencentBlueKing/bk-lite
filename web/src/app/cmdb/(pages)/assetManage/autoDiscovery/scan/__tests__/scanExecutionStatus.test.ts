import { describe, expect, it } from 'vitest';

import {
  isScanExecuteDisabled,
  isScanExecutionBusy,
} from '../scanExecutionStatus';

describe('扫描执行状态', () => {
  it.each(['pending', 'running', 'finalizing'])('进行中状态 %s 视为忙碌', (status) => {
    expect(isScanExecutionBusy(status)).toBe(true);
  });

  it.each(['completed', 'failed', 'timed_out', '', undefined, null])(
    '终态或空状态 %s 不视为忙碌',
    (status) => {
      expect(isScanExecutionBusy(status)).toBe(false);
    }
  );

  it('最新执行为进行中时禁止再次点击执行', () => {
    expect(
      isScanExecuteDisabled({
        taskId: 1,
        executingTaskId: null,
        executionStatus: 'running',
      })
    ).toBe(true);
  });

  it('其它任务正在发起执行时禁止点击当前行', () => {
    expect(
      isScanExecuteDisabled({
        taskId: 1,
        executingTaskId: 2,
        executionStatus: 'completed',
      })
    ).toBe(true);
  });

  it('当前行请求进行中时仍允许由 loading 接管，不额外禁用', () => {
    expect(
      isScanExecuteDisabled({
        taskId: 1,
        executingTaskId: 1,
        executionStatus: 'completed',
      })
    ).toBe(false);
  });

  it('空闲任务可以执行', () => {
    expect(
      isScanExecuteDisabled({
        taskId: 1,
        executingTaskId: null,
        executionStatus: 'completed',
      })
    ).toBe(false);
  });
});
