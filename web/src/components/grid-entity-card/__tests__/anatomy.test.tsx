import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import GridEntityCard from '@/components/grid-entity-card';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }),
}));

vi.mock('@/components/ellipsis-with-tooltip', () => ({
  default: ({ text }: { text: string }) => <span>{text}</span>,
}));

afterEach(() => {
  cleanup();
});

describe('GridEntityCard', () => {
  it('keeps a compact catalog card without a reserved subline', () => {
    const { container } = render(
      <GridEntityCard name="电子邮件" description="通过 SMTP 发送邮件通知。" />,
    );

    expect(container.querySelector('article')?.className).toContain('min-h-[144px]');
    expect(screen.queryByText('已启动')).toBeNull();
  });

  it('renders status, origin, and entity footer when those slots have content', () => {
    render(
      <GridEntityCard
        name="CMDB"
        description="资产台账"
        statusTone="ok"
        statusLabel="已启动"
        origin="builtin"
        metaLabels={['资产数据']}
        footer="entity"
        owner="ops"
        team={['默认组织', '安全组']}
      />,
    );

    expect(screen.getByText('已启动')).toBeTruthy();
    expect(screen.getByText('资产数据')).toBeTruthy();
    expect(screen.getByText('ops')).toBeTruthy();
    expect(screen.getByText('+1')).toBeTruthy();
  });

  it('uses the fail token for error status', () => {
    const { container } = render(
      <GridEntityCard
        name="失败实例"
        statusTone="error"
        statusLabel="启动失败"
      />,
    );

    expect(container.querySelector('[aria-hidden]')?.className).toContain('bg-[var(--color-fail)]');
  });

  it('does not wrap a single team name in a tooltip', () => {
    const { container } = render(
      <GridEntityCard
        name="CMDB"
        footer="entity"
        owner="ops"
        team="默认组织"
      />,
    );

    expect(container.querySelector('.ant-tooltip')).toBeNull();
    expect(screen.getByText('默认组织')).toBeTruthy();
  });
});
