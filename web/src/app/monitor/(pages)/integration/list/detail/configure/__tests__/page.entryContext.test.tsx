import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Configure from '../page';

const navigationMocks = vi.hoisted(() => ({
  searchParams: new URLSearchParams()
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => navigationMocks.searchParams
}));

vi.mock('@/app/monitor/hooks/integration/common/getObjectConfig', () => ({
  useObjectConfigInfo: () => ({
    ready: true,
    getCollectType: () => 'k8s'
  })
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === 'monitor.integrations.missingEntryContext'
        ? '缺少插件关联的监控对象，无法进入配置'
        : key
  })
}));

vi.mock('../automatic', () => ({ default: () => <div>automatic</div> }));
vi.mock('../k8s/k8sConfiguration', () => ({
  default: () => <div data-testid="k8s-configuration" />
}));
vi.mock('../k3s/k3sConfiguration', () => ({ default: () => <div>k3s</div> }));
vi.mock('../flow/flowConfiguration', () => ({ default: () => <div>flow</div> }));
vi.mock('../accessGuide/index', () => ({ default: () => <div>api</div> }));

afterEach(() => {
  cleanup();
  navigationMocks.searchParams = new URLSearchParams();
});

describe('集成配置入口上下文', () => {
  it('缺少对象 ID 时显示错误且不渲染配置表单', () => {
    navigationMocks.searchParams = new URLSearchParams({
      name: 'Cluster',
      plugin_name: 'K8S',
      plugin_id: '297'
    });

    render(<Configure />);

    expect(
      screen.getByText('缺少插件关联的监控对象，无法进入配置')
    ).toBeTruthy();
    expect(screen.queryByTestId('k8s-configuration')).toBeNull();
  });

  it('上下文完整时渲染 K8s 配置', () => {
    navigationMocks.searchParams = new URLSearchParams({
      id: '12',
      name: 'Cluster',
      plugin_name: 'K8S',
      plugin_id: '297'
    });

    render(<Configure />);

    expect(screen.getByTestId('k8s-configuration')).toBeTruthy();
  });
});
