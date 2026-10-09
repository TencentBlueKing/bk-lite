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

const renderToolbar = (
  props: Partial<React.ComponentProps<typeof ScreenToolbar>> = {},
) => render(
  <ScreenToolbar
    editMode
    onOpenSettings={() => undefined}
    onOpenFilterConfig={() => undefined}
    onPreview={() => undefined}
    onRefresh={() => undefined}
    onEdit={() => undefined}
    onCancel={() => undefined}
    onSave={() => undefined}
    canUndo={false}
    canRedo={false}
    onUndo={() => undefined}
    onRedo={() => undefined}
    {...props}
  />,
);

describe('screen edit history toolbar', () => {
  it('puts undo and redo ahead of the canvas tools and disables them when unavailable', () => {
    renderToolbar();
    const labels = screen.getAllByRole('button').map((button) => button.getAttribute('aria-label'));
    expect(labels.slice(0, 2)).toEqual([
      'opsAnalysis.screen.undo',
      'opsAnalysis.screen.redo',
    ]);
    expect(labels.indexOf('opsAnalysis.screen.undo')).toBeLessThan(
      labels.indexOf('opsAnalysis.screen.canvasSettings'),
    );
    expect(screen.getByRole('button', { name: 'opsAnalysis.screen.undo' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button', { name: 'opsAnalysis.screen.redo' }).hasAttribute('disabled')).toBe(true);
  });

  it('hides undo and redo while viewing or sharing', () => {
    const { rerender } = renderToolbar({ editMode: false });
    expect(screen.queryByRole('button', { name: 'opsAnalysis.screen.undo' })).toBeNull();

    rerender(
      <ScreenToolbar
        editMode
        shareMode
        onOpenSettings={() => undefined}
        onOpenFilterConfig={() => undefined}
        onPreview={() => undefined}
        onRefresh={() => undefined}
        onEdit={() => undefined}
        onCancel={() => undefined}
        onSave={() => undefined}
        onUndo={() => undefined}
        onRedo={() => undefined}
      />,
    );
    expect(screen.queryByRole('button', { name: 'opsAnalysis.screen.undo' })).toBeNull();
  });
});
