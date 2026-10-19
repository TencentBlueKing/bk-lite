import { application3DHoverSupportsLinkMenu } from '@/app/ops-analysis/utils/interactionLinkHint';
import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

export interface Application3DLinkHoverState {
  id: string;
  name: string;
  kind: string;
  x: number;
  y: number;
}

/** contextHint 仅在查看态且存在数据链接时非空。 */
export const shouldShowApplication3DLinkHover = (
  hint: string | undefined,
  kind: string | undefined,
  menuOpen: boolean,
) => Boolean(hint?.trim()) && !menuOpen && application3DHoverSupportsLinkMenu(kind);

/** 浮层画在组件内部，用和大屏机房浮层相同的可读缩放抵消 fitScale。 */
export const application3DHoverReadableScale = (
  screen: Pick<
    ScreenRenderContext,
    'enabled' | 'fitScale' | 'widgetUiScale' | 'screenUiScale'
  > | undefined,
) => {
  if (!screen?.enabled) return 1;
  const fitScale = Number.isFinite(screen.fitScale) && screen.fitScale > 0
    ? screen.fitScale
    : 1;
  const uiScale = screen.widgetUiScale || screen.screenUiScale || 1;
  return Math.max(uiScale, 1 / fitScale, 1);
};

export const placeSceneHoverPopup = ({
  clientX,
  clientY,
  anchorLeft,
  anchorTop,
  anchorWidth,
  anchorHeight,
  offsetWidth,
  offsetHeight,
  popupWidth,
  popupHeight,
  readableScale = 1,
}: {
  clientX: number;
  clientY: number;
  anchorLeft: number;
  anchorTop: number;
  anchorWidth: number;
  anchorHeight: number;
  offsetWidth: number;
  offsetHeight: number;
  popupWidth: number;
  popupHeight: number;
  readableScale?: number;
}) => {
  const offset = 6 * readableScale;
  const margin = 8 * readableScale;
  const width = popupWidth || 160 * readableScale;
  const height = popupHeight || 52 * readableScale;
  const scaleX = anchorWidth ? offsetWidth / anchorWidth : 1;
  const scaleY = anchorHeight ? offsetHeight / anchorHeight : 1;
  const localX = (clientX - anchorLeft) * scaleX;
  const localY = (clientY - anchorTop) * scaleY;
  const roomWidth = offsetWidth || anchorWidth;
  const roomHeight = offsetHeight || anchorHeight;
  const minLeft = margin;
  const maxLeft = Math.max(minLeft, roomWidth - width - margin);
  const minTop = margin;
  const maxTop = Math.max(minTop, roomHeight - height - margin);
  const preferredLeft = localX + offset;
  const flippedLeft = localX - width - offset;
  const preferredTop = localY + offset;
  return {
    left: Math.min(
      Math.max(
        preferredLeft + width > roomWidth - margin ? flippedLeft : preferredLeft,
        minLeft,
      ),
      maxLeft,
    ),
    top: Math.min(Math.max(preferredTop, minTop), maxTop),
  };
};
