import '@ant-design/v5-patch-for-react-19';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ScreenToolbar from '../screenToolbar';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/components/permission', () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@/components/time-selector', () => ({
  default: () => null,
}));

const renderViewToolbar = (
  props: Partial<React.ComponentProps<typeof ScreenToolbar>> = {},
) => render(
  <ScreenToolbar
    editMode={false}
    onOpenSettings={() => undefined}
    onOpenFilterConfig={() => undefined}
    onPreview={() => undefined}
    onRefresh={() => undefined}
    onEdit={() => undefined}
    onCancel={() => undefined}
    onSave={() => undefined}
    onOpenShare={() => undefined}
    onOpenDisplay={() => undefined}
    {...props}
  />,
);

describe('screen display toolbar', () => {
  it('shows cast beside share on the view toolbar', () => {
    renderViewToolbar();
    expect(screen.getByRole('button', { name: 'opsAnalysis.screen.displayTitle' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'dashboard.share' })).toBeTruthy();
  });

  it('hides cast while the screen is already a shared or cast display', () => {
    renderViewToolbar({ shareMode: true });
    expect(screen.queryByRole('button', { name: 'opsAnalysis.screen.displayTitle' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'dashboard.share' })).toBeNull();
  });
});
