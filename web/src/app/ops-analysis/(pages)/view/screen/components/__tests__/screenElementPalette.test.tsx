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
  const expandPalette = () => {
    fireEvent.click(
      screen.getByRole('button', { name: 'opsAnalysis.screen.expandDisplayElements' }),
    );
  };

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
    expandPalette();

    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();
    const collapsePalette = screen.getByRole('button', {
      name: 'opsAnalysis.screen.collapseDisplayElements',
    });
    expect(collapsePalette.closest('aside')?.className).toContain('z-40');
    expect(screen.queryByText('opsAnalysis.screen.elementCorner')).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.titleFrame.hero-6')).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.panelFrame.border-22')).toBeNull();

    await user.click(screen.getByRole('button', { name: '说明' }));
    expect(onSelectItem).toHaveBeenCalledWith('text-1');
    expect(screen.getByRole('button', { name: '说明' }).className).toContain('cursor-pointer');

    const frameGroup = screen.getByRole('button', {
      name: 'opsAnalysis.screen.elementPanelFrame',
    });
    expect(frameGroup.className).toContain('cursor-pointer');
    await user.click(frameGroup);
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
    expandPalette();

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
    expandPalette();

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
    expandPalette();

    const chartButton = screen.getByRole('button', {
      name: 'opsAnalysis.screen.elementChart',
    });
    expect(chartButton.className).toContain('cursor-pointer');
    await user.click(chartButton);
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
    expandPalette();

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

  it('scrolls the element list until the selected row is visible', () => {
    const items = [0, 1, 2].map((index) =>
      createScreenTextItem([], {
        id: `text-${index}`,
        content: `项${index}`,
        zIndex: 3 - index,
      }),
    );
    const props = {
      items,
      onSelectItem: () => undefined,
      onAddText: () => undefined,
      onAddClock: () => undefined,
      onAddTitleFrame: () => undefined,
      onAddDecoration: () => undefined,
      onAddShape: () => undefined,
      onOpenChartSelector: () => undefined,
      onOpenItemMenu: () => undefined,
      onReorderItem: () => undefined,
    };
    const box = (top: number, bottom: number) =>
      ({
        x: 0,
        y: top,
        width: 160,
        height: bottom - top,
        left: 0,
        right: 160,
        top,
        bottom,
        toJSON: () => ({}),
      }) as DOMRect;
    const view = render(<ScreenElementPalette {...props} selectedItemId={null} />);
    expandPalette();
    const list = document.querySelector('[data-screen-element-list]') as HTMLElement;
    const row = document.querySelector('[data-screen-list-item="text-2"]') as HTMLElement;
    const listRect = vi.spyOn(list, 'getBoundingClientRect').mockReturnValue(box(0, 100));
    const rowRect = vi.spyOn(row, 'getBoundingClientRect').mockReturnValue(box(240, 270));

    view.rerender(<ScreenElementPalette {...props} selectedItemId="text-2" />);
    expect(list.scrollTop).toBe(170);

    rowRect.mockReturnValue(box(20, 50));
    view.rerender(<ScreenElementPalette {...props} selectedItemId={null} />);
    view.rerender(<ScreenElementPalette {...props} selectedItemId="text-2" />);
    expect(list.scrollTop).toBe(170);

    listRect.mockRestore();
    rowRect.mockRestore();
  });

  it('covers the canvas on hover and only reserves width after pinning', () => {
    render(
      <ScreenElementPalette
        items={[createScreenTextItem([], { id: 'text-1', content: '说明' })]}
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

    const aside = screen
      .getByRole('button', { name: 'opsAnalysis.screen.expandDisplayElements' })
      .closest('aside');
    const column = aside?.querySelector('[data-screen-palette-column]') as HTMLElement;
    expect(column.style.width).toBe('40px');
    expect(column.style.transition).toContain('width');
    expect(screen.queryByRole('button', { name: '说明' })).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.elementList')).toBeNull();

    fireEvent.mouseEnter(aside!);
    expect(column.style.width).toBe('40px');
    expect(document.querySelector('[data-screen-palette-overlay]')?.className).toContain(
      'w-[162px]',
    );
    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'opsAnalysis.screen.expandDisplayElements' }),
    ).toBeTruthy();

    const row = document.querySelector('[data-screen-list-item="text-1"]');
    fireEvent.dragStart(row!);
    fireEvent.mouseLeave(aside!);
    expect(column.style.width).toBe('40px');
    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();
    fireEvent.dragEnd(row!);
    expect(screen.queryByRole('button', { name: '说明' })).toBeNull();

    fireEvent.click(
      screen.getByRole('button', { name: 'opsAnalysis.screen.expandDisplayElements' }),
    );
    expect(column.style.width).toBe('162px');
    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();
    fireEvent.mouseLeave(aside!);
    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();

    fireEvent.click(
      screen.getByRole('button', { name: 'opsAnalysis.screen.collapseDisplayElements' }),
    );
    expect(column.style.width).toBe('40px');
    expect(screen.getByRole('button', { name: '说明' })).toBeTruthy();
    fireEvent.transitionEnd(column, { propertyName: 'width' });
    expect(screen.queryByRole('button', { name: '说明' })).toBeNull();
  });

  it('opens a catalog from the icon rail without widening the column', () => {
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

    const aside = screen
      .getByRole('button', { name: 'opsAnalysis.screen.elementShape' })
      .closest('aside');
    fireEvent.click(screen.getByRole('button', { name: 'opsAnalysis.screen.elementShape' }));
    expect(
      (aside?.querySelector('[data-screen-palette-column]') as HTMLElement | null)?.style.width,
    ).toBe('40px');
    expect(document.querySelector('[data-screen-palette-overlay]')).toBeNull();
    expect(document.querySelector('[data-shape-thumb="circle"]')).toBeTruthy();
    const flyout = document.querySelector('[data-screen-catalog-flyout]');
    expect(flyout?.getAttribute('style')).toContain('left: 40px');
  });
});
