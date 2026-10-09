'use client';

import React, { useLayoutEffect, useRef, useState } from 'react';
import type {
  ScreenDecorationItem,
  ScreenPanelFramePresetId,
  ScreenTextStyleConfig,
  ScreenTitleFrameItem,
  ScreenTitleFramePresetId,
} from '@/app/ops-analysis/types/screen';
import title01 from '../assets/chrome/title-01.png';
import title02 from '../assets/chrome/title-02.png';
import title04 from '../assets/chrome/title-04.png';
import title05 from '../assets/chrome/title-05.png';
import title06 from '../assets/chrome/title-06.png';
import title03 from '../assets/chrome/title-03.png';
import smallTitle4Left from '../assets/chrome/small-title4-left.png';
import smallTitle4Dec from '../assets/chrome/small-title4-dec.png';
import smallTitle4Light from '../assets/chrome/small-title4-light.png';
import smallTitle4Scan from '../assets/chrome/small-title4-scanlight.png';
import smallTitle8Bg from '../assets/chrome/small-title8-bg.png';
import smallTitle8Line from '../assets/chrome/small-title8-line.png';
import smallTitle5Light from '../assets/chrome/small-title5-light.png';
import smallTitle6Left from '../assets/chrome/small-title6-left.png';
import smallTitle6Middle from '../assets/chrome/small-title6-middle.png';
import smallTitle6Right from '../assets/chrome/small-title6-right.png';
import heroThumb1 from '../assets/chrome/thumbs/screen-title-01.png';
import heroThumb2 from '../assets/chrome/thumbs/screen-title-02.png';
import heroThumb3 from '../assets/chrome/thumbs/screen-title-03.png';
import heroThumb4 from '../assets/chrome/thumbs/screen-title-04.png';
import heroThumb5 from '../assets/chrome/thumbs/screen-title-05.png';
import heroThumb6 from '../assets/chrome/thumbs/screen-title-06.png';
import sectionThumb1 from '../assets/chrome/thumbs/small-title4.png';
import sectionThumb2 from '../assets/chrome/thumbs/small-title8.png';
import sectionThumb3 from '../assets/chrome/thumbs/small-title5.png';
import sectionThumb4 from '../assets/chrome/thumbs/small-title6.png';
import border21 from '../assets/chrome/border-21.png';
import border22 from '../assets/chrome/border-22.png';
import border23 from '../assets/chrome/border-23.png';
import border25 from '../assets/chrome/border-25.png';
import border1 from '../assets/chrome/border-1.png';
import border16 from '../assets/chrome/border-16.png';
import border20 from '../assets/chrome/border-20.png';
import border24 from '../assets/chrome/border-24.png';
import tech01 from '../assets/chrome/tech01.png';
import border27Lt from '../assets/chrome/border-27-lt.png';
import {
  resolveDividerPreset,
  resolvePanelFramePreset,
} from '../utils/screenItems';

type ImageAsset = string | { src: string };

const assetSrc = (asset: ImageAsset) =>
  typeof asset === 'string' ? asset : asset.src;

const colorVar = (token?: ScreenTextStyleConfig['color']) => {
  if (token === 'muted') return 'var(--screen-clock-color)';
  if (token === 'accent') return 'var(--screen-chrome-accent)';
  return 'var(--screen-title-color)';
};

export const screenChromeTextStyle = (
  style?: ScreenTextStyleConfig,
  fallback?: Partial<ScreenTextStyleConfig>,
): React.CSSProperties => ({
  fontSize: style?.fontSize ?? fallback?.fontSize ?? 20,
  fontWeight: style?.fontWeight ?? fallback?.fontWeight ?? 600,
  color: colorVar(style?.color ?? fallback?.color),
  textAlign: style?.align ?? fallback?.align ?? 'left',
  lineHeight: 1.2,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  textShadow: 'var(--screen-title-text-shadow)',
});

