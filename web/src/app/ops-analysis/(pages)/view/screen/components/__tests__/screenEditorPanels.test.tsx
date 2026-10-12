import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

  it('stores an uploaded image and drops it when cleared or switched to a color', async () => {
    const onChange = vi.fn();
    const { container } = render(
      <ScreenCanvasSettings viewport={defaultViewport} onChange={onChange} />,
    );

    fireEvent.click(screen.getByText('opsAnalysis.screen.backgroundTypeImage'));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['png-bytes'], 'wall.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          background: {
            type: 'image',
            src: expect.stringMatching(/^data:image\/png;base64,/),
          },
        }),
      );
    });

    const uploaded = onChange.mock.calls.at(-1)?.[0] as ScreenViewportConfig;
    onChange.mockClear();
    cleanup();
    render(<ScreenCanvasSettings viewport={uploaded} onChange={onChange} />);
    fireEvent.click(screen.getByText('opsAnalysis.screen.backgroundImageClear'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        background: { type: 'preset', key: 'dark-glow' },
      }),
    );

    onChange.mockClear();
    cleanup();
    render(<ScreenCanvasSettings viewport={uploaded} onChange={onChange} />);
    fireEvent.click(screen.getByText('opsAnalysis.screen.backgroundTypeColor'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        background: { type: 'color', color: '#071422' },
      }),
    );
    const colorBackground = onChange.mock.calls.at(-1)?.[0].background;
    expect(colorBackground).not.toHaveProperty('src');
  });

  it('drops a custom image when switching back to a wallpaper', () => {
    const onChange = vi.fn();
    render(
      <ScreenCanvasSettings
        viewport={{
          ...defaultViewport,
          background: {
            type: 'image',
            src: 'data:image/png;base64,iVBORw0KGgo=',
          },
        }}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByText('opsAnalysis.screen.backgroundTypePreset'));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        background: { type: 'preset', key: 'dark-glow' },
      }),
    );
    expect(onChange.mock.calls.at(-1)?.[0].background).not.toHaveProperty('src');
  });

  it('keeps a custom image when the theme changes', () => {
    const onChange = vi.fn();
    const background = {
      type: 'image' as const,
      src: 'data:image/png;base64,iVBORw0KGgo=',
    };
    render(
      <ScreenCanvasSettings
        viewport={{ ...defaultViewport, background }}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByText('opsAnalysis.screen.themeLight'));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        theme: 'screen-light',
        background,
      }),
    );
  });

  it('does not store an unsupported background image', () => {
    const onChange = vi.fn();
    const { container } = render(
      <ScreenCanvasSettings viewport={defaultViewport} onChange={onChange} />,
    );
    fireEvent.click(screen.getByText('opsAnalysis.screen.backgroundTypeImage'));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [new File(['gif'], 'wall.gif', { type: 'image/gif' })],
      },
    });
    expect(screen.getByText('opsAnalysis.screen.backgroundImageBadType')).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('does not store an oversized background image', () => {
    const onChange = vi.fn();
    const { container } = render(
      <ScreenCanvasSettings viewport={defaultViewport} onChange={onChange} />,
    );
    fireEvent.click(screen.getByText('opsAnalysis.screen.backgroundTypeImage'));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const oversized = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'wall.png', {
      type: 'image/png',
    });
    fireEvent.change(input, { target: { files: [oversized] } });
    expect(screen.getByText('opsAnalysis.screen.backgroundImageTooLarge')).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
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
  it('keeps the image uploader open when a solid color background is copied', () => {
    const onChange = vi.fn();
    const colorViewport: ScreenViewportConfig = {
      ...defaultViewport,
      background: { type: 'color', color: '#112233' },
    };
    const { rerender } = render(
      <ScreenCanvasSettings viewport={colorViewport} onChange={onChange} />,
    );

    fireEvent.click(screen.getByText('opsAnalysis.screen.backgroundTypeImage'));
    expect(screen.getByText('opsAnalysis.screen.backgroundImageUpload')).toBeTruthy();

    rerender(
      <ScreenCanvasSettings
        viewport={{ ...colorViewport, width: 1280, background: { type: 'color', color: '#112233' } }}
        onChange={onChange}
      />,
    );
    expect(screen.getByText('opsAnalysis.screen.backgroundImageUpload')).toBeTruthy();
  });

  it('lets a clock color be chosen instead of the three theme presets', () => {
    const clock = createScreenClockItem([], {
      textStyle: { fontSize: 20, color: 'accent' },
    });
    const onChange = vi.fn();
    const { container } = render(
      <ScreenStyleInspector item={clock} viewport={defaultViewport} onChange={onChange} />,
    );

    expect(screen.queryByText('opsAnalysis.screen.colorCanvas')).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.colorMuted')).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.colorAccent')).toBeNull();
    expect(screen.getByText('opsAnalysis.screen.textColor')).toBeTruthy();
    expect(container.querySelector('.ant-color-picker-trigger')).toBeTruthy();
  });

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
