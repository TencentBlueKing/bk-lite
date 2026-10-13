import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  SCREEN_INSPECTOR_DEFAULT_WIDTH,
  ScreenInspectorPane,
} from '../screenInspectorPane';

describe('screen inspector pane', () => {
  it('starts at the current sidebar width and grows when dragged left', () => {
    render(
      <ScreenInspectorPane label="调整右侧栏宽度">
        <div>画布设置</div>
      </ScreenInspectorPane>,
    );

    const pane = document.querySelector('[data-screen-inspector]');
    expect(pane?.getAttribute('style')).toContain(
      `width: ${SCREEN_INSPECTOR_DEFAULT_WIDTH}px`,
    );

    fireEvent.mouseDown(screen.getByRole('separator'), { clientX: 800 });
    fireEvent.mouseMove(document, { clientX: 760 });
    expect(pane?.getAttribute('style')).toContain('width: 440px');

    fireEvent.mouseMove(document, { clientX: 2000 });
    expect(pane?.getAttribute('style')).toContain('width: 320px');

    fireEvent.mouseUp(document);
    expect(document.body.style.cursor).toBe('');
  });

  it('hides the pane and keeps its width while collapsed', () => {
    const view = render(
      <ScreenInspectorPane label="调整右侧栏宽度" collapsed>
        <div>画布设置</div>
      </ScreenInspectorPane>,
    );

    const pane = document.querySelector('[data-screen-inspector]');
    expect(pane?.getAttribute('style')).toContain('display: none');
    expect(pane?.getAttribute('style')).toContain(
      `width: ${SCREEN_INSPECTOR_DEFAULT_WIDTH}px`,
    );
    expect(pane?.getAttribute('aria-hidden')).toBe('true');

    view.rerender(
      <ScreenInspectorPane label="调整右侧栏宽度">
        <div>画布设置</div>
      </ScreenInspectorPane>,
    );
    expect(pane?.getAttribute('style') ?? '').not.toContain('display: none');
    expect(pane?.getAttribute('aria-hidden')).toBeNull();
  });
});