const VisionImg: React.FC<{
  src: ImageAsset;
  className?: string;
  style?: React.CSSProperties;
  /** Vision 素材黑底表示空，用 lighten 透出壁纸，避免 screen 把青色洗灰。 */
  punchBlack?: boolean;
}> = ({ src, className, style, punchBlack = false }) => (
  <img
    alt=""
    draggable={false}
    src={assetSrc(src)}
    className={`pointer-events-none select-none ${punchBlack ? 'mix-blend-lighten' : ''} ${className || ''}`}
    style={style}
  />
);

const TITLE_FRAME_THUMBS: Record<ScreenTitleFramePresetId, ImageAsset> = {
  'hero-1': heroThumb1,
  'hero-2': heroThumb2,
  'hero-3': heroThumb4,
  'hero-4': heroThumb5,
  'hero-5': heroThumb6,
  'hero-6': heroThumb3,
  'section-1': sectionThumb1,
  'section-2': sectionThumb2,
  'section-3': sectionThumb3,
  'section-4': sectionThumb4,
};

/** 目录缩略图用参考项目里已经排好版的静态图，不在窄格子里重绘标题皮肤。 */
export const titleFrameThumbSrc = (preset: ScreenTitleFramePresetId) =>
  assetSrc(TITLE_FRAME_THUMBS[preset]);

const HeroTitle: React.FC<{
  item: ScreenTitleFrameItem;
  src: ImageAsset;
  fontSize: number;
}> = ({ item, src, fontSize }) => (
  <div className="relative h-full w-full overflow-hidden">
    <VisionImg
      src={src}
      punchBlack
      className="absolute inset-0 h-full w-full object-fill"
    />
    <div className="absolute inset-0 flex items-center justify-center px-10 text-center">
      <span
        className="max-w-[78%] truncate"
        style={screenChromeTextStyle(item.textStyle, {
          fontSize,
          fontWeight: 700,
          align: 'center',
        })}
      >
        {item.content || ''}
      </span>
    </div>
  </div>
);

const SectionTitle4: React.FC<{ item: ScreenTitleFrameItem }> = ({ item }) => (
  <div className="relative flex h-full min-h-[20px] w-full overflow-hidden">
    <VisionImg src={smallTitle4Left} punchBlack className="h-full w-[34px] shrink-0" />
    <div className="relative flex min-w-0 flex-1 items-center justify-between">
      <div
        className="absolute inset-0 z-0"
        style={{
          backgroundImage:
            'linear-gradient(-89deg, color-mix(in srgb, var(--screen-chrome-accent) 8%, transparent) 0%, color-mix(in srgb, var(--screen-chrome-accent) 30%, transparent) 100%)',
        }}
      />
      <VisionImg
        src={smallTitle4Light}
        punchBlack
        className="absolute inset-0 z-0 h-full w-full"
      />
      <span
        className="relative z-1 min-w-0 flex-1 truncate whitespace-nowrap px-3"
        style={screenChromeTextStyle(item.textStyle, { fontSize: 18, fontWeight: 700 })}
      >
        {item.content || ''}
      </span>
      <VisionImg src={smallTitle4Dec} punchBlack className="relative z-1 mr-5 h-[10px] w-[131px] shrink-0" />
    </div>
    <VisionImg
      src={smallTitle4Scan}
      punchBlack
      className="absolute top-0 left-1 z-2 h-full w-[38px] opacity-0"
      style={{ animation: 'screen-chrome-title4-scan 2.5s linear infinite' }}
    />
  </div>
);

