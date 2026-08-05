import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmIntegrationAddPage from '../page';

const api = {
  getApplications: vi.fn(),
  getCloudRegions: vi.fn(),
  getIngestSnippet: vi.fn(),
  isLoading: false,
};

vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getApplications.mockResolvedValue([
    {
      id: 'application-bklite',
      application_id: 'bklite',
      name: 'BK-Lite',
      description: '',
      is_builtin: false,
      service_count: 0,
      organization_ids: [1],
      created_at: '2026-08-05T00:00:00Z',
      updated_at: '2026-08-05T00:00:00Z',
      created_by: 'admin',
      updated_by: 'admin',
    },
  ]);
  api.getCloudRegions.mockResolvedValue([{ id: 1, name: '默认云区域' }]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 添加接入', () => {
  it('点击 SDK 接入方式后从右侧打开配置抽屉', async () => {
    const user = userEvent.setup();
    render(<ApmIntegrationAddPage />);

    await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));

    const panel = await screen.findByRole('dialog', { name: 'Node.js 接入' });
    expect(panel.closest('.ant-drawer-right')).not.toBeNull();
  });

  it('生成成功后才展示真实上报端点', async () => {
    api.getIngestSnippet.mockResolvedValue({
      application_id: 'bklite',
      application_name: 'BK-Lite',
      cloud_region: { id: 1, name: '默认云区域' },
      http_endpoint: 'http://proxy.example.com:4318/v1/traces',
      environment: {},
      code: 'export OTEL_SERVICE_NAME=checkout',
    });
    const user = userEvent.setup();
    render(<ApmIntegrationAddPage />);

    await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));
    expect(screen.queryByDisplayValue('生成配置后显示')).toBeNull();

    await user.type(screen.getByRole('textbox', { name: /服务名称/ }), 'checkout');
    await user.click(screen.getByRole('button', { name: /生成临时配置/ }));

    expect(await screen.findByDisplayValue('http://proxy.example.com:4318/v1/traces')).not.toBeNull();
    expect(screen.queryByText('OTLP/gRPC 端点')).toBeNull();
  });

  it('将运行方式呈现为有名称的表单选择组', async () => {
    const user = userEvent.setup();
    render(<ApmIntegrationAddPage />);

    await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));

    expect(screen.getByRole('radiogroup', { name: '运行方式' })).not.toBeNull();
  });

  it('将区域接收地址缺失转换为可恢复的用户提示', async () => {
    api.getIngestSnippet.mockRejectedValue({
      response: {
        data: {
          detail: '所选云区域没有可用的被动接收地址。',
        },
      },
    });
    const user = userEvent.setup();
    render(<ApmIntegrationAddPage />);

    await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));
    await user.type(screen.getByRole('textbox', { name: /服务名称/ }), 'checkout');
    await user.click(screen.getByRole('button', { name: /生成临时配置/ }));

    expect(await screen.findByText('所选云区域没有可用的接收地址，请联系管理员检查云区域代理配置后重试。')).not.toBeNull();
  });
});
