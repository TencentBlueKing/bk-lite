import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { FormTriggerAccessPanel } from '../components/form-trigger-access-panel';

const mocks = vi.hoisted(() => ({ get: vi.fn(), writeText: vi.fn() }));

vi.mock('@/utils/request', () => ({ default: () => ({ get: mocks.get }) }));

describe('表单触发器入口', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.writeText.mockReset();
    mocks.get.mockResolvedValue({
      count: 1,
      items: [{
        id: 'runtime-trigger-1',
        workflow: 6,
        workflow_name: '巡检流程',
        node_key: 'trigger_form',
        name: '巡检表单',
        trigger_type: 'FORM',
        enabled: true,
        input_schema: {},
        default_inputs: {},
        config: {},
        idempotency_window_seconds: 300,
        next_run_at: null,
        last_run_at: null,
      }],
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: mocks.writeText },
    });
  });

  it('纯草稿只显示草稿预览入口', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(
      <App>
        <FormTriggerAccessPanel workflowId={6} nodeKey="trigger_form" currentVersion={0} hasDraft />
      </App>,
    );

    expect(screen.getByText('草稿预览')).not.toBeNull();
    expect(screen.getByText('使用已保存草稿')).not.toBeNull();
    expect(screen.queryByText('正式入口')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(mocks.get).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '查看草稿预览' }));
    expect(open).toHaveBeenCalledWith('/workflow-orchestration/forms/test/6/trigger_form', '_blank', 'noopener,noreferrer');

    fireEvent.click(screen.getByRole('button', { name: '复制草稿预览链接' }));
    await waitFor(() => expect(mocks.writeText).toHaveBeenCalledWith('http://localhost:3000/workflow-orchestration/forms/test/6/trigger_form'));
    open.mockRestore();
  });

  it('已发布且没有草稿修改时只显示正式入口', async () => {
    render(
      <App>
        <FormTriggerAccessPanel workflowId={6} nodeKey="trigger_form" currentVersion={2} hasDraft={false} />
      </App>,
    );

    expect(screen.getByText('正式入口')).not.toBeNull();
    expect(screen.getByText('指向最新发布版本')).not.toBeNull();
    expect(screen.queryByText('草稿预览')).toBeNull();
    await waitFor(() => expect((screen.getByRole('button', { name: '查看正式入口' }) as HTMLButtonElement).disabled).toBe(false));
    expect(mocks.get).toHaveBeenCalledTimes(1);
  });

  it('已发布且有草稿修改时允许切换入口，但一次只展示一个', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(
      <App>
        <FormTriggerAccessPanel workflowId={6} nodeKey="trigger_form" currentVersion={2} hasDraft />
      </App>,
    );

    expect(screen.getByRole('radio', { name: '草稿预览' })).not.toBeNull();
    expect(screen.getByRole('radio', { name: '正式入口' })).not.toBeNull();
    expect(screen.getByText('使用已保存草稿')).not.toBeNull();
    expect(screen.queryByText('指向最新发布版本')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: '正式入口' }).closest('label')!);
    expect(screen.queryByText('使用已保存草稿')).toBeNull();
    expect(screen.getByText('指向最新发布版本')).not.toBeNull();

    const productionOpen = await screen.findByRole('button', { name: '查看正式入口' });
    await waitFor(() => expect((productionOpen as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(productionOpen);
    expect(open).toHaveBeenCalledWith('/workflow-orchestration/forms/runtime-trigger-1', '_blank', 'noopener,noreferrer');

    fireEvent.mouseEnter(screen.getByRole('button', { name: '复制正式入口链接' }));
    expect((await screen.findByRole('tooltip')).textContent).toContain('复制正式入口链接');
    expect(mocks.get).toHaveBeenCalledTimes(1);
    open.mockRestore();
  });
});