const SectionTitle8: React.FC<{ item: ScreenTitleFrameItem }> = ({ item }) => (
  <div className="relative h-full min-h-[20px] w-full overflow-hidden">
    <div
      className="absolute inset-0 z-0"
      style={{
        backgroundImage:
          'linear-gradient(270deg, color-mix(in srgb, var(--screen-stage-bg) 84%, transparent) 0%, color-mix(in srgb, var(--screen-canvas-bg) 84%, transparent) 100%)',
      }}
    />
    <VisionImg src={smallTitle8Bg} className="absolute inset-0 z-1 h-full w-full" />
    <VisionImg
      src={smallTitle8Line}
      className="absolute top-0 left-0 z-0 h-full w-[833px] max-w-none"
      style={{ animation: 'screen-chrome-title8-move 1.2s linear infinite' }}
    />
    <div className="absolute inset-0 z-2 flex items-center px-2">
      <span className="h-0.5 w-2 shrink-0 bg-(--screen-chrome-accent)" />
      <span
        className="min-w-0 flex-1 truncate px-2 text-center"
        style={screenChromeTextStyle(item.textStyle, {
          fontSize: 16,
          fontWeight: 700,
          align: 'center',
        })}
      >
        {item.content || ''}
      </span>
      <span className="h-0.5 w-2 shrink-0 bg-(--screen-chrome-accent)" />
    </div>
  </div>
);

const SectionTitle5: React.FC<{ item: ScreenTitleFrameItem }> = ({ item }) => (
  <div className="relative h-full min-h-[20px] w-full overflow-hidden">
    <VisionImg
      src={smallTitle5Light}
      punchBlack
      className="absolute inset-0 h-full w-full object-fill"
    />
    <div className="absolute inset-0 flex items-center justify-between px-3">
      <span className="h-1.5 w-1.5 shrink-0 bg-(--screen-chrome-accent)" />
      <span
        className="min-w-0 flex-1 truncate px-2 text-center"
        style={screenChromeTextStyle(item.textStyle, {
          fontSize: 16,
          fontWeight: 700,
          align: 'center',
        })}
      >
        {item.content || ''}
      </span>
      <span className="h-1.5 w-1.5 shrink-0 bg-(--screen-chrome-accent)" />
    </div>
  </div>
);

const SectionTitle6: React.FC<{ item: ScreenTitleFrameItem }> = ({ item }) => (
  <div className="relative flex h-full min-h-[20px] w-full overflow-hidden">
    <VisionImg
      src={smallTitle6Left}
      punchBlack
      className="h-full w-[47%] shrink-0 object-fill"
    />
    <div className="relative h-full min-w-0 flex-1">
      <div
        className="absolute inset-x-0 top-[15%] bottom-0"
        style={{
          backgroundImage:
            'linear-gradient(-89deg, color-mix(in srgb, var(--screen-chrome-accent) 18%, transparent) 0%, color-mix(in srgb, var(--screen-chrome-accent) 30%, transparent) 100%)',
        }}
      />
      <VisionImg
        src={smallTitle6Middle}
        punchBlack
        className="relative z-1 h-full w-full object-fill"
      />
    </div>
    <VisionImg
      src={smallTitle6Right}
      punchBlack
      className="h-full w-[17%] shrink-0 object-fill"
    />
    <span
      className="absolute inset-y-0 left-0 z-2 flex w-[58%] items-center truncate pl-3"
      style={screenChromeTextStyle(item.textStyle, { fontSize: 16, fontWeight: 700 })}
    >
      {item.content || ''}
    </span>
  </div>
);

export const TitleFrameSkin: React.FC<{
  item: Pick<ScreenTitleFrameItem, 'preset' | 'content' | 'textStyle'>;
}> = ({ item }) => {
  const preset: ScreenTitleFramePresetId = item.preset;
  const frame = item as ScreenTitleFrameItem;
  if (preset === 'hero-2') return <HeroTitle item={frame} src={title02} fontSize={24} />;
  if (preset === 'hero-3') return <HeroTitle item={frame} src={title04} fontSize={22} />;
  if (preset === 'hero-4') return <HeroTitle item={frame} src={title05} fontSize={22} />;
  if (preset === 'hero-5') return <HeroTitle item={frame} src={title06} fontSize={20} />;
  if (preset === 'hero-6') return <HeroTitle item={frame} src={title03} fontSize={22} />;
  if (preset === 'section-1') return <SectionTitle4 item={frame} />;
  if (preset === 'section-2') return <SectionTitle8 item={frame} />;
  if (preset === 'section-3') return <SectionTitle5 item={frame} />;
  if (preset === 'section-4') return <SectionTitle6 item={frame} />;
  return <HeroTitle item={frame} src={title01} fontSize={26} />;
};

