import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { IntlProvider } from 'react-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ExecutionLifecycleActions } from '../components/execution-lifecycle-actions';
import { ExecutionTerminationResidualAlert } from '../components/execution-termination-residual-alert';
import type { ExecutionRecord } from '../lib/types';

const mocks = vi.hoisted(() => {
  const post = vi.fn();
  return { post, api: { get: vi.fn(), post, patch: vi.fn() } };
});

vi.mock('@/utils/request', () => ({
  default: () => mocks.api,
}));

function baseExecution(overrides: Partial<ExecutionRecord> = {}): ExecutionRecord {
  return {
    id: 'execution-1',
    workflow: 1,
    workflow_name: '巡检流程',
    workflow_deleted: false,
    workflow_enabled: true,
    workflow_version: 3,
    conductor_workflow_id: 'c-1',
    status: 'RUNNING',
    trigger_type: 'FORM',
    mode: 'PRODUCTION',
    has_warnings: false,
    warning_count: 0,
    input: {},
    output: {},
    tasks: [],
    definition_snapshot: { tasks: [] },
    resource_snapshot: {},
    target_snapshot: { fields: {}, unique_total: 0 },
    atom_executions: [],
    artifacts: [],
    error_message: '',
    termination_reason: '',
    started_by: 'alice',
    created_at: '2026-11-02T01:00:00Z',
    finished_at: null,
    duration_ms: null,
    updated_at: '2026-11-02T01:00:00Z',
    permission: ['View', 'Execute'],
    ...overrides,
  };
}

function wrap(node: ReactNode) {
  return (
    <IntlProvider locale="zh-CN" messages={{}}>
      <App>{node}</App>
    </IntlProvider>
  );
}

describe('ExecutionTerminationResidualAlert', () => {
  it('still renders residual facts for a later UI pass', () => {
    render(wrap(
      <ExecutionTerminationResidualAlert
        execution={baseExecution({
          status: 'TERMINATED',
          termination_reason: '发布回滚',
          output: {
            termination_job_cancels: [
              { task_id: 101, ok: true },
              { task_id: 102, ok: false },
            ],
          },
        })}
      />,
    ));
    expect(screen.getByTestId('execution-termination-residual-alert').textContent).toContain('仍有 1 个关联作业未能确认停止');
  });
});

describe('ExecutionLifecycleActions terminate messaging', () => {
  beforeEach(() => {
    mocks.post.mockReset();
  });

  it('shows one-paragraph terminate hint and always success toast', async () => {
    mocks.post.mockResolvedValue(baseExecution({
      status: 'TERMINATING',
      termination_reason: '发布回滚',
      output: {
        termination_job_cancels: [
          { task_id: 101, ok: true },
          { task_id: 102, ok: false },
        ],
      },
    }));

    render(wrap(
      <ExecutionLifecycleActions execution={baseExecution()} presentation="menu" />,
    ));

    fireEvent.click(screen.getByRole('button', { name: /终止/ }));
    expect(screen.getByText(/流程将停止继续执行，并尽量停止已下发的关联作业/)).not.toBeNull();
    expect(screen.queryByText(/目标机上可能仍有任务在跑/)).toBeNull();
    fireEvent.change(screen.getByPlaceholderText('请输入终止原因'), { target: { value: '发布回滚' } });
    fireEvent.click(screen.getByRole('button', { name: /确认终止/ }));

    await waitFor(() => {
      expect(screen.getByText('已提交终止请求')).not.toBeNull();
    });
    expect(screen.queryByText('已终止，但有关联作业未确认停止，请查看执行详情')).toBeNull();
    expect(mocks.post).toHaveBeenCalledWith(
      '/workflow/api/executions/execution-1/terminate/',
      { reason: '发布回滚' },
    );
  });
});
