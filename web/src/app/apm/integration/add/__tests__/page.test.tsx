import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
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

function renderPage() {
  return render(
    <IntlProvider locale="zh" messages={{
      'apm.integration.copyEndpoint': '复制 HTTP 上报端点',
      'apm.integration.copyEndpointSuccess': 'HTTP 上报端点已复制',
      'apm.integration.copyFailure': '复制失败，请手动选择并复制',
      'apm.integration.copyShellSnippet': '复制 Shell 接入片段',
      'apm.integration.copyShellSnippetSuccess': 'Shell 接入片段已复制',
      'apm.integration.instanceIdentityHelp': '实例 ID 在应用进程启动时生成，每个副本唯一。',
    }}>
      <ApmIntegrationAddPage />
    </IntlProvider>
  );
}

async function generateSnippet(code = 'export FIRST=1\nexport SECOND=2') {
  api.getIngestSnippet.mockResolvedValue({
    application_id: 'bklite',
    application_name: 'BK-Lite',
    cloud_region: { id: 1, name: '默认云区域' },
    http_endpoint: 'http://proxy.example.com:4318/v1/traces',
    environment: {},
    code,
  });
  const user = userEvent.setup();
  renderPage();
  await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));
  await user.type(screen.getByRole('textbox', { name: /服务名称/ }), 'checkout');
  await user.click(screen.getByRole('button', { name: /生成临时配置/ }));
  await screen.findByDisplayValue('http://proxy.example.com:4318/v1/traces');
  expect(document.querySelector('pre code')?.textContent).toBe(code);
  return user;
}

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
    renderPage();

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
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));
    expect(screen.queryByDisplayValue('生成配置后显示')).toBeNull();

    await user.type(screen.getByRole('textbox', { name: /服务名称/ }), 'checkout');
    await user.click(screen.getByRole('button', { name: /生成临时配置/ }));

    expect(await screen.findByDisplayValue('http://proxy.example.com:4318/v1/traces')).not.toBeNull();
    expect(screen.queryByText('OTLP/gRPC 端点')).toBeNull();
    const snippetToolbar = screen.getByRole('group', { name: 'Shell 接入片段' });
    expect(within(snippetToolbar).getByRole('button', { name: '复制 Shell 接入片段' })).not.toBeNull();
  });

  it('将运行方式呈现为有名称的表单选择组', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));

    expect(screen.getByRole('radiogroup', { name: '运行方式' })).not.toBeNull();
    expect(screen.getByRole('radio', { name: 'Kubernetes Pod（Downward API）' })).not.toBeNull();
  });

  it('选择 Kubernetes SDK 运行方式后请求 Pod 运行时配置', async () => {
    api.getIngestSnippet.mockResolvedValue({
      application_id: 'bklite',
      application_name: 'BK-Lite',
      cloud_region: { id: 1, name: '默认云区域' },
      http_endpoint: 'http://proxy.example.com:4318/v1/traces',
      environment: {},
      code: 'spec:\n  template: {}',
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Python 接入' }));
    await user.click(screen.getByText('Kubernetes Pod（Downward API）'));
    await user.type(screen.getByRole('textbox', { name: /服务名称/ }), 'checkout');
    await user.click(screen.getByRole('button', { name: /生成临时配置/ }));

    expect(api.getIngestSnippet).toHaveBeenCalledWith(expect.objectContaining({
      language: 'python',
      runtime: 'kubernetes',
    }));
    expect(await screen.findByText('Kubernetes 配置片段')).not.toBeNull();
  });

  it('明确把 Go 呈现为手动 SDK 接入而不是自动探针', async () => {
    api.getIngestSnippet.mockResolvedValue({
      application_id: 'bklite',
      application_name: 'BK-Lite',
      cloud_region: { id: 1, name: '默认云区域' },
      http_endpoint: 'http://proxy.example.com:4318/v1/traces',
      environment: {},
      code: 'Go 无通用零代码探针',
    });
    const user = userEvent.setup();
    renderPage();

    expect((await screen.findAllByText('手动 SDK')).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: 'Go 接入' }));
    expect(screen.getByRole('radio', { name: 'Go 手动 SDK' })).not.toBeNull();
    expect(screen.queryByRole('radio', { name: 'Go 自动探针' })).toBeNull();
    await user.type(screen.getByRole('textbox', { name: /服务名称/ }), 'checkout');
    await user.click(screen.getByRole('button', { name: /生成临时配置/ }));

    expect(await screen.findByText('Go SDK 接入指南')).not.toBeNull();
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
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Node.js 接入' }));
    await user.type(screen.getByRole('textbox', { name: /服务名称/ }), 'checkout');
    await user.click(screen.getByRole('button', { name: /生成临时配置/ }));

    expect(await screen.findByText('所选云区域没有可用的接收地址，请联系管理员检查云区域代理配置后重试。')).not.toBeNull();
  });

  it('复制完整 Shell 代码并反馈成功', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const code = 'export FIRST=1\nexport SECOND=2\npython app.py';
    const user = await generateSnippet(code);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });

    await user.click(screen.getByRole('button', { name: '复制 Shell 接入片段' }));

    expect(writeText).toHaveBeenCalledWith(code);
    expect(await screen.findByText('Shell 接入片段已复制')).not.toBeNull();
  });

  it('Clipboard API 不可用时使用受控的浏览器降级复制', async () => {
    const execCommand = vi.fn().mockReturnValue(true);
    const user = await generateSnippet();
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand });

    await user.click(screen.getByRole('button', { name: '复制 Shell 接入片段' }));

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(await screen.findByText('Shell 接入片段已复制')).not.toBeNull();
    expect(document.querySelector('textarea')).toBeNull();
  });

  it('降级复制失败时反馈失败并清理临时文本框', async () => {
    const user = await generateSnippet();
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    Object.defineProperty(document, 'execCommand', { configurable: true, value: vi.fn().mockReturnValue(false) });

    await user.click(screen.getByRole('button', { name: '复制 Shell 接入片段' }));

    expect(await screen.findByText('复制失败，请手动选择并复制')).not.toBeNull();
    expect(document.querySelector('textarea')).toBeNull();
  });
});
