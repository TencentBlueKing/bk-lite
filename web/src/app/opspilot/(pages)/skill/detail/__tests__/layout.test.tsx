import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SkillSettingsLayout from '../layout';

const mockPush = vi.fn();
let mockPathname = '/opspilot/skill/detail/settings';
let mockSearchParams = new URLSearchParams('id=48');

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
}));

vi.mock('@/context/permissions', () => ({
  usePermissions: () => ({
    menus: [],
    loading: false,
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback || key,
  }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type, className }: { type: string; className?: string }) => (
    <span data-testid={`icon-${type}`} className={className} />
  ),
}));

const mockSkillInfo = {
  name: 'IT运维助手',
  introduction: '智能运维问答助手',
};

vi.mock('@/app/opspilot/context/skillContext', () => ({
  SkillProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useSkill: () => ({
    skillInfo: mockSkillInfo,
    isLoading: false,
    refreshSkillInfo: vi.fn(),
  }),
}));

describe('SkillSettingsLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPathname = '/opspilot/skill/detail/settings';
    mockSearchParams = new URLSearchParams('id=48');
  });

  afterEach(() => {
    cleanup();
  });

  it('renders unified sidebar intro matching list cards without displaying ID', () => {
    render(
      <SkillSettingsLayout>
        <div data-testid="workbench-content">Studio Content</div>
      </SkillSettingsLayout>
    );

    // Displays name and description
    expect(screen.getByText('IT运维助手')).toBeTruthy();
    expect(screen.getByText('智能运维问答助手')).toBeTruthy();

    // ID is completely omitted as requested
    expect(screen.queryByText(/ID/)).toBeNull();

    // Compact icon, no background plate — same pool/algorithm as list cards
    const icon = screen.getByTestId(/^icon-jiqiren/);
    expect(icon).toBeTruthy();
    expect(icon.className).toContain('text-base');
    expect(icon.className).toContain('text-[var(--color-primary)]');
    expect(icon.parentElement?.className ?? '').not.toMatch(/bg-\[var\(--color-fill/);

    // 3-level SideMenu navigation items
    const settingsMenu = screen.getByText('设置');
    const channelMenu = screen.getByText('发布');
    expect(settingsMenu).toBeTruthy();
    expect(channelMenu).toBeTruthy();

    const settingsLink = settingsMenu.closest('a');
    const channelLink = channelMenu.closest('a');
    expect(settingsLink?.getAttribute('href')).toContain('/opspilot/skill/detail/settings?id=48');
    expect(channelLink?.getAttribute('href')).toContain('/opspilot/skill/detail/channel?id=48');
    expect(screen.getByTestId('icon-settings-fill')).toBeTruthy();

    expect(screen.getByTestId('workbench-content')).toBeTruthy();

    // Unified left block: subtle divider line with comfortable spacing (Option B)
    const separator = document.querySelector('[role="separator"]');
    expect(separator).toBeTruthy();
    expect(separator?.className).toContain('border-[var(--color-border-2)]');
    expect(screen.queryByText('IT运维助手')?.closest('.bg-\\[var\\(--color-fill-1\\)\\]')).toBeNull();
  }, 20000);

  it('navigates back to /opspilot/skill when back button is clicked', () => {
    const { container } = render(
      <SkillSettingsLayout>
        <div>Content</div>
      </SkillSettingsLayout>
    );

    const backBtn = container.querySelector('button.absolute.bottom-4.left-4') || screen.getByRole('button');
    expect(backBtn).toBeTruthy();
    if (backBtn) {
      fireEvent.click(backBtn);
      expect(mockPush).toHaveBeenCalledWith('/opspilot/skill');
    }
  }, 20000);
});
