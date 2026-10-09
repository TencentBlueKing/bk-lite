'use client';

import React, { useEffect, useState } from 'react';
import type {
  ScreenClockItem,
  ScreenItem,
  ScreenTextStyleConfig,
} from '@/app/ops-analysis/types/screen';
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
      className="flex h-full w-full flex-wrap items-center"
      data-screen-clock
      style={{
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        color: style.color,
        textShadow: style.textShadow,
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

interface ScreenChromeRendererProps {
  item: ScreenItem;
}

const ScreenChromeRenderer: React.FC<ScreenChromeRendererProps> = ({
  item,
}) => {
  let body: React.ReactNode = null;
  if (isScreenTextItem(item)) {
    body = (
      <div className="h-full w-full px-1 py-1" style={screenChromeTextStyle(item.textStyle)}>
        {item.content}
      </div>
    );
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