const visionBorder21Width = (width: number, height: number) => {
  if (height > 381 && width > 742) return 83;
  if (height > 190 && width > 371) return 43;
  if (height > 95 && width > 185) return 23;
  if (height > 50 && width > 90) return 13;
  return 8;
};

type BorderImageMode = 'fixed-83' | 'fixed-25' | 'fluid' | 'tech' | 'fill';

const PANEL_FRAME_SKIN: Record<
  ScreenPanelFramePresetId,
  { src: ImageAsset; mode: BorderImageMode }
> = {
  'border-21': { src: border21, mode: 'fixed-83' },
  'border-22': { src: border22, mode: 'fixed-83' },
  'border-23': { src: border23, mode: 'fixed-83' },
  'border-25': { src: border25, mode: 'fixed-25' },
  'border-1': { src: border1, mode: 'fluid' },
  tech: { src: tech01, mode: 'tech' },
  'border-16': { src: border16, mode: 'fill' },
  'border-20': { src: border20, mode: 'fill' },
  'border-24': { src: border24, mode: 'fill' },
};

const VisionBorderImage: React.FC<{
  src: ImageAsset;
  mode: Exclude<BorderImageMode, 'fill'>;
}> = ({ src, mode }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 320, height: 180 });

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const update = () =>
      setBox({ width: node.clientWidth, height: node.clientHeight });
    update();
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    observer?.observe(node);
    return () => observer?.disconnect();
  }, []);

  const fluidTB = box.height > 200 ? 100 : Math.max(8, box.height / 2);
  const fluidLR = box.width > 300 ? 150 : Math.max(8, box.width / 2);
  const fixedScale = Math.min(1, box.width / 742, box.height / 381);
  const sliceTB =
    mode === 'tech'
      ? Math.min(fluidTB, Math.max(8, box.height * 0.28))
      : mode === 'fluid'
        ? fluidTB
        : mode === 'fixed-25'
          ? Math.max(8, Math.round(100 * fixedScale))
          : 83;
  const sliceLR =
    mode === 'tech'
      ? Math.min(fluidLR, Math.max(8, box.width * 0.28))
      : mode === 'fluid'
        ? fluidLR
        : mode === 'fixed-25'
          ? Math.max(8, Math.round(95 * fixedScale))
          : 83;
  const borderWidth =
    mode === 'fixed-83'
      ? `${Math.min(visionBorder21Width(box.width, box.height), Math.max(8, Math.floor(Math.min(box.width, box.height) * 0.18)))}px`
      : `${sliceTB}px ${sliceLR}px`;

  return (
    <div ref={ref} className="h-full w-full">
      <div
        className="box-border h-full w-full"
        style={{
          borderStyle: 'solid',
          borderColor: 'transparent',
          borderWidth,
          borderImageSource: `url("${assetSrc(src)}")`,
          borderImageSlice: `${sliceTB} ${sliceLR}`,
          borderImageRepeat: 'stretch',
        }}
      />
    </div>
  );
};

const CornerSkin: React.FC<{ preset: string }> = ({ preset }) => (
  <VisionImg
    src={border27Lt}
    punchBlack
    className={
      // 右角在左上素材上水平翻转。原点必须用顶边中点，若用右上角会把图形翻出选中框。
      preset === 'b'
        ? 'h-full w-full origin-top object-contain object-left-top -scale-x-100'
        : 'h-full w-full object-contain object-left-top'
    }
  />
);

const LineTicks: React.FC<{ fit?: boolean }> = ({ fit = false }) => (
  <div className="flex h-full w-full items-center gap-1 overflow-hidden">
    {Array.from({ length: fit ? 8 : 16 }, (_, index) => (
      <span
        key={index}
        className={
          fit
            ? 'h-1/2 min-w-0 flex-1 bg-(--screen-chrome-accent) opacity-50'
            : 'h-1/2 w-2 shrink-0 bg-(--screen-chrome-accent) opacity-50'
        }
      />
    ))}
  </div>
);

