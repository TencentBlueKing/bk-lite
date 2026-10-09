import '@ant-design/v5-patch-for-react-19';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ScreenElementPalette } from '../screenEditorPanels';
import { createScreenTextItem } from '../../utils/screenItems';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('screen element palette', () => {
  it('opens a flyout beside the rail and closes it after placing a frame', async () => {
    const user = userEvent.setup();
    const onAddDecoration = vi.fn();
    const onSelectItem = vi.fn();
    render(
      <div>
        <ScreenElementPalette
          items={[createScreenTextItem([], { id: 'text-1', content: '说明' })]}
          selectedItemId={null}
          onSelectItem={onSelectItem}
          onAddText={() => undefined}
          onAddClock={() => undefined}
          onAddTitleFrame={() => undefined}
          onAddDecoration={onAddDecoration}
          onAddShape={() => undefined}
          onOpenChartSelector={() => undefined}
          onOpenItemMenu={() => undefined}
          onReorderItem={() => undefined}
        />
        <button type="button">画布</button>
      </div>,
    );

    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();
    expect(screen.queryByText('opsAnalysis.screen.elementCorner')).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.titleFrame.hero-6')).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.panelFrame.border-22')).toBeNull();

    await user.click(screen.getByRole('button', { name: '说明' }));
    expect(onSelectItem).toHaveBeenCalledWith('text-1');

    await user.click(
      screen.getByRole('button', { name: 'opsAnalysis.screen.elementPanelFrame' }),
    );
    expect(screen.getByText('opsAnalysis.screen.panelFrame.border-24')).toBeTruthy();
    expect(screen.queryByText('opsAnalysis.screen.titleFrame.hero-6')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'opsAnalysis.screen.elementTitle' }));
    expect(screen.getByText('opsAnalysis.screen.titleFrame.hero-6')).toBeTruthy();
    expect(document.querySelector('[data-title-frame-thumb="hero-1"]')).toBeTruthy();
    expect(document.querySelector('[data-title-frame-thumb="section-4"]')).toBeTruthy();
    expect(screen.queryByText('opsAnalysis.screen.panelFrame.border-22')).toBeNull();

    await user.click(
      screen.getByRole('button', { name: 'opsAnalysis.screen.elementPanelFrame' }),
    );
    await user.click(screen.getByText('opsAnalysis.screen.panelFrame.border-22'));
    expect(onAddDecoration).toHaveBeenCalledWith('panelFrame', 'border-22');
    expect(screen.queryByText('opsAnalysis.screen.panelFrame.border-24')).toBeNull();

    await user.click(
      screen.getByRole('button', { name: 'opsAnalysis.screen.elementDivider' }),
    );
    const flyout = document.querySelector('[data-screen-catalog-flyout]');
    expect(flyout).toBeTruthy();
    expect(flyout?.className).not.toContain('h-full');
    expect(flyout?.getAttribute('style')).toContain('max-height');
    expect(screen.getByText('opsAnalysis.screen.divider.line-4')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '画布' }));
    expect(screen.queryByText('opsAnalysis.screen.divider.line-4')).toBeNull();
    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();
  }, 15000);

  it('draws the circle thumbnail as a square and leaves the rectangle wide', async () => {
    const user = userEvent.setup();
    render(
      <ScreenElementPalette
        items={[]}
        selectedItemId={null}
        onSelectItem={() => undefined}
        onAddText={() => undefined}
        onAddClock={() => undefined}
        onAddTitleFrame={() => undefined}
        onAddDecoration={() => undefined}
        onAddShape={() => undefined}
        onOpenChartSelector={() => undefined}
        onOpenItemMenu={() => undefined}
        onReorderItem={() => undefined}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'opsAnalysis.screen.elementShape' }));
    expect(document.querySelector('[data-shape-thumb="circle"]')?.className).toContain(
      'aspect-square',
    );
    expect(document.querySelector('[data-shape-thumb="rect"]')?.className).toContain(
      'w-full',
    );
    expect(document.querySelector('[data-shape-thumb="rect"]')?.className).not.toContain(
      'aspect-square',
    );
  });

  it('opens the shared menu from the list row and does not show a delete icon', () => {
    const onOpenItemMenu = vi.fn();
    render(
      <ScreenElementPalette
        items={[createScreenTextItem([], { id: 'text-1', content: '说明' })]}
        selectedItemId="text-1"
        onSelectItem={() => undefined}
        onAddText={() => undefined}
        onAddClock={() => undefined}
        onAddTitleFrame={() => undefined}
        onAddDecoration={() => undefined}
        onAddShape={() => undefined}
        onOpenChartSelector={() => undefined}
        onOpenItemMenu={onOpenItemMenu}
        onReorderItem={() => undefined}
      />,
    );

    expect(screen.queryByRole('button', { name: 'common.delete' })).toBeNull();
    fireEvent.contextMenu(screen.getByRole('button', { name: '说明' }));
    expect(onOpenItemMenu).toHaveBeenCalledWith('text-1', expect.any(Object));
  });

  it('opens the chart selector from the sidebar and does not open a catalog', async () => {
    const user = userEvent.setup();
    const onOpenChartSelector = vi.fn();
    render(
      <ScreenElementPalette
        items={[]}
        selectedItemId={null}
        onSelectItem={() => undefined}
        onAddText={() => undefined}
        onAddClock={() => undefined}
        onAddTitleFrame={() => undefined}
        onAddDecoration={() => undefined}
        onAddShape={() => undefined}
        onOpenChartSelector={onOpenChartSelector}
        onOpenItemMenu={() => undefined}
        onReorderItem={() => undefined}
      />,
    );

    await user.click(
      screen.getByRole('button', { name: 'opsAnalysis.screen.elementChart' }),
    );
    expect(onOpenChartSelector).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-screen-catalog-flyout]')).toBeNull();
  });

  it('draws a straight insertion line outside the rounded list row', () => {
    render(
      <ScreenElementPalette
        items={[
          createScreenTextItem([], { id: 'text-1', content: '说明', zIndex: 2 }),
          createScreenTextItem([], { id: 'text-2', content: '备注', zIndex: 1 }),
        ]}
        selectedItemId={null}
        onSelectItem={() => undefined}
        onAddText={() => undefined}
        onAddClock={() => undefined}
        onAddTitleFrame={() => undefined}
        onAddDecoration={() => undefined}
        onAddShape={() => undefined}
        onOpenChartSelector={() => undefined}
        onOpenItemMenu={() => undefined}
        onReorderItem={() => undefined}
      />,
    );

    const source = document.querySelector('[data-screen-list-item="text-2"]');
    const target = document.querySelector('[data-screen-list-item="text-1"]');
    expect(source).toBeTruthy();
    expect(target).toBeTruthy();
    fireEvent.dragStart(source!);
    fireEvent.dragOver(target!);
    const line = document.querySelector('[data-screen-layer-drop]');
    expect(line).toBeTruthy();
    expect(line?.parentElement).not.toBe(target);
    expect(target?.className).not.toContain('shadow-[');
    expect(line?.className).toContain('h-0.5');
    expect(line?.className).not.toContain('rounded');
  });
});
