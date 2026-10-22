'use client';

import React, { useEffect, useState } from 'react';
import InteractionTitleIcon from '@/app/ops-analysis/components/interactionTitleIcon';
import { useFilterTemplateText } from '@/app/ops-analysis/context/filterTemplate';
import { useInteractionSurface } from '@/app/ops-analysis/context/interactionSurface';
import type {
  ScreenClockItem,
  ScreenItem,
  ScreenTextItem,
  ScreenTextStyleConfig,
} from '@/app/ops-analysis/types/screen';
import {
  readWidgetInteraction,
  shouldShowInteractionEntry,
} from '@/app/ops-analysis/utils/interactionLink';
import { getScreenClockDisplayParts } from '../utils/screenClock';
import {
  isScreenClockItem,
  isScreenDecorationItem,
  isScreenShapeItem,
  isScreenTextItem,
  isScreenTitleFrameItem,
} from '../utils/screenItems';
import { screenShapeCss } from '../utils/screenShape';
import {
  DecorationSkin,
  TitleFrameSkin,
  screenChromeTextStyle,
  screenUniformTextProps,
} from './screenChromeSkins';

const ClockSkin: React.FC<{
  format?: ScreenClockItem['format'];
  textStyle?: ScreenTextStyleConfig;
}> = ({ format, textStyle }) => {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const parts = getScreenClockDisplayParts(now, format);
  const style = screenChromeTextStyle(textStyle, {
    fontSize: 20,
    fontWeight: 600,
    color: 'canvas',
  });
  const partClassName =
    'mr-2 leading-none tabular-nums tracking-[0.08em] last:mr-0';

  return (
    <div
      {...screenUniformTextProps(
        textStyle,
        undefined,
        'flex h-full w-full flex-wrap items-center',
      )}
      data-screen-clock
      style={{
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        color: style.color,
      }}
    >
      {parts.date ? <span className={partClassName}>{parts.date}</span> : null}
      {parts.week ? (
        <span className={`whitespace-nowrap ${partClassName}`}>{parts.week}</span>
      ) : null}
      <span className={partClassName}>{parts.primary}</span>
    </div>
  );
};

const ScreenTextBody: React.FC<{ item: ScreenTextItem }> = ({ item }) => {
  const textContent = useFilterTemplateText(item.content);
  const surface = useInteractionSurface();
  const titleConfig = item.interaction?.kind === 'title'
    ? { interaction: item.interaction }
    : undefined;
  const showLink = shouldShowInteractionEntry(
    surface,
    Boolean(readWidgetInteraction(titleConfig)),
  );
  if (!showLink) {
    return (
      <div
        {...screenUniformTextProps(
          item.textStyle,
          undefined,
          'h-full w-full px-1 py-1',
        )}
        style={screenChromeTextStyle(item.textStyle)}
      >
        {textContent}
      </div>
    );
  }

  const align = item.textStyle?.align ?? 'left';
  const multiline = textContent.includes('\n');
  return (
    <div
      {...screenUniformTextProps(
        item.textStyle,
        undefined,
        'flex h-full w-full min-w-0 flex-nowrap items-center justify-start overflow-hidden px-1 py-1',
      )}
      data-screen-text-link=""
      style={{
        ...screenChromeTextStyle(item.textStyle),
        gap: '0.4em',
      }}
    >
      <span
        data-screen-text-label=""
        className="min-w-0 overflow-hidden"
        style={{
          flex: '1 1 auto',
          textAlign: align,
          whiteSpace: multiline ? 'pre-wrap' : 'nowrap',
          wordBreak: multiline ? 'break-word' : 'normal',
          textOverflow: multiline ? 'clip' : 'ellipsis',
        }}
      >
        {textContent}
      </span>
      <InteractionTitleIcon config={titleConfig} variant="text" />
    </div>
  );
};

interface ScreenChromeRendererProps {
  item: ScreenItem;
}

const ScreenChromeRenderer: React.FC<ScreenChromeRendererProps> = ({
  item,
}) => {
  let body: React.ReactNode = null;
  if (isScreenTextItem(item)) {
    body = <ScreenTextBody item={item} />;
  } else if (isScreenClockItem(item)) {
    body = <ClockSkin format={item.format} textStyle={item.textStyle} />;
  } else if (isScreenTitleFrameItem(item)) {
    body = <TitleFrameSkin item={item} />;
  } else if (isScreenDecorationItem(item)) {
    body = <DecorationSkin item={item} />;
  } else if (isScreenShapeItem(item)) {
    body = <div style={screenShapeCss(item.shape, item.shapeStyle)} />;
  }

  return <div className="relative h-full w-full">{body}</div>;
};

export default ScreenChromeRenderer;