const DividerSkin: React.FC<{ preset: string; preview?: boolean }> = ({
  preset,
  preview = false,
}) => {
  const resolved = resolveDividerPreset(preset);
  if (resolved === 'line-dec') {
    return (
      <div className="flex h-full w-full items-center" data-decoration={resolved}>
        <VisionImg src={smallTitle4Dec} punchBlack className="h-[10px] w-full" />
      </div>
    );
  }
  if (resolved === 'line-2') {
    return (
      <div
        className="flex h-full w-full flex-col justify-center"
        data-decoration={resolved}
      >
        <div className="mb-1 flex justify-end gap-1.5">
          <span className="h-1 w-2.5 bg-(--screen-chrome-accent) opacity-30" />
          <span className="h-1 w-2.5 bg-(--screen-chrome-accent) opacity-50" />
          <span className="h-1 w-2.5 bg-(--screen-chrome-accent)" />
        </div>
        <div className="w-full border-b border-dashed border-(--screen-chrome-accent)" />
      </div>
    );
  }
  if (resolved === 'line-3') {
    return (
      <div data-decoration={resolved} className="h-full w-full">
        <LineTicks fit={preview} />
      </div>
    );
  }
  if (resolved === 'line-4') {
    return (
      <div data-decoration={resolved} className="relative h-full w-full">
        <svg
          className="h-full w-full opacity-80"
          viewBox="0 0 100 24"
          preserveAspectRatio="none"
          aria-hidden
        >
          <polyline
            points="0,22 40,22 52,3 100,3"
            fill="none"
            stroke="var(--screen-chrome-accent)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          <circle
            cx="98"
            cy="3"
            r="1.6"
            fill="none"
            stroke="var(--screen-chrome-accent)"
          />
        </svg>
        <div className="absolute inset-0 flex items-start justify-center pt-1">
          {[1, 0.55, 0.28, 0.12].map((opacity) => (
            <span
              key={opacity}
              className="ml-[2%] h-full w-[2%] origin-bottom -skew-x-[40deg] bg-(--screen-chrome-accent)"
              style={{ opacity }}
            />
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="flex h-full w-full items-center" data-decoration={resolved}>
      <span className="h-0.5 w-2 shrink-0 bg-(--screen-chrome-accent)" />
      <span className="mx-1 h-px min-w-0 flex-1 bg-(--screen-chrome-accent) opacity-30" />
      <span className="h-0.5 w-2 shrink-0 bg-(--screen-chrome-accent)" />
    </div>
  );
};

export const DecorationSkin: React.FC<{
  item: Pick<ScreenDecorationItem, 'decorationType' | 'preset'>;
  /** 窄缩略图里不要用超出卡片的刻度，否则拖拽预览会带上相邻卡片。 */
  preview?: boolean;
}> = ({ item, preview = false }) => {
  if (item.decorationType === 'divider') {
    return <DividerSkin preset={item.preset} preview={preview} />;
  }
  if (item.decorationType === 'corner') {
    return <CornerSkin preset={item.preset} />;
  }
  const frame = resolvePanelFramePreset(item.preset);
  const skin = PANEL_FRAME_SKIN[frame];
  return (
    <div className="h-full w-full" data-decoration={frame}>
      {skin.mode === 'fill' ? (
        <VisionImg src={skin.src} punchBlack className="h-full w-full object-fill" />
      ) : (
        <VisionBorderImage src={skin.src} mode={skin.mode} />
      )}
    </div>
  );
};

export const ScreenChromeSkinStyles: React.FC = () => (
  <style>{`
    @keyframes screen-chrome-shine {
      0%, 100% { opacity: 0.22; }
      50% { opacity: 0.82; }
    }
    @keyframes screen-chrome-title4-scan {
      20% { opacity: 0; left: 4px; }
      40% { opacity: 1; }
      100% { opacity: 0; left: calc(100% - 185px); }
    }
    @keyframes screen-chrome-title8-move {
      0% { transform: translateX(0); }
      100% { transform: translateX(-34px); }
    }
  `}</style>
);

