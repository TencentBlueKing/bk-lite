'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  ColorPicker,
  Input,
  InputNumber,
  Segmented,
  Select,
  Slider,
  Switch,
  Tag,
  Tooltip,
  Upload,
} from 'antd';
import {
  AppstoreOutlined,
  AreaChartOutlined,
  BgColorsOutlined,
  BlockOutlined,
  BorderOuterOutlined,
  BorderOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  ColumnHeightOutlined,
  ColumnWidthOutlined,
  DesktopOutlined,
  FontColorsOutlined,
  FontSizeOutlined,
  LeftOutlined,
  MinusOutlined,
  PictureOutlined,
  QuestionCircleOutlined,
  RightOutlined,
  SwapOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { SCREEN_LAYER_DRAG_MIME } from '../utils/screenLayer';
import type { ScreenGeometryField } from '../utils/screenEditHistory';
import type {
  ScreenClockFormatId,
  ScreenDecorationPresetId,
  ScreenDecorationType,
  ScreenFitAdapter,
  ScreenItem,
  ScreenShapeKind,
  ScreenShapeStyle,
  ScreenTextAlign,
  ScreenThemeId,
  ScreenTextStyleConfig,
  ScreenTitleFramePresetId,
  ScreenViewportConfig,
} from '@/app/ops-analysis/types/screen';
import type { ScreenWidgetAppearance } from '@/app/ops-analysis/types/dashBoard';
import {
  SCREEN_VIEWPORT_PRESETS,
  isValidViewportSize,
  resolveScreenFitAdapter,
} from '../utils/viewport';
import {
  SCREEN_THEME_OPTIONS,
  getScreenTheme,
  resolveScreenThemeId,
} from '../utils/screenTheme';
import {
  SCREEN_WALLPAPER_PRESETS,
  defaultWallpaperKeyForTheme,
  SCREEN_BACKGROUND_IMAGE_MIME_TYPES,
  isScreenImageBackgroundSrc,
  resolveScreenCanvasBackgroundStyle,
  screenBackgroundImageRejection,
} from '../utils/screenBackground';
import { buildScreenElementList } from '../utils/screenElementList';
import {
  SCREEN_CLOCK_FORMATS,
  SCREEN_DIVIDER_PRESETS,
  SCREEN_PANEL_FRAME_PRESETS,
  TITLE_FRAME_PRESETS,
  resolveDividerPreset,
  resolvePanelFramePreset,
  writeScreenChromeDrag,
  type ScreenChromeDragPayload,
  isScreenClockItem,
  isScreenDecorationItem,
  isScreenShapeItem,
  isScreenTextItem,
  isScreenTitleFrameItem,
  isScreenWidgetItem,
} from '../utils/screenItems';
import {
  SCREEN_SHAPE_KINDS,
  resolveScreenShapeStyle,
  screenShapeCss,
} from '../utils/screenShape';
import { formatScreenClockByPreset } from '../utils/screenClock';
import { resolveScreenWidgetAppearance } from '../utils/layoutUtils';
import {
  DecorationSkin,
  ScreenChromeSkinStyles,
  isScreenTextHexColor,
  screenChromeTextStyle,
  titleFrameThumbSrc,
} from './screenChromeSkins';

const GEOMETRY_MIN = 1;

const palettePreviewStyle = {
  ...getScreenTheme('screen-dark').variables,
  ...resolveScreenCanvasBackgroundStyle(
    { type: 'preset', key: 'dark-glow' },
    'screen-dark',
  ),
} as React.CSSProperties;

const CLOCK_FORMAT_LABEL_KEYS: Record<ScreenClockFormatId, string> = {
  'YYYY-MM-DD HH:mm:ss': 'opsAnalysis.screen.clockFormatFull',
  'HH:mm:ss': 'opsAnalysis.screen.clockFormatTime',
  'YYYY-MM-DD': 'opsAnalysis.screen.clockFormatDate',
  'YYYY年M月D日': 'opsAnalysis.screen.clockFormatZhDate',
  'M月D日 HH:mm': 'opsAnalysis.screen.clockFormatMonthTime',
  'dddd HH:mm:ss': 'opsAnalysis.screen.clockFormatWeekTime',
};

const getAspectRatioText = (w: number, h: number) => {
  if (!w || !h) return '16:9';
  const gcd = (a: number, b: number): number => (!b ? a : gcd(b, a % b));
  const divisor = gcd(w, h);
  const ratioW = w / divisor;
  const ratioH = h / divisor;
  if (
    (ratioW === 16 && ratioH === 9) ||
    (ratioW === 4 && ratioH === 3) ||
    (ratioW === 21 && ratioH === 9)
  ) {
    return `${ratioW}:${ratioH}`;
  }
  return `${(w / h).toFixed(2)}:1`;
};

// ==========================================
// 统一卡片与头部容器（Inspector UI 构件）
// ==========================================

const InspectorSection: React.FC<{
  title: React.ReactNode;
  icon?: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}> = ({ title, icon, extra, children, className = '' }) => (
  <section
    className={`rounded-lg border border-(--color-border-1) bg-(--color-fill-1)/25 p-3 transition-colors hover:border-(--color-border-2) ${className}`}
  >
    <div className="mb-2.5 flex items-center justify-between border-b border-(--color-border-1)/60 pb-2">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-(--color-text-1)">
        {icon ? <span className="text-xs text-(--color-primary)">{icon}</span> : null}
        <span>{title}</span>
      </div>
      {extra ? <div className="text-xs">{extra}</div> : null}
    </div>
    <div className="space-y-3">{children}</div>
  </section>
);

const InspectorHeader: React.FC<{
  icon: React.ReactNode;
  title: string;
  badge?: React.ReactNode;
  extra?: React.ReactNode;
}> = ({ icon, title, badge, extra }) => (
  <header className="flex items-center justify-between rounded-lg border border-(--color-border-1) bg-(--color-bg-2) px-3 py-2 shadow-xs">
    <div className="flex min-w-0 items-center gap-2">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-(--color-primary)/10 text-(--color-primary)">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="truncate text-xs font-bold text-(--color-text-1)">{title}</div>
        {badge ? (
          <div className="truncate text-[10px] text-(--color-text-3)">{badge}</div>
        ) : null}
      </div>
    </div>
    {extra ? <div className="shrink-0">{extra}</div> : null}
  </header>
);

// ==========================================
// 紧凑专业的位置与尺寸（X / Y / W / H）网格
// ==========================================

const CompactGeometryGrid: React.FC<{
  item: ScreenItem;
  viewport: ScreenViewportConfig;
  onChange: (next: ScreenItem, editedKey?: ScreenGeometryField) => void;
}> = ({ item, viewport, onChange }) => {
  const { t } = useTranslation();

  const patch = (
    patchValue: Partial<Pick<ScreenItem, 'x' | 'y' | 'w' | 'h'>>,
    editedKey: ScreenGeometryField,
  ) => {
    const next = { ...item, ...patchValue };
    const w = Math.max(GEOMETRY_MIN, Math.min(next.w, viewport.width - next.x));
    const h = Math.max(GEOMETRY_MIN, Math.min(next.h, viewport.height - next.y));
    onChange({
      ...next,
      w,
      h,
      x: Math.max(0, Math.min(next.x, viewport.width - w)),
      y: Math.max(0, Math.min(next.y, viewport.height - h)),
    }, editedKey);
  };

  const centerHorizontal = () => {
    const targetX = Math.max(0, Math.round((viewport.width - item.w) / 2));
    onChange({ ...item, x: targetX });
  };

  const centerVertical = () => {
    const targetY = Math.max(0, Math.round((viewport.height - item.h) / 2));
    onChange({ ...item, y: targetY });
  };

  return (
    <InspectorSection
      title={t('opsAnalysis.screen.positionAndSize')}
      icon={<BorderOuterOutlined />}
      extra={
        <div className="flex items-center gap-1">
          <Tooltip title={t('opsAnalysis.screen.centerHorizontal')}>
            <Button
              size="small"
              type="text"
              aria-label={t('opsAnalysis.screen.centerHorizontal')}
              className="h-6 w-6 p-0 text-(--color-text-3) hover:text-(--color-primary)"
              onClick={centerHorizontal}
              icon={<ColumnWidthOutlined />}
            />
          </Tooltip>
          <Tooltip title={t('opsAnalysis.screen.centerVertical')}>
            <Button
              size="small"
              type="text"
              aria-label={t('opsAnalysis.screen.centerVertical')}
              className="h-6 w-6 p-0 text-(--color-text-3) hover:text-(--color-primary)"
              onClick={centerVertical}
              icon={<ColumnHeightOutlined />}
            />
          </Tooltip>
        </div>
      }
    >
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-[11px] text-(--color-text-3)">
          <span>{t('opsAnalysis.screen.geometry.x')}</span>
          <InputNumber
            className="w-full text-xs"
            precision={0}
            controls={false}
            prefix={<span className="text-[10px] font-semibold text-(--color-text-3)">X</span>}
            suffix={<span className="text-[10px] text-(--color-text-3)">px</span>}
            value={item.x}
            onChange={(val) => {
              if (typeof val === 'number') patch({ x: val }, 'x');
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-(--color-text-3)">
          <span>{t('opsAnalysis.screen.geometry.y')}</span>
          <InputNumber
            className="w-full text-xs"
            precision={0}
            controls={false}
            prefix={<span className="text-[10px] font-semibold text-(--color-text-3)">Y</span>}
            suffix={<span className="text-[10px] text-(--color-text-3)">px</span>}
            value={item.y}
            onChange={(val) => {
              if (typeof val === 'number') patch({ y: val }, 'y');
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-(--color-text-3)">
          <span>{t('opsAnalysis.screen.geometry.w')}</span>
          <InputNumber
            className="w-full text-xs"
            precision={0}
            controls={false}
            min={GEOMETRY_MIN}
            prefix={<span className="text-[10px] font-semibold text-(--color-text-3)">W</span>}
            suffix={<span className="text-[10px] text-(--color-text-3)">px</span>}
            value={item.w}
            onChange={(val) => {
              if (typeof val === 'number') patch({ w: val }, 'w');
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-(--color-text-3)">
          <span>{t('opsAnalysis.screen.geometry.h')}</span>
          <InputNumber
            className="w-full text-xs"
            precision={0}
            controls={false}
            min={GEOMETRY_MIN}
            prefix={<span className="text-[10px] font-semibold text-(--color-text-3)">H</span>}
            suffix={<span className="text-[10px] text-(--color-text-3)">px</span>}
            value={item.h}
            onChange={(val) => {
              if (typeof val === 'number') patch({ h: val }, 'h');
            }}
          />
        </label>
      </div>
    </InspectorSection>
  );
};

const PaletteThumb: React.FC<{
  label: string;
  heightClass?: string;
  dragPayload?: ScreenChromeDragPayload;
  onDragEnd?: () => void;
  onClick: () => void;
  children: React.ReactNode;
}> = ({ label, heightClass = 'h-10', dragPayload, onDragEnd, onClick, children }) => {
  const draggedRef = useRef(false);
  return (
    <button
      type="button"
      draggable={Boolean(dragPayload)}
      className="flex cursor-grab flex-col gap-1 overflow-hidden rounded border border-(--color-border-1) bg-(--color-fill-1) p-1 text-left hover:border-(--color-primary) active:cursor-grabbing"
      onDragStart={(event) => {
        if (!dragPayload) return;
        draggedRef.current = true;
        writeScreenChromeDrag(event.dataTransfer, dragPayload);
      }}
      onDragEnd={() => {
        onDragEnd?.();
      }}
      onClick={() => {
        if (draggedRef.current) {
          draggedRef.current = false;
          return;
        }
        onClick();
      }}
    >
      <div
        className={`${heightClass} isolate overflow-hidden rounded-[2px] px-0.5`}
        style={{
          ...palettePreviewStyle,
          isolation: 'isolate',
          backgroundColor: '#071422',
        }}
      >
        {children}
      </div>
      <span className="truncate text-center text-[10px] leading-none text-(--color-text-2)">
        {label}
      </span>
    </button>
  );
};

type PaletteGroup = 'text' | 'title' | 'frame' | 'divider' | 'shape';

const CATALOG_FLYOUT_WIDTH = 260;

const elementListIcon = (item: ScreenItem | undefined) => {
  if (!item) return null;
  if (isScreenTextItem(item)) return <FontSizeOutlined aria-hidden />;
  if (isScreenTitleFrameItem(item)) return <FontColorsOutlined aria-hidden />;
  if (isScreenClockItem(item)) return <ClockCircleOutlined aria-hidden />;
  if (isScreenWidgetItem(item)) return <AreaChartOutlined aria-hidden />;
  if (isScreenDecorationItem(item)) {
    if (item.decorationType === 'divider') return <MinusOutlined aria-hidden />;
    if (item.decorationType === 'corner') return <BorderOutlined aria-hidden />;
    return <BorderOuterOutlined aria-hidden />;
  }
  if (isScreenShapeItem(item)) return <BlockOutlined aria-hidden />;
  return null;
};

interface ScreenElementPaletteProps {
  selectedItemId?: string | null;
  items: ScreenItem[];
  onSelectItem: (itemId: string | null) => void;
  onAddText: () => void;
  onAddClock: () => void;
  onAddTitleFrame: (preset: ScreenTitleFramePresetId) => void;
  onAddDecoration: (
    decorationType: ScreenDecorationType,
    preset: ScreenDecorationPresetId,
  ) => void;
  onAddShape: (shape: ScreenShapeKind) => void;
  onOpenChartSelector: () => void;
  onOpenItemMenu: (itemId: string, point: { x: number; y: number }) => void;
  onReorderItem: (itemId: string, toIndex: number) => void;
}

export const ScreenElementPalette: React.FC<ScreenElementPaletteProps> = ({
  selectedItemId,
  items,
  onSelectItem,
  onAddText,
  onAddClock,
  onAddTitleFrame,
  onAddDecoration,
  onAddShape,
  onOpenChartSelector,
  onOpenItemMenu,
  onReorderItem,
}) => {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLElement>(null);
  const draggingIdRef = useRef<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [paletteGroup, setPaletteGroup] = useState<PaletteGroup | null>(null);
  const [flyoutBox, setFlyoutBox] = useState({ top: 8, maxHeight: 400 });
  const listed = useMemo(
    () =>
      buildScreenElementList(items, {
        text: t('opsAnalysis.screen.elementText'),
        title: t('opsAnalysis.screen.elementTitle'),
        clock: t('opsAnalysis.screen.elementClock'),
        corner: t('opsAnalysis.screen.elementCorner'),
        divider: t('opsAnalysis.screen.elementDivider'),
        panelFrame: t('opsAnalysis.screen.elementPanelFrame'),
        panelFramePreset: (preset) =>
          t(`opsAnalysis.screen.panelFrame.${resolvePanelFramePreset(preset)}`),
        dividerPreset: (preset) =>
          t(`opsAnalysis.screen.divider.${resolveDividerPreset(preset)}`),
        shapeRect: t('opsAnalysis.screen.shape.rect'),
        shapeCircle: t('opsAnalysis.screen.shape.circle'),
        shapeRoundedRect: t('opsAnalysis.screen.shape.roundedRect'),
      }),
    [items, t],
  );
  const itemById = useMemo(
    () => new Map(items.map((item) => [item.id, item])),
    [items],
  );

  const place = (action: () => void) => {
    action();
    setPaletteGroup(null);
  };

  useEffect(() => {
    if (!paletteGroup) return undefined;
    const onPointerDown = (event: PointerEvent) => {
      const root = rootRef.current;
      if (!root || !(event.target instanceof Node) || root.contains(event.target)) return;
      setPaletteGroup(null);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [paletteGroup]);

  const paletteGroups: { id: PaletteGroup; label: string; icon: React.ReactNode }[] = [
    {
      id: 'text',
      label: t('opsAnalysis.screen.textAndClock'),
      icon: <FontSizeOutlined aria-hidden />,
    },
    {
      id: 'title',
      label: t('opsAnalysis.screen.elementTitle'),
      icon: <FontColorsOutlined aria-hidden />,
    },
    {
      id: 'frame',
      label: t('opsAnalysis.screen.elementPanelFrame'),
      icon: <BorderOuterOutlined aria-hidden />,
    },
    {
      id: 'divider',
      label: t('opsAnalysis.screen.elementDivider'),
      icon: <MinusOutlined aria-hidden />,
    },
    {
      id: 'shape',
      label: t('opsAnalysis.screen.elementShape'),
      icon: <BlockOutlined aria-hidden />,
    },
  ];

  const catalog = (() => {
    if (paletteGroup === 'text') {
      return (
        <div className="grid grid-cols-2 gap-2">
          <PaletteThumb
            heightClass="h-16"
            label={t('opsAnalysis.screen.elementText')}
            dragPayload={{ kind: 'text' }}
            onDragEnd={() => setPaletteGroup(null)}
            onClick={() => place(onAddText)}
          >
            <div
              className="flex h-full items-center justify-center px-1"
              style={screenChromeTextStyle({
                fontSize: 16,
                fontWeight: 600,
                align: 'center',
                color: 'canvas',
              })}
            >
              {t('opsAnalysis.screen.textPreview')}
            </div>
          </PaletteThumb>
          <PaletteThumb
            heightClass="h-16"
            label={t('opsAnalysis.screen.elementClock')}
            dragPayload={{ kind: 'clock' }}
            onDragEnd={() => setPaletteGroup(null)}
            onClick={() => place(onAddClock)}
          >
            <div className="flex h-full items-center justify-center">
              <span
                className="font-semibold leading-none tabular-nums tracking-[0.14em] text-(--screen-title-color)"
                style={{ fontSize: 16 }}
              >
                12:00:00
              </span>
            </div>
          </PaletteThumb>
        </div>
      );
    }
    if (paletteGroup === 'title') {
      return (
        <div className="grid grid-cols-2 gap-2">
          {TITLE_FRAME_PRESETS.map((preset) => (
            <PaletteThumb
              key={preset}
              heightClass="h-20"
              label={t(`opsAnalysis.screen.titleFrame.${preset}`)}
              dragPayload={{ kind: 'titleFrame', preset }}
              onDragEnd={() => setPaletteGroup(null)}
              onClick={() => place(() => onAddTitleFrame(preset))}
            >
              <img
                alt=""
                draggable={false}
                data-title-frame-thumb={preset}
                src={titleFrameThumbSrc(preset)}
                className="h-full w-full object-cover"
              />
            </PaletteThumb>
          ))}
        </div>
      );
    }
    if (paletteGroup === 'frame') {
      return (
        <div className="grid grid-cols-2 gap-2">
          {SCREEN_PANEL_FRAME_PRESETS.map((preset) => (
            <PaletteThumb
              key={preset}
              heightClass="h-16"
              label={t(`opsAnalysis.screen.panelFrame.${preset}`)}
              dragPayload={{ kind: 'decoration', decorationType: 'panelFrame', preset }}
              onDragEnd={() => setPaletteGroup(null)}
              onClick={() => place(() => onAddDecoration('panelFrame', preset))}
            >
              <DecorationSkin item={{ decorationType: 'panelFrame', preset }} />
            </PaletteThumb>
          ))}
        </div>
      );
    }
    if (paletteGroup === 'divider') {
      return (
        <div className="grid grid-cols-2 gap-2">
          {SCREEN_DIVIDER_PRESETS.map((preset) => (
            <PaletteThumb
              key={preset}
              heightClass="h-10"
              label={t(`opsAnalysis.screen.divider.${preset}`)}
              dragPayload={{ kind: 'decoration', decorationType: 'divider', preset }}
              onDragEnd={() => setPaletteGroup(null)}
              onClick={() => place(() => onAddDecoration('divider', preset))}
            >
              <DecorationSkin
                item={{ decorationType: 'divider', preset }}
                preview
              />
            </PaletteThumb>
          ))}
        </div>
      );
    }
    if (paletteGroup === 'shape') {
      return (
        <div className="grid grid-cols-2 gap-2">
          {SCREEN_SHAPE_KINDS.map((shape) => (
            <PaletteThumb
              key={shape}
              heightClass="h-16"
              label={t(`opsAnalysis.screen.shape.${shape}`)}
              dragPayload={{ kind: 'shape', shape }}
              onDragEnd={() => setPaletteGroup(null)}
              onClick={() => place(() => onAddShape(shape))}
            >
              <div className="flex h-full items-center justify-center p-2">
                <div
                  data-shape-thumb={shape}
                  className={
                    shape === 'circle' ? 'aspect-square h-full' : 'h-full w-full'
                  }
                  style={screenShapeCss(shape)}
                />
              </div>
            </PaletteThumb>
          ))}
        </div>
      );
    }
    return null;
  })();

  const activeGroup = paletteGroups.find((group) => group.id === paletteGroup);

  return (
    <aside
      ref={rootRef}
      className={`relative z-20 h-full shrink-0 transition-[width] duration-300 ${
        collapsed
          ? 'w-0 border-r-0'
          : 'w-[192px] border-r border-(--color-border-1) bg-(--color-bg-1)'
      }`}
    >
      <button
        type="button"
        aria-label={collapsed ? t('common.expand') : t('common.collapse')}
        className="absolute top-5 z-30 flex h-6 w-6 items-center justify-center border border-(--color-border-1) bg-(--color-bg-1) text-(--color-text-2) shadow-sm hover:bg-(--color-fill-2)"
        style={{
          right: collapsed ? -24 : -12,
          borderRadius: collapsed ? '0 50% 50% 0' : '50%',
        }}
        onClick={() => {
          setCollapsed((current) => !current);
          setPaletteGroup(null);
        }}
      >
        {collapsed ? <RightOutlined aria-hidden /> : <LeftOutlined aria-hidden />}
      </button>
      <div
        className={`flex h-full min-h-0 flex-col bg-(--color-bg-1) ${
          collapsed ? 'pointer-events-none opacity-0' : ''
        }`}
        aria-hidden={collapsed}
      >
        <div className="shrink-0 border-b border-(--color-border-1) px-2 py-2">
          <div className="mb-1 px-1 text-xs font-semibold text-(--color-text-1)">
            {t('opsAnalysis.screen.displayElements')}
          </div>
          <button
            type="button"
            className="mb-0.5 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-(--color-text-2) hover:bg-(--color-fill-1)"
            onClick={() => {
              setPaletteGroup(null);
              onOpenChartSelector();
            }}
          >
            <span className="text-(--color-text-3)">
              <AreaChartOutlined aria-hidden />
            </span>
            <span className="min-w-0 flex-1 truncate">
              {t('opsAnalysis.screen.elementChart')}
            </span>
          </button>
          {paletteGroups.map((group) => {
            const active = paletteGroup === group.id;
            return (
              <button
                key={group.id}
                type="button"
                aria-expanded={active}
                className={`mb-0.5 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs ${
                  active
                    ? 'bg-(--color-fill-2) font-medium text-(--color-primary)'
                    : 'text-(--color-text-2) hover:bg-(--color-fill-1)'
                }`}
                onClick={(event) => {
                  if (paletteGroup === group.id) {
                    setPaletteGroup(null);
                    return;
                  }
                  const root = rootRef.current;
                  const rootTop = root?.getBoundingClientRect().top ?? 0;
                  const rawTop = event.currentTarget.getBoundingClientRect().top - rootTop;
                  const room = Math.max(160, (root?.clientHeight ?? 400) - 16);
                  const maxHeight = Math.min(400, room);
                  const top = Math.max(8, Math.min(rawTop, room - maxHeight + 8));
                  setFlyoutBox({ top, maxHeight });
                  setPaletteGroup(group.id);
                }}
              >
                <span className={active ? 'text-(--color-primary)' : 'text-(--color-text-3)'}>
                  {group.icon}
                </span>
                <span className="min-w-0 flex-1 truncate">{group.label}</span>
              </button>
            );
          })}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          <div className="mb-1 px-1 text-xs font-semibold text-(--color-text-1)">
            {t('opsAnalysis.screen.elementList')}
          </div>
          {listed.length === 0 ? (
            <div className="px-1 py-3 text-xs text-(--color-text-3)">
              {t('opsAnalysis.screen.canvasEmpty')}
            </div>
          ) : (
            listed.map((entry, index) => {
              const selected = selectedItemId === entry.id;
              return (
                <div key={entry.id} className="relative mb-0.5">
                  {dropIndex === index ? (
                    <span
                      aria-hidden
                      data-screen-layer-drop=""
                      className="pointer-events-none absolute inset-x-0 top-0 z-10 block h-0.5 -translate-y-1/2 bg-(--color-primary)"
                    />
                  ) : null}
                  <div
                    draggable
                    data-screen-list-item={entry.id}
                    className={`cursor-grab rounded-md active:cursor-grabbing ${
                      selected
                        ? 'bg-[color-mix(in_srgb,var(--color-primary)_14%,transparent)]'
                        : 'hover:bg-(--color-fill-1)'
                    } ${draggingId === entry.id ? 'opacity-40' : ''}`}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      onSelectItem(entry.id);
                      onOpenItemMenu(entry.id, { x: event.clientX, y: event.clientY });
                    }}
                    onDragStart={(event) => {
                      draggingIdRef.current = entry.id;
                      setDraggingId(entry.id);
                      event.dataTransfer?.setData(SCREEN_LAYER_DRAG_MIME, entry.id);
                      if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
                    }}
                    onDragOver={(event) => {
                      if (draggingIdRef.current == null) return;
                      event.preventDefault();
                      if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
                      setDropIndex(index);
                    }}
                    onDrop={(event) => {
                      const itemId =
                        event.dataTransfer?.getData(SCREEN_LAYER_DRAG_MIME) ||
                        draggingIdRef.current;
                      draggingIdRef.current = null;
                      setDraggingId(null);
                      setDropIndex(null);
                      if (!itemId) return;
                      event.preventDefault();
                      onReorderItem(itemId, index);
                    }}
                    onDragEnd={() => {
                      draggingIdRef.current = null;
                      setDraggingId(null);
                      setDropIndex(null);
                    }}
                  >
                    <button
                      type="button"
                      className={`flex w-full min-w-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs ${
                        selected
                          ? 'font-medium text-(--color-text-1)'
                          : 'text-(--color-text-2)'
                      }`}
                      onClick={() => onSelectItem(entry.id)}
                    >
                      <span
                        className={`shrink-0 ${
                          selected ? 'text-(--color-primary)' : 'text-(--color-text-3)'
                        }`}
                      >
                        {elementListIcon(itemById.get(entry.id))}
                      </span>
                      <span className="truncate">{entry.label}</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
      {activeGroup && !collapsed ? (
        <div
          data-screen-catalog-flyout=""
          className="absolute left-full z-30 ml-1 flex flex-col overflow-y-auto rounded-md border border-(--color-border-1) bg-(--color-bg-1) shadow-lg"
          style={{
            top: flyoutBox.top,
            width: CATALOG_FLYOUT_WIDTH,
            maxHeight: flyoutBox.maxHeight,
          }}
        >
          <div className="shrink-0 border-b border-(--color-border-1) px-3 py-2 text-xs font-semibold text-(--color-text-1)">
            {activeGroup.label}
          </div>
          <div className="p-2">
            <ScreenChromeSkinStyles />
            {catalog}
          </div>
        </div>
      ) : null}
    </aside>
  );
};

// ==========================================
// 文本排版表单段
// ==========================================

type TextStyleFieldKey = 'fontSize' | 'fontWeight' | 'color' | 'align';

const textColorSwatch = (
  color: ScreenTextStyleConfig['color'],
  theme: ScreenThemeId,
) => {
  if (isScreenTextHexColor(color)) return color;
  const variables = getScreenTheme(theme).variables;
  if (color === 'muted') return String(variables['--screen-clock-color']);
  if (color === 'accent') return String(variables['--screen-chrome-accent']);
  return String(variables['--screen-title-color']);
};

const TextStyleFields: React.FC<{
  value?: ScreenTextStyleConfig;
  theme?: ScreenThemeId;
  onChange: (next: ScreenTextStyleConfig) => void;
  onFieldEditEnd?: () => void;
  fields?: TextStyleFieldKey[];
  minFontSize?: number;
  maxFontSize?: number;
}> = ({
  value,
  theme = 'screen-dark',
  onChange,
  onFieldEditEnd,
  fields = ['fontSize', 'fontWeight', 'color', 'align'],
  minFontSize = 12,
  maxFontSize = 72,
}) => {
  const { t } = useTranslation();
  const style = value || {};
  const show = (field: TextStyleFieldKey) => fields.includes(field);

  return (
    <div className="space-y-3">
      {show('fontSize') ? (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-(--color-text-2)">
            <span>{t('opsAnalysis.screen.fontSize')}</span>
            <span className="font-mono text-xs text-(--color-text-1)">
              {style.fontSize ?? 20} px
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Slider
              min={minFontSize}
              max={maxFontSize}
              value={style.fontSize ?? 20}
              className="m-0 flex-1"
              onChange={(fontSize) =>
                onChange({ ...style, fontSize: Number(fontSize) || 20 })
              }
              onChangeComplete={() => onFieldEditEnd?.()}
            />
            <InputNumber
              size="small"
              className="w-16 text-xs"
              min={minFontSize}
              max={maxFontSize}
              value={style.fontSize ?? 20}
              onChange={(fontSize) =>
                onChange({ ...style, fontSize: Number(fontSize) || 20 })
              }
            />
          </div>
        </div>
      ) : null}

      {show('fontWeight') ? (
        <div className="flex items-center justify-between text-xs text-(--color-text-2)">
          <span>{t('opsAnalysis.screen.fontWeight')}</span>
          <Select
            size="small"
            className="w-32"
            value={style.fontWeight ?? 600}
            onChange={(fontWeight) => onChange({ ...style, fontWeight })}
            options={[
              { label: t('opsAnalysis.screen.fontWeightRegular'), value: 400 },
              { label: t('opsAnalysis.screen.fontWeightSemibold'), value: 600 },
              { label: t('opsAnalysis.screen.fontWeightBold'), value: 700 },
              { label: t('opsAnalysis.screen.fontWeightHeavy'), value: 800 },
            ]}
          />
        </div>
      ) : null}

      {show('color') ? (
        <div className="flex items-center justify-between text-xs text-(--color-text-2)">
          <span>{t('opsAnalysis.screen.textColor')}</span>
          <ColorPicker
            disabledAlpha
            showText
            value={textColorSwatch(style.color, resolveScreenThemeId(theme))}
            onChangeComplete={(color) => {
              const hex = `#${color.toHexString().replace('#', '').slice(0, 6)}`;
              if (!isScreenTextHexColor(hex)) return;
              onChange({ ...style, color: hex });
              onFieldEditEnd?.();
            }}
          />
        </div>
      ) : null}

      {show('align') ? (
        <div className="space-y-1.5">
          <div className="text-xs text-(--color-text-2)">{t('opsAnalysis.screen.textAlign')}</div>
          <Segmented
            block
            size="small"
            value={style.align ?? 'left'}
            onChange={(align) =>
              onChange({ ...style, align: align as ScreenTextAlign })
            }
            options={[
              { label: t('opsAnalysis.screen.alignLeft'), value: 'left' },
              { label: t('opsAnalysis.screen.alignCenter'), value: 'center' },
              { label: t('opsAnalysis.screen.alignRight'), value: 'right' },
            ]}
          />
        </div>
      ) : null}
    </div>
  );
};

// ==========================================
// 大屏画布全局配置面板（ScreenCanvasSettings）
// ==========================================

interface ScreenCanvasSettingsProps {
  viewport: ScreenViewportConfig;
  onChange: (viewport: ScreenViewportConfig) => void;
  onFieldEditEnd?: () => void;
}

export const ScreenCanvasSettings: React.FC<ScreenCanvasSettingsProps> = ({
  viewport,
  onChange,
  onFieldEditEnd,
}) => {
  const { t } = useTranslation();
  const theme = resolveScreenThemeId(viewport.theme);
  const adapter = resolveScreenFitAdapter(viewport.adapter);
  const [widthDraft, setWidthDraft] = useState(viewport.width);
  const [heightDraft, setHeightDraft] = useState(viewport.height);

  useEffect(() => {
    setWidthDraft(viewport.width);
    setHeightDraft(viewport.height);
  }, [viewport.width, viewport.height]);

  const presetKey =
    SCREEN_VIEWPORT_PRESETS.find(
      (item) => item.width === viewport.width && item.height === viewport.height,
    )?.key || 'custom';

  const wallpapers = SCREEN_WALLPAPER_PRESETS.filter((item) => item.theme === theme);
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;
  const backgroundModeRef = useRef<'preset' | 'color' | 'image'>('preset');
  const [imageError, setImageError] = useState<'type' | 'size' | null>(null);
  const [backgroundMode, setBackgroundMode] = useState<'preset' | 'color' | 'image'>(
    viewport.background?.type === 'image'
      ? 'image'
      : viewport.background?.type === 'color'
        ? 'color'
        : 'preset',
  );
  backgroundModeRef.current = backgroundMode;

  const selectBackgroundMode = (mode: 'preset' | 'color' | 'image') => {
    backgroundModeRef.current = mode;
    setBackgroundMode(mode);
  };

  const backgroundType = viewport.background?.type;
  useEffect(() => {
    const mode =
      backgroundType === 'image' ? 'image' : backgroundType === 'color' ? 'color' : 'preset';
    backgroundModeRef.current = mode;
    setBackgroundMode(mode);
  }, [backgroundType]);

  const applyViewport = (next: ScreenViewportConfig) => {
    onChange(next);
  };

  const resetToThemePreset = () => {
    setImageError(null);
    selectBackgroundMode('preset');
    applyViewport({
      ...viewportRef.current,
      background: {
        type: 'preset',
        key: defaultWallpaperKeyForTheme(theme),
      },
    });
  };

  const acceptBackgroundImage = (file: File) => {
    const rejection = screenBackgroundImageRejection(file);
    if (rejection) {
      setImageError(rejection);
      return;
    }
    const reader = new FileReader();
    const fail = () => setImageError('type');
    reader.onload = () => {
      if (backgroundModeRef.current !== 'image') return;
      const result = reader.result;
      if (!isScreenImageBackgroundSrc(result)) {
        fail();
        return;
      }
      setImageError(null);
      applyViewport({
        ...viewportRef.current,
        background: { type: 'image', src: result },
      });
    };
    reader.onerror = fail;
    reader.onabort = fail;
    reader.readAsDataURL(file);
  };

  const writeViewportAxis = (axis: 'width' | 'height', value: number) => {
    if (axis === 'width') setWidthDraft(value);
    else setHeightDraft(value);
    if (!isValidViewportSize(value) || value === viewportRef.current[axis]) return;
    applyViewport({ ...viewportRef.current, [axis]: value });
  };

  const commitSize = () => {
    if (!isValidViewportSize(widthDraft) || !isValidViewportSize(heightDraft)) {
      setWidthDraft(viewport.width);
      setHeightDraft(viewport.height);
      return;
    }
    if (widthDraft === viewport.width && heightDraft === viewport.height) {
      return;
    }
    applyViewport({ ...viewport, width: widthDraft, height: heightDraft });
  };

  const swapWidthHeight = () => {
    const nextW = heightDraft;
    const nextH = widthDraft;
    setWidthDraft(nextW);
    setHeightDraft(nextH);
    applyViewport({ ...viewport, width: nextW, height: nextH });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-3">
      {/* 顶部指示 */}
      <InspectorHeader
        icon={<AppstoreOutlined />}
        title={t('opsAnalysis.screen.canvasSettings')}
        badge={`${viewport.width} × ${viewport.height} (${getAspectRatioText(
          viewport.width,
          viewport.height,
        )})`}
      />

      {/* 1. 画布主题 */}
      <InspectorSection
        title={t('opsAnalysis.screen.canvasTheme')}
        icon={<BgColorsOutlined />}
      >
        <Segmented
          block
          value={theme}
          options={SCREEN_THEME_OPTIONS.map((item) => ({
            label: (
              <span className="flex items-center justify-center gap-1.5 py-0.5">
                <span
                  className={`h-2.5 w-2.5 rounded-full border border-black/20 ${
                    item.id === 'screen-dark' ? 'bg-[#071422]' : 'bg-[#ffffff]'
                  }`}
                />
                <span>{t(item.labelKey)}</span>
              </span>
            ),
            value: item.id,
          }))}
          onChange={(nextTheme) => {
            const themeId = resolveScreenThemeId(nextTheme);
            const keepBackground =
              viewport.background?.type === 'color' ||
              viewport.background?.type === 'image';
            applyViewport({
              ...viewport,
              theme: themeId,
              background: keepBackground
                ? viewport.background
                : { type: 'preset', key: defaultWallpaperKeyForTheme(themeId) },
            });
          }}
        />
      </InspectorSection>

      {/* 2. 画布分辨率与尺寸 */}
      <InspectorSection
        title={t('opsAnalysis.screen.resolutionPreset')}
        icon={<DesktopOutlined />}
        extra={
          <div className="flex items-center gap-1">
            <Tag bordered={false} className="mr-0 font-mono text-[10px] text-(--color-text-3)">
              {getAspectRatioText(widthDraft, heightDraft)}
            </Tag>
            <Tooltip title={t('opsAnalysis.screen.swapWidthHeight')}>
              <Button
                size="small"
                type="text"
                aria-label={t('opsAnalysis.screen.swapWidthHeight')}
                className="h-5 w-5 p-0 text-(--color-text-3) hover:text-(--color-primary)"
                onClick={swapWidthHeight}
                icon={<SwapOutlined />}
              />
            </Tooltip>
          </div>
        }
      >
        <div className="grid grid-cols-3 gap-1.5">
          {SCREEN_VIEWPORT_PRESETS.map((preset) => {
            const isActive = presetKey === preset.key;
            return (
              <button
                key={preset.key}
                type="button"
                onClick={() =>
                  applyViewport({
                    ...viewport,
                    width: preset.width,
                    height: preset.height,
                  })
                }
                className={`flex items-center justify-center rounded-md border px-1 py-1.5 text-xs transition-colors ${
                  isActive
                    ? 'border-(--color-primary) bg-(--color-primary)/10 font-semibold text-(--color-primary)'
                    : 'border-(--color-border-1) bg-(--color-bg-1) text-(--color-text-2) hover:border-(--color-border-2) hover:text-(--color-text-1)'
                }`}
              >
                <span>{preset.label}</span>
              </button>
            );
          })}
        </div>

        <div className="grid grid-cols-2 gap-2 pt-1">
          <label className="flex flex-col gap-1 text-[11px] text-(--color-text-3)">
            <span>{t('opsAnalysis.screen.width')}</span>
            <InputNumber
              className="w-full text-xs"
              precision={0}
              controls={false}
              prefix={<span className="text-[10px] font-semibold text-(--color-text-3)">W</span>}
              suffix={<span className="text-[10px] text-(--color-text-3)">px</span>}
              value={widthDraft}
              onChange={(width) => {
                if (typeof width === 'number') writeViewportAxis('width', width);
              }}
              onBlur={commitSize}
              onPressEnter={commitSize}
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-(--color-text-3)">
            <span>{t('opsAnalysis.screen.height')}</span>
            <InputNumber
              className="w-full text-xs"
              precision={0}
              controls={false}
              prefix={<span className="text-[10px] font-semibold text-(--color-text-3)">H</span>}
              suffix={<span className="text-[10px] text-(--color-text-3)">px</span>}
              value={heightDraft}
              onChange={(height) => {
                if (typeof height === 'number') writeViewportAxis('height', height);
              }}
              onBlur={commitSize}
              onPressEnter={commitSize}
            />
          </label>
        </div>
      </InspectorSection>

      {/* 3. 背景设置 */}
      <InspectorSection
        title={t('opsAnalysis.screen.background')}
        icon={<PictureOutlined />}
      >
        <Segmented
          block
          value={backgroundMode}
          options={[
            { label: t('opsAnalysis.screen.backgroundTypePreset'), value: 'preset' },
            { label: t('opsAnalysis.screen.backgroundTypeColor'), value: 'color' },
            { label: t('opsAnalysis.screen.backgroundTypeImage'), value: 'image' },
          ]}
          onChange={(mode) => {
            setImageError(null);
            if (mode === 'image') {
              selectBackgroundMode('image');
              return;
            }
            if (mode === 'color') {
              selectBackgroundMode('color');
              applyViewport({
                ...viewportRef.current,
                background: { type: 'color', color: '#071422' },
              });
              return;
            }
            resetToThemePreset();
          }}
        />

        {backgroundMode === 'image' ? (
          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between gap-2">
              <span className="shrink-0 text-xs text-(--color-text-2)">
                {t('opsAnalysis.screen.backgroundTypeImage')}
              </span>
              <div className="flex min-w-0 items-center gap-2">
                {viewport.background?.type === 'image' ? (
                  <img
                    alt=""
                    src={viewport.background.src}
                    className="h-9 w-14 shrink-0 rounded border border-(--color-border-1) object-cover"
                  />
                ) : null}
                <Upload
                  accept={SCREEN_BACKGROUND_IMAGE_MIME_TYPES.join(',')}
                  showUploadList={false}
                  beforeUpload={(file) => {
                    acceptBackgroundImage(file);
                    return false;
                  }}
                >
                  <Button size="small" icon={<UploadOutlined />}>
                    {t('opsAnalysis.screen.backgroundImageUpload')}
                  </Button>
                </Upload>
                {viewport.background?.type === 'image' ? (
                  <Button size="small" type="link" onClick={resetToThemePreset}>
                    {t('opsAnalysis.screen.backgroundImageClear')}
                  </Button>
                ) : null}
              </div>
            </div>
            {imageError ? (
              <div className="text-xs text-(--color-error)">
                {t(
                  imageError === 'size'
                    ? 'opsAnalysis.screen.backgroundImageTooLarge'
                    : 'opsAnalysis.screen.backgroundImageBadType',
                )}
              </div>
            ) : null}
          </div>
        ) : viewport.background?.type === 'color' ? (
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-(--color-text-2)">
              {t('opsAnalysis.screen.customColor')}
            </span>
            <ColorPicker
              showText
              value={viewport.background.color}
              onChange={(color) =>
                applyViewport({
                  ...viewport,
                  background: { type: 'color', color: color.toHexString() },
                })
              }
              onChangeComplete={() => onFieldEditEnd?.()}
            />
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 pt-1">
            {wallpapers.map((item) => {
              const isSelected =
                viewport.background?.type === 'preset' &&
                viewport.background.key === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  aria-label={item.key}
                  onClick={() =>
                    applyViewport({
                      ...viewport,
                      background: { type: 'preset', key: item.key },
                    })
                  }
                  className={`group relative flex flex-col overflow-hidden rounded-md border text-left transition-all ${
                    isSelected
                      ? 'border-(--color-primary) shadow-sm ring-2 ring-(--color-primary)/30'
                      : 'border-(--color-border-1) hover:border-(--color-border-2)'
                  }`}
                >
                  <div className="relative h-12 w-full" style={{ background: item.background }}>
                    {isSelected ? (
                      <div className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-(--color-primary) text-[9px] text-white shadow-xs">
                        <CheckOutlined />
                      </div>
                    ) : null}
                  </div>
                  <div className="flex items-center justify-between bg-(--color-bg-2) px-2 py-1 text-[11px]">
                    <span
                      className={`truncate font-medium ${
                        isSelected ? 'text-(--color-primary)' : 'text-(--color-text-2)'
                      }`}
                    >
                      {t(`opsAnalysis.screen.wallpaper.${item.key}`) || item.key}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </InspectorSection>

      {/* 4. 显示方式适配 */}
      <InspectorSection
        title={
          <div className="flex items-center gap-1">
            <span>{t('opsAnalysis.screen.fitAdapter')}</span>
            <Tooltip title={t('opsAnalysis.screen.fitAdapterHint')}>
              <QuestionCircleOutlined className="cursor-help text-xs text-(--color-text-3) hover:text-(--color-primary)" />
            </Tooltip>
          </div>
        }
        icon={<DesktopOutlined />}
      >
        <Segmented
          block
          value={adapter}
          options={[
            { label: t('opsAnalysis.screen.fitFill'), value: 'fill' },
            { label: t('opsAnalysis.screen.fitWidth'), value: 'fitWidth' },
            { label: t('opsAnalysis.screen.fitHeight'), value: 'fitHeight' },
          ]}
          onChange={(next) =>
            applyViewport({
              ...viewport,
              adapter: next as ScreenFitAdapter,
            })
          }
        />
      </InspectorSection>
    </div>
  );
};

// ==========================================
// 形状样式表单分组（ShapeStyleFields）
// ==========================================

const ShapeStyleFields: React.FC<{
  shape: ScreenShapeKind;
  value?: ScreenShapeStyle;
  onChange: (next: { shape: ScreenShapeKind; shapeStyle: ScreenShapeStyle }) => void;
  onFieldEditEnd?: () => void;
}> = ({ shape, value, onChange, onFieldEditEnd }) => {
  const { t } = useTranslation();
  const style = resolveScreenShapeStyle(value);
  const patch = (next: Partial<ScreenShapeStyle>) => {
    onChange({
      shape,
      shapeStyle: resolveScreenShapeStyle({ ...style, ...next }),
    });
  };

  const fillMode: 'none' | 'solid' | 'gradient' = style.hideBackground
    ? 'none'
    : style.gradient
      ? 'gradient'
      : 'solid';

  const handleFillModeChange = (mode: string) => {
    if (mode === 'none') {
      patch({ hideBackground: true, gradient: false });
    } else if (mode === 'solid') {
      patch({ hideBackground: false, gradient: false });
    } else if (mode === 'gradient') {
      patch({ hideBackground: false, gradient: true });
    }
  };

  return (
    <>
      {/* 1. 填充与背景 */}
      <InspectorSection
        title={t('opsAnalysis.screen.shapeFill')}
        icon={<BgColorsOutlined />}
      >
        <div className="space-y-1.5">
          <div className="text-xs text-(--color-text-2)">{t('opsAnalysis.screen.shape.fillMode')}</div>
          <Segmented
            block
            size="small"
            value={fillMode}
            onChange={(val) => handleFillModeChange(val as string)}
            options={[
              { label: t('opsAnalysis.screen.shape.fillNone'), value: 'none' },
              { label: t('opsAnalysis.screen.shape.fillSolid'), value: 'solid' },
              { label: t('opsAnalysis.screen.shape.fillGradient'), value: 'gradient' },
            ]}
          />
        </div>

        {fillMode === 'solid' && (
          <div className="flex items-center justify-between text-xs text-(--color-text-2)">
            <span>{t('opsAnalysis.screen.shape.backgroundColor')}</span>
            <ColorPicker
              showText
              value={style.backgroundColor}
              onChange={(nextColor) => patch({ backgroundColor: nextColor.toRgbString() })}
              onChangeComplete={() => onFieldEditEnd?.()}
            />
          </div>
        )}

        {fillMode === 'gradient' && (
          <div className="space-y-2.5 rounded-md border border-(--color-border-1)/60 bg-(--color-fill-1)/20 p-2 text-xs">
            <div className="flex items-center justify-between text-(--color-text-2)">
              <span>{t('opsAnalysis.screen.shape.gradientDirection')}</span>
              <Segmented
                size="small"
                value={style.gradientDirection}
                onChange={(gradientDirection) =>
                  patch({
                    gradientDirection: gradientDirection as ScreenShapeStyle['gradientDirection'],
                  })
                }
                options={[
                  { label: t('opsAnalysis.screen.shape.gradientVertical'), value: 'vertical' },
                  { label: t('opsAnalysis.screen.shape.gradientHorizontal'), value: 'horizontal' },
                ]}
              />
            </div>
            <div className="flex items-center justify-between text-(--color-text-2)">
              <span>{t('opsAnalysis.screen.shape.gradientStart')}</span>
              <ColorPicker
                showText
                value={style.gradientStart}
                onChange={(c) => patch({ gradientStart: c.toRgbString() })}
                onChangeComplete={() => onFieldEditEnd?.()}
              />
            </div>
            <div className="flex items-center justify-between text-(--color-text-2)">
              <span>{t('opsAnalysis.screen.shape.gradientEnd')}</span>
              <ColorPicker
                showText
                value={style.gradientEnd}
                onChange={(c) => patch({ gradientEnd: c.toRgbString() })}
                onChangeComplete={() => onFieldEditEnd?.()}
              />
            </div>
          </div>
        )}
      </InspectorSection>

      {/* 2. 边框描边 */}
      <InspectorSection
        title={t('opsAnalysis.screen.shapeStroke')}
        icon={<BorderOutlined />}
      >
        <div className="flex items-center justify-between text-xs text-(--color-text-2)">
          <span>{t('opsAnalysis.screen.shape.hideBorder')}</span>
          <Switch
            size="small"
            checked={style.hideBorder}
            onChange={(hideBorder) => patch({ hideBorder })}
          />
        </div>
        {!style.hideBorder && (
          <>
            <div className="flex items-center justify-between text-xs text-(--color-text-2)">
              <span>{t('opsAnalysis.screen.shape.borderColor')}</span>
              <ColorPicker
                showText
                value={style.borderColor}
                onChange={(nextColor) => patch({ borderColor: nextColor.toRgbString() })}
                onChangeComplete={() => onFieldEditEnd?.()}
              />
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-(--color-text-2)">
                <span>{t('opsAnalysis.screen.shape.borderWidth')}</span>
                <span className="font-mono text-xs text-(--color-text-1)">
                  {style.borderWidth} px
                </span>
              </div>
              <Slider
                min={0}
                max={40}
                value={style.borderWidth}
                className="m-0"
                onChange={(borderWidth) => patch({ borderWidth })}
                onChangeComplete={() => onFieldEditEnd?.()}
              />
            </div>
          </>
        )}
      </InspectorSection>

      {/* 3. 阴影与外发光 */}
      <InspectorSection
        title={t('opsAnalysis.screen.shapeShadow')}
        icon={<PictureOutlined />}
      >
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-(--color-text-2)">
            <span>{t('opsAnalysis.screen.shape.shadow')}</span>
            <span className="font-mono text-xs text-(--color-text-1)">
              {style.shadow} px
            </span>
          </div>
          <Slider
            min={0}
            max={80}
            value={style.shadow}
            className="m-0"
            onChange={(shadow) => patch({ shadow })}
            onChangeComplete={() => onFieldEditEnd?.()}
          />
        </div>
      </InspectorSection>
    </>
  );
};

// ==========================================
// 核心属性检查器（ScreenStyleInspector）
// ==========================================

interface ScreenStyleInspectorProps {
  item: ScreenItem;
  viewport: ScreenViewportConfig;
  onChange: (next: ScreenItem, editedKey?: ScreenGeometryField) => void;
  onFieldEditEnd?: () => void;
}

export const ScreenStyleInspector: React.FC<ScreenStyleInspectorProps> = ({
  item,
  viewport,
  onChange,
  onFieldEditEnd,
}) => {
  const { t } = useTranslation();
  const [changingTitlePreset, setChangingTitlePreset] = useState(false);
  const [changingDecoPreset, setChangingDecoPreset] = useState(false);
  const sampleClockDate = useMemo(() => new Date(), []);

  useEffect(() => {
    setChangingTitlePreset(false);
    setChangingDecoPreset(false);
  }, [item.id]);

  // 1. 图表组件的样式表单
  if (isScreenWidgetItem(item)) {
    const appearance = resolveScreenWidgetAppearance(
      item.chartType,
      item.valueConfig?.appearance,
    );
    const patchAppearance = (next: ScreenWidgetAppearance) => {
      onChange({
        ...item,
        valueConfig: {
          ...item.valueConfig,
          appearance: next,
        },
      });
    };

    return (
      <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto px-3 py-3">
        {/* 容器与边框风格 */}
        <InspectorSection
          title={t('opsAnalysis.screen.containerStyle')}
          icon={<BlockOutlined />}
        >
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => patchAppearance({ ...appearance, frame: 'panel' })}
              className={`flex flex-col items-center justify-center gap-1.5 rounded-lg border p-2.5 text-xs transition-all ${
                appearance.frame !== 'bare'
                  ? 'border-(--color-primary) bg-(--color-primary)/10 font-semibold text-(--color-primary)'
                  : 'border-(--color-border-1) bg-(--color-bg-1) text-(--color-text-2) hover:border-(--color-border-2)'
              }`}
            >
              <BorderOuterOutlined className="text-base" />
              <span>{t('opsAnalysis.screen.widgetFramePanel')}</span>
            </button>
            <button
              type="button"
              onClick={() => patchAppearance({ ...appearance, frame: 'bare' })}
              className={`flex flex-col items-center justify-center gap-1.5 rounded-lg border p-2.5 text-xs transition-all ${
                appearance.frame === 'bare'
                  ? 'border-(--color-primary) bg-(--color-primary)/10 font-semibold text-(--color-primary)'
                  : 'border-(--color-border-1) bg-(--color-bg-1) text-(--color-text-2) hover:border-(--color-border-2)'
              }`}
            >
              <BorderOutlined className="text-base" />
              <span>{t('opsAnalysis.screen.widgetFrameBare')}</span>
            </button>
          </div>
        </InspectorSection>

        {/* 紧凑尺寸与位置 */}
        <CompactGeometryGrid item={item} viewport={viewport} onChange={onChange} />
      </div>
    );
  }

  // 2. 纯展示元素（文本、标题框、时钟、形状、边框）
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto px-3 py-3">
      {/* 文本元素 */}
      {isScreenTextItem(item) && (
        <>
          <InspectorHeader
            icon={<FontSizeOutlined />}
            title={t('opsAnalysis.screen.elementText')}
            badge={t('opsAnalysis.screen.textContent')}
          />
          <InspectorSection
            title={t('opsAnalysis.screen.textContent')}
            icon={<FontSizeOutlined />}
          >
            <Input.TextArea
              value={item.content}
              rows={4}
              placeholder={t('opsAnalysis.screen.textPlaceholder')}
              className="text-xs"
              onChange={(event) => onChange({ ...item, content: event.target.value })}
            />
          </InspectorSection>

          <InspectorSection
            title={t('opsAnalysis.screen.textTypography')}
            icon={<FontColorsOutlined />}
          >
            <TextStyleFields
              value={item.textStyle}
              theme={viewport.theme}
              onChange={(textStyle) => onChange({ ...item, textStyle })}
              onFieldEditEnd={onFieldEditEnd}
            />
          </InspectorSection>
        </>
      )}

      {/* 标题框 */}
      {isScreenTitleFrameItem(item) && (
        <>
          <InspectorHeader
            icon={<FontColorsOutlined />}
            title={t(`opsAnalysis.screen.titleFrame.${item.preset}`) || item.preset}
            badge={`${t('opsAnalysis.screen.elementTitle')} · ${item.preset}`}
            extra={
              <Button
                size="small"
                type="link"
                className="h-auto p-0 text-xs"
                onClick={() => setChangingTitlePreset((prev) => !prev)}
              >
                {changingTitlePreset ? t('common.collapse') : t('opsAnalysis.screen.changePreset')}
              </Button>
            }
          />

          {/* 预设无损快速切换 */}
          {changingTitlePreset && (
            <InspectorSection
              title={t('opsAnalysis.screen.titleFramePreset')}
              icon={<PictureOutlined />}
            >
              <div className="grid grid-cols-2 gap-2">
                {TITLE_FRAME_PRESETS.map((preset) => {
                  const isCur = item.preset === preset;
                  return (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => onChange({ ...item, preset })}
                      className={`flex flex-col overflow-hidden rounded border text-left transition-all ${
                        isCur
                          ? 'border-(--color-primary) ring-2 ring-(--color-primary)/30'
                          : 'border-(--color-border-1) hover:border-(--color-border-2)'
                      }`}
                    >
                      <img
                        alt=""
                        src={titleFrameThumbSrc(preset)}
                        className="h-9 w-full object-cover"
                      />
                      <span className="truncate bg-(--color-bg-2) px-1.5 py-1 text-center text-[10px] text-(--color-text-2)">
                        {t(`opsAnalysis.screen.titleFrame.${preset}`)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </InspectorSection>
          )}

          <InspectorSection
            title={t('opsAnalysis.screen.textContent')}
            icon={<FontSizeOutlined />}
          >
            <Input
              value={item.content}
              allowClear
              placeholder={t('opsAnalysis.screen.titlePlaceholder')}
              className="text-xs"
              onChange={(event) => onChange({ ...item, content: event.target.value })}
            />
          </InspectorSection>

          <InspectorSection
            title={t('opsAnalysis.screen.textTypography')}
            icon={<FontColorsOutlined />}
          >
            <TextStyleFields
              value={item.textStyle}
              theme={viewport.theme}
              minFontSize={14}
              maxFontSize={64}
              onChange={(textStyle) => onChange({ ...item, textStyle })}
              onFieldEditEnd={onFieldEditEnd}
            />
          </InspectorSection>
        </>
      )}

      {/* 数字时钟 */}
      {isScreenClockItem(item) && (
        <>
          <InspectorHeader
            icon={<ClockCircleOutlined />}
            title={t('opsAnalysis.screen.elementClock')}
            badge={item.format}
          />
          <InspectorSection
            title={t('opsAnalysis.screen.clockFormat')}
            icon={<ClockCircleOutlined />}
          >
            <Select
              className="w-full text-xs"
              value={item.format}
              onChange={(format: ScreenClockFormatId) =>
                onChange({ ...item, format })
              }
              options={SCREEN_CLOCK_FORMATS.map((format) => ({
                label: (
                  <div className="flex items-center justify-between gap-2 py-0.5 text-xs">
                    <span className="font-mono text-(--color-text-1)">
                      {formatScreenClockByPreset(sampleClockDate, format)}
                    </span>
                    <span className="text-[10px] text-(--color-text-3)">
                      ({t(CLOCK_FORMAT_LABEL_KEYS[format])})
                    </span>
                  </div>
                ),
                value: format,
              }))}
            />
          </InspectorSection>

          <InspectorSection
            title={t('opsAnalysis.screen.clockStyle')}
            icon={<FontColorsOutlined />}
          >
            <TextStyleFields
              value={item.textStyle}
              theme={viewport.theme}
              fields={['fontSize', 'color']}
              minFontSize={12}
              maxFontSize={48}
              onChange={(textStyle) => onChange({ ...item, textStyle })}
              onFieldEditEnd={onFieldEditEnd}
            />
          </InspectorSection>
        </>
      )}

      {/* 几何形状 */}
      {isScreenShapeItem(item) && (
        <>
          <InspectorHeader
            icon={<BlockOutlined />}
            title={t(`opsAnalysis.screen.shape.${item.shape}`)}
            badge={item.shape}
          />
          <ShapeStyleFields
            shape={item.shape}
            value={item.shapeStyle}
            onChange={(next) => onChange({ ...item, ...next })}
            onFieldEditEnd={onFieldEditEnd}
          />
        </>
      )}

      {/* 装饰边框与线条 */}
      {isScreenDecorationItem(item) && (
        <>
          <InspectorHeader
            icon={<BorderOuterOutlined />}
            title={
              item.decorationType === 'panelFrame'
                ? t(`opsAnalysis.screen.panelFrame.${resolvePanelFramePreset(item.preset)}`)
                : item.decorationType === 'divider'
                  ? t(`opsAnalysis.screen.divider.${resolveDividerPreset(item.preset)}`)
                  : t('opsAnalysis.screen.elementCorner')
            }
            badge={`${t('opsAnalysis.screen.elementPanelFrame')} · ${item.preset}`}
            extra={
              item.decorationType === 'panelFrame' || item.decorationType === 'divider' ? (
                <Button
                  size="small"
                  type="link"
                  className="h-auto p-0 text-xs"
                  onClick={() => setChangingDecoPreset((prev) => !prev)}
                >
                  {changingDecoPreset ? t('common.collapse') : t('opsAnalysis.screen.changePreset')}
                </Button>
              ) : null
            }
          />
          {changingDecoPreset && item.decorationType === 'panelFrame' && (
            <InspectorSection
              title={t('opsAnalysis.screen.changePreset')}
              icon={<PictureOutlined />}
            >
              <div className="grid grid-cols-3 gap-1.5">
                {SCREEN_PANEL_FRAME_PRESETS.map((preset) => {
                  const isCur = item.preset === preset;
                  return (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => onChange({ ...item, preset })}
                      className={`flex flex-col items-center overflow-hidden rounded border p-1 text-center transition-all ${
                        isCur
                          ? 'border-(--color-primary) bg-(--color-primary)/10 ring-1 ring-(--color-primary)'
                          : 'border-(--color-border-1) bg-(--color-bg-1) hover:border-(--color-border-2)'
                      }`}
                    >
                      <div className="h-10 w-full overflow-hidden rounded-[2px] bg-[#071422]">
                        <DecorationSkin item={{ decorationType: 'panelFrame', preset }} preview />
                      </div>
                      <span className={`mt-1 truncate text-[10px] ${isCur ? 'font-medium text-(--color-primary)' : 'text-(--color-text-2)'}`}>
                        {t(`opsAnalysis.screen.panelFrame.${preset}`)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </InspectorSection>
          )}
          {changingDecoPreset && item.decorationType === 'divider' && (
            <InspectorSection
              title={t('opsAnalysis.screen.changePreset')}
              icon={<PictureOutlined />}
            >
              <div className="grid grid-cols-2 gap-1.5">
                {SCREEN_DIVIDER_PRESETS.map((preset) => {
                  const isCur = item.preset === preset;
                  return (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => onChange({ ...item, preset })}
                      className={`flex flex-col items-center overflow-hidden rounded border p-1 text-center transition-all ${
                        isCur
                          ? 'border-(--color-primary) bg-(--color-primary)/10 ring-1 ring-(--color-primary)'
                          : 'border-(--color-border-1) bg-(--color-bg-1) hover:border-(--color-border-2)'
                      }`}
                    >
                      <div className="flex h-8 w-full items-center justify-center overflow-hidden rounded-[2px] bg-[#071422] px-1">
                        <DecorationSkin item={{ decorationType: 'divider', preset }} preview />
                      </div>
                      <span className={`mt-1 truncate text-[10px] ${isCur ? 'font-medium text-(--color-primary)' : 'text-(--color-text-2)'}`}>
                        {t(`opsAnalysis.screen.divider.${preset}`)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </InspectorSection>
          )}
        </>
      )}

      {/* 紧凑尺寸与位置（通用） */}
      <CompactGeometryGrid item={item} viewport={viewport} onChange={onChange} />
    </div>
  );
};
