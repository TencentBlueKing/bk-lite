import '@ant-design/v5-patch-for-react-19';
import './test-mocks';

import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { WorkflowFormPage } from '../components/workflow-form-page';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/utils/request', () => ({ default: () => ({ get: mocks.get, post: mocks.post }) }));

describe('表单触发器入口', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })),
    });
  });

  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.push.mockReset();
    mocks.get.mockResolvedValue({
      id: 8,
      name: '巡检流程',
      description: '收集主机名',
      current_version: 2,
      canvas_metadata: {
        trigger_nodes: [{
          id: 'trigger_form',
          name: '巡检表单',
          trigger_type: 'FORM',
          input_schema: { type: 'object', properties: { hostname: { type: 'string', title: '主机名' } }, required: ['hostname'] },
          config: {},
        }],
      },
    });
    mocks.post.mockResolvedValue({ id: 'execution-1' });
  });

  it('按 Schema 生成测试页，提交后启动草稿调试', async () => {
    render(<App><WorkflowFormPage mode="test" workflowId={8} nodeKey="trigger_form" /></App>);

    expect(await screen.findByRole('heading', { name: '巡检表单' })).not.toBeNull();
    expect(screen.queryByRole('region', { name: '入口地址' })).toBeNull();
    expect(mocks.get).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText('主机名'), { target: { value: 'db-01' } });
    fireEvent.click(screen.getByRole('button', { name: /send提交/ }));

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(
      '/workflow_orchestration/api/workflows/8/debug/',
      { inputs: { hostname: 'db-01' }, trigger_id: 'trigger_form' },
    ));
    expect(await screen.findByText('调试执行已启动')).not.toBeNull();
  });
});
