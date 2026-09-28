import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WebhookTriggerPanel } from '../components/webhook-trigger-panel';

const mocks = vi.hoisted(() => ({ get: vi.fn(), writeText: vi.fn() }));

vi.mock('@/utils/request', () => ({ default: () => ({ get: mocks.get }) }));

describe('Webhook 触发入口', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.writeText.mockReset();
    mocks.get.mockResolvedValue({
      count: 1,
      items: [{
        id: 'runtime-webhook-1',
        workflow: 6,
        workflow_name: '告警流程',
        node_key: 'trigger_webhook',
        name: '告警 Webhook',
        trigger_type: 'WEBHOOK',
        enabled: true,
        input_schema: {},
        default_inputs: {},
        config: { response_mode: 'IMMEDIATE' },
        idempotency_window_seconds: 3600,
        next_run_at: null,
        last_run_at: null,
      }],
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: mocks.writeText },
    });
  });

  it('测试入口说明 token 由平台生成、body 由调用方填写', () => {
    render(<App><WebhookTriggerPanel
      workflowId={6}
      nodeKey="trigger_webhook"
      currentVersion={0}
      testBusy={false}
      testError=""
      onCancelTest={vi.fn()}
    /></App>);

    expect(screen.getByText('参数说明')).not.toBeNull();
    expect(screen.getByText('token')).not.toBeNull();
    expect(screen.getByText('body')).not.toBeNull();
    expect(screen.getAllByText('平台生成')).toHaveLength(1);
    expect(screen.getAllByText('调用方填写').length).toBeGreaterThanOrEqual(2);
  });

  it('正式入口解释幂等键并可复制 curl', async () => {
    render(<App><WebhookTriggerPanel
      workflowId={6}
      nodeKey="trigger_webhook"
      currentVersion={2}
      testBusy={false}
      testError=""
      onCancelTest={vi.fn()}
    /></App>);

    fireEvent.click(screen.getByText('正式入口'));
    expect(await screen.findByText('idempotency_key')).not.toBeNull();
    expect(screen.getByText(/重试时复用同一值/)).not.toBeNull();
    await waitFor(() => expect(screen.getByText(/runtime-webhook-1/)).not.toBeNull());

    fireEvent.click(screen.getByRole('button', { name: '复制 curl' }));
    await waitFor(() => expect(mocks.writeText).toHaveBeenCalledWith(expect.stringContaining("curl --request POST")));
    expect(mocks.writeText.mock.calls[0][0]).toContain('Authorization: Bearer <API Token>');
  });
});
