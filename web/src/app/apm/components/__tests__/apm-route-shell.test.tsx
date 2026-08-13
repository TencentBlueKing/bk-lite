import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ApmRouteShell from '../apm-route-shell';

describe('ApmRouteShell', () => {
  it('不重复渲染二级页面介绍卡，同时保留无障碍页面标题', () => {
    const { container } = render(
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

  it('复用二级导航内容区的顶部留白，不再叠加页面壳顶部内边距', () => {
    const { container } = render(
      <ApmRouteShell title="服务" description="服务目录">
        <div>服务工作面</div>
      </ApmRouteShell>,
    );

    const shell = container.firstElementChild;

    expect(shell?.classList.contains('px-4')).toBe(true);
    expect(shell?.classList.contains('pb-4')).toBe(true);
    expect(shell?.classList.contains('p-4')).toBe(false);
    expect(Array.from(shell?.classList ?? []).some((className) => className.startsWith('pt-'))).toBe(false);
  });
});
