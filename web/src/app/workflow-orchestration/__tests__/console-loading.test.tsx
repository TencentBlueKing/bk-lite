import './test-mocks';

import { App } from 'antd';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { WorkflowOrchestrationConsole } from '../components/workflow-orchestration-console';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({
    get: vi.fn(() => new Promise(() => undefined)),
    patch: vi.fn(),
    post: vi.fn(),
  }),
}));

describe('编排画布加载态', () => {
  it('流程请求返回前不会读取尚不存在的画布元数据', () => {
    render(
      <App>
        <WorkflowOrchestrationConsole workflowId={1} />
      </App>,
    );

    expect(screen.getByLabelText('加载流程')).not.toBeNull();
  });
});
