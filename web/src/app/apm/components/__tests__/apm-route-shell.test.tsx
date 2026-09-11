import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ApmRouteShell from '../apm-route-shell';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';

describe('ApmRouteShell', () => {
  it('不重复渲染二级页面介绍卡，同时保留无障碍页面标题', () => {
    const { container } = renderWithApmIntl(
      <ApmRouteShell
        title="服务"
        description="按应用与服务浏览最高活跃告警状态和 RED 指标。"
        dependency="telemetry"
      >
        <div>服务工作面</div>
      </ApmRouteShell>,
    );

    expect(screen.getByText('服务工作面')).toBeTruthy();
    expect(screen.queryByText('按应用与服务浏览最高活跃告警状态和 RED 指标。')).toBeNull();
    expect(container.querySelector('header')).toBeNull();
    expect(
      screen.getByRole('heading', { level: 1, name: '服务' }).classList.contains('sr-only'),
    ).toBe(true);
  });

  it('复用二级导航内容区的留白，页面壳不再二次水平缩进', () => {
    const { container } = renderWithApmIntl(
      <ApmRouteShell title="服务" description="服务目录">
        <div>服务工作面</div>
      </ApmRouteShell>,
    );

    const shell = container.firstElementChild;

    expect(shell?.classList.contains('px-4')).toBe(false);
    expect(shell?.classList.contains('lg:px-5')).toBe(false);
    expect(shell?.classList.contains('pb-4')).toBe(true);
    expect(shell?.classList.contains('p-4')).toBe(false);
    expect(Array.from(shell?.classList ?? []).some((className) => className.startsWith('px-'))).toBe(false);
    expect(Array.from(shell?.classList ?? []).some((className) => className.startsWith('pt-'))).toBe(false);
  });

  it('工作区占满可用宽度，超宽屏不再截断到 1920px', () => {
    const { container } = renderWithApmIntl(
      <ApmRouteShell title="服务" description="服务目录">
        <div>服务工作面</div>
      </ApmRouteShell>,
    );

    const workArea = container.firstElementChild?.firstElementChild;

    expect(workArea?.classList.contains('w-full')).toBe(true);
    expect(workArea?.classList.contains('min-w-0')).toBe(true);
    expect(Array.from(workArea?.classList ?? []).some((className) => className.startsWith('max-w-'))).toBe(false);
  });

  it('允许事件工作区关闭二次内边距，由页面分区自行管理留白', () => {
    const { container } = renderWithApmIntl(
      <ApmRouteShell title="告警" description="告警工作区" spacing="flush">
        <div>告警列表</div>
      </ApmRouteShell>,
    );

    const shell = container.firstElementChild;

    expect(shell?.classList.contains('min-h-0')).toBe(true);
    expect(shell?.classList.contains('px-4')).toBe(false);
    expect(shell?.classList.contains('pb-4')).toBe(false);
  });
});
