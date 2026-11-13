import { toCanvasPixels } from '@/app/ops-analysis/components/widget-viewport';

const LINE_HEIGHT = 1.25;

export interface WidgetStateFit {
  showIcon: boolean;
  fontSize: number;
  lineClamp: number;
  iconSize: number;
  iconGap: number;
  padding: number;
  showTitle: boolean;
}

/**
 * 所有图表错误提示共用：正常字号是上限。
 * 组件放不下图标和两行字时去掉警告图标，字号再随剩余区域缩小。
 */
export const fitWidgetStateContent = ({
  width,
  height,
  scale,
  textLength,
}: {
  width: number;
  height: number;
  scale: number;
  textLength: number;
}): WidgetStateFit => {
  const padding = Math.min(8, Math.max(2, Math.round(Math.min(width, height) * 0.06)));
  const innerW = Math.max(0, width - padding * 2);
  const innerH = Math.max(0, height - padding * 2);
  const preferred = toCanvasPixels(13, scale);
  const iconSize = toCanvasPixels(22, scale);
  const iconGap = toCanvasPixels(6, scale);
  const showIcon = innerW >= preferred * 8
    && innerH >= iconSize + iconGap + preferred * LINE_HEIGHT * 2;
  const textH = Math.max(0, innerH - (showIcon ? iconSize + iconGap : 0));
  const fontSize = Math.max(1, Math.min(
    preferred,
    innerW / 8,
    textH / LINE_HEIGHT || preferred,
  ));
  const lineClamp = Math.max(1, Math.floor(textH / (fontSize * LINE_HEIGHT)) || 1);
  const charsPerLine = Math.max(1, Math.floor(innerW / fontSize));
  const neededLines = textLength > 0 ? Math.ceil(textLength / charsPerLine) : 1;

  return {
    showIcon,
    fontSize,
    lineClamp,
    iconSize,
    iconGap,
    padding,
    showTitle: textLength > 0 && neededLines > lineClamp,
  };
};
