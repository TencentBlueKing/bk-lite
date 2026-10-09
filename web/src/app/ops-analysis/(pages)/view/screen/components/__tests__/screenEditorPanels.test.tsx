import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import {
  ScreenCanvasSettings,
  ScreenStyleInspector,
} from '../screenEditorPanels';
import {
  createScreenClockItem,
  createScreenDecorationItem,
  createScreenShapeItem,
  createScreenTitleFrameItem,
} from '../../utils/screenItems';
import { createScreenWidgetItem } from '../../utils/layoutUtils';
import type { ScreenViewportConfig } from '@/app/ops-analysis/types/screen';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
});

const defaultViewport: ScreenViewportConfig = {
  width: 1920,
  height: 1080,
  theme: 'screen-dark',
  adapter: 'fill',
  background: { type: 'preset', key: 'dark-glow' },
};

describe('ScreenCanvasSettings', () => {
  it('renders canvas settings with resolution presets and aspect ratio tag', () => {
    const onChange = vi.fn();
    render(<ScreenCanvasSettings viewport={defaultViewport} onChange={onChange} />);

    expect(screen.getByText('opsAnalysis.screen.canvasSettings')).toBeTruthy();
    expect(screen.getByText('16:9')).toBeTruthy();
    expect(screen.getByText('1920 × 1080')).toBeTruthy();
    expect(screen.getByText('3840 × 2160')).toBeTruthy();
  });

  it('swaps width and height on swap button click', () => {
    const onChange = vi.fn();
    render(<ScreenCanvasSettings viewport={defaultViewport} onChange={onChange} />);

    const swapBtn = screen.getByRole('button', {
      name: 'opsAnalysis.screen.swapWidthHeight',
    });
    fireEvent.click(swapBtn);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        width: 1080,
        height: 1920,
      }),
    );
  });

  it('switches to color background mode and applies default color without recommended palette', () => {
    const onChange = vi.fn();
    render(<ScreenCanvasSettings viewport={defaultViewport} onChange={onChange} />);

    // Switch to color mode
    const colorTab = screen.getByText('opsAnalysis.screen.backgroundTypeColor');
    fireEvent.click(colorTab);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        background: { type: 'color', color: '#071422' },
      }),
    );

    // Recommended colors should not exist
    expect(screen.queryByText('opsAnalysis.screen.recommendedColors')).toBeNull();
  });
});

describe('ScreenStyleInspector for Widgets', () => {
  it('renders container style options and geometry without redundant header', () => {
    const widget = {
      ...createScreenWidgetItem('single', []),
      title: '核心业务指标',
      x: 100,
      y: 200,
      w: 400,
      h: 300,
    };
    const onChange = vi.fn();

    render(
      <ScreenStyleInspector
        item={widget}
        viewport={defaultViewport}
        onChange={onChange}
      />,
    );

    expect(screen.getByText('opsAnalysis.screen.containerStyle')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.widgetFramePanel')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.widgetFrameBare')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.positionAndSize')).toBeTruthy();
    // Redundant header & headerVisibility should not be displayed
    expect(screen.queryByText('opsAnalysis.screen.headerVisibility')).toBeNull();
  });

  it('supports horizontal centering shortcut', () => {
    const widget = {
      ...createScreenWidgetItem('single', []),
      x: 100,
      y: 200,
      w: 400,
      h: 300,
    };
    const onChange = vi.fn();

    render(
      <ScreenStyleInspector
        item={widget}
        viewport={defaultViewport}
        onChange={onChange}
      />,
    );

    const centerHBtn = screen.getByRole('button', {
      name: 'opsAnalysis.screen.centerHorizontal',
    });
    fireEvent.click(centerHBtn);

    // (1920 - 400) / 2 = 760
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        x: 760,
      }),
    );
  });
});

describe('ScreenStyleInspector for Display Elements', () => {
  it('renders title frame inspector with text input and change preset trigger', () => {
    const titleItem = createScreenTitleFrameItem([], {
      preset: 'hero-5',
      content: '数字大屏看板',
    });
    const onChange = vi.fn();

    render(
      <ScreenStyleInspector
        item={titleItem}
        viewport={defaultViewport}
        onChange={onChange}
      />,
    );

    expect(screen.getByDisplayValue('数字大屏看板')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.changePreset')).toBeTruthy();

    // Click change preset
    fireEvent.click(screen.getByText('opsAnalysis.screen.changePreset'));
    expect(screen.getByText('common.collapse')).toBeTruthy();
  });

  it('renders clock inspector with preview formatted items', () => {
    const clockItem = createScreenClockItem([], {
      format: 'HH:mm:ss',
    });
    const onChange = vi.fn();

    render(
      <ScreenStyleInspector
        item={clockItem}
        viewport={defaultViewport}
        onChange={onChange}
      />,
    );

    expect(screen.getByText('opsAnalysis.screen.elementClock')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.clockFormat')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.clockStyle')).toBeTruthy();
  });

  it('renders shape inspector with fill, stroke and shadow sections', () => {
    const shapeItem = createScreenShapeItem([], 'rect');
    const onChange = vi.fn();

    render(
      <ScreenStyleInspector
        item={shapeItem}
        viewport={defaultViewport}
        onChange={onChange}
      />,
    );

    expect(screen.getByText('opsAnalysis.screen.shapeFill')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.shape.fillMode')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.shapeStroke')).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.shapeShadow')).toBeTruthy();

    // Switch to gradient fill mode
    const gradientOption = screen.getByText('opsAnalysis.screen.shape.fillGradient');
    fireEvent.click(gradientOption);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        shapeStyle: expect.objectContaining({
          hideBackground: false,
          gradient: true,
        }),
      }),
    );
  });

  it('renders decoration inspector with collapsible preset switcher', () => {
    const decoItem = createScreenDecorationItem([], 'panelFrame', 'border-21');
    const onChange = vi.fn();

    render(
      <ScreenStyleInspector
        item={decoItem}
        viewport={defaultViewport}
        onChange={onChange}
      />,
    );

    // Old plain preview section should be removed
    expect(screen.queryByText('opsAnalysis.screen.assetPreview')).toBeNull();
    // Change preset button should be displayed
    const changePresetBtn = screen.getByText('opsAnalysis.screen.changePreset');
    expect(changePresetBtn).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.positionAndSize')).toBeTruthy();

    // Preset list is initially collapsed
    expect(screen.queryByText('opsAnalysis.screen.panelFrame.border-22')).toBeNull();

    // Click to expand preset switcher
    fireEvent.click(changePresetBtn);
    expect(screen.getByText('common.collapse')).toBeTruthy();

    // Click another preset button to switch
    const border22Btn = screen.getByText('opsAnalysis.screen.panelFrame.border-22');
    fireEvent.click(border22Btn);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        preset: 'border-22',
      }),
    );

    // Click to collapse
    fireEvent.click(screen.getByText('common.collapse'));
    expect(screen.queryByText('opsAnalysis.screen.panelFrame.border-22')).toBeNull();
  });
});
