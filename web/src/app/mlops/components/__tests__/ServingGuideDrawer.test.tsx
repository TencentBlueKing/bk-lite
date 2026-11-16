import { fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { describe, expect, it, vi } from 'vitest';

import { DatasetType } from '@/app/mlops/types';
import ServingGuideDrawer from '../ServingGuideDrawer';

vi.mock('../serving.module.scss', () => ({ default: { content: '' } }));

vi.mock('@/utils/request', () => ({
  default: () => ({
    get: vi.fn(),
    post: vi.fn(),
    del: vi.fn(),
    patch: vi.fn(),
  }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({ hasPermission: () => true }),
}));

const messages = {
  'serving-guide.capabilityTest': '在线测试',
  'serving-guide.sendRequest': '发送请求',
  'serving-guide.serviceNotRunning': '服务未运行，请先启动服务后再进行测试',
};

function renderDrawer(serving: { id: number; name: string; is_builtin?: boolean; container_info?: { state?: string } }) {
  return render(
    <IntlProvider locale="zh" messages={messages} onError={() => undefined}>
      <ServingGuideDrawer
        open
        onClose={() => undefined}
        algorithmType={DatasetType.TIMESERIES_PREDICT}
        serving={serving}
      />
    </IntlProvider>,
  );
}

function sendButton() {
  fireEvent.click(screen.getByText('在线测试'));
  return screen.getByRole('button', { name: /发送请求/ });
}

describe('ServingGuideDrawer 试调用', () => {
  it('内置发布不看容器状态，发送按钮可用', () => {
    renderDrawer({ id: 2, name: 'GradientBoosting', is_builtin: true, container_info: {} });

    expect(sendButton().hasAttribute('disabled')).toBe(false);
    expect(screen.queryByText('服务未运行，请先启动服务后再进行测试')).toBeNull();
  });

  it('普通发布未运行时不能发送', () => {
    renderDrawer({ id: 3, name: 'trained', container_info: { state: 'stopped' } });

    expect(sendButton().hasAttribute('disabled')).toBe(true);
    expect(screen.queryByText('服务未运行，请先启动服务后再进行测试')).not.toBeNull();
  });

  it('普通发布运行中可以发送', () => {
    renderDrawer({ id: 4, name: 'trained', container_info: { state: 'running' } });

    expect(sendButton().hasAttribute('disabled')).toBe(false);
    expect(screen.queryByText('服务未运行，请先启动服务后再进行测试')).toBeNull();
  });
});
