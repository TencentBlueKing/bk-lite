import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'opsHomepage.openInAnalysis': '在运营分析中打开',
      'opsHomepage.moreActions': '更多操作',
      'opsHomepage.pinWorkbench': '恢复工作台首页',
    }[key] ?? key),
  }),
}));

import HomepageViewToolbar from '../homepageViewToolbar';

afterEach(() => {
  cleanup();
});

describe('HomepageViewToolbar', () => {
  it('keeps only the link that opens the dashboard in operations analysis', () => {
    render(<HomepageViewToolbar dashboardId="42" />);

    const openLink = screen.getByRole('link', { name: /在运营分析中打开/ });
    expect(openLink.getAttribute('href')).toBe('/ops-analysis/view?type=dashboard&id=dashboard_42');
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByText('恢复工作台首页')).toBeNull();
  });

  it('renders nothing until a dashboard id is known', () => {
    const { container } = render(<HomepageViewToolbar />);
    expect(container.childElementCount).toBe(0);
  });
});
