'use client';

import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Dropdown } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { useInteractionMenuScale } from '@/app/ops-analysis/context/interactionMenuScale';
import { useInteractionSurface } from '@/app/ops-analysis/context/interactionSurface';
import { shouldNavigateInteraction } from '@/app/ops-analysis/utils/interactionLink';
import { useTranslation } from '@/utils/i18n';

interface InteractionDataMenuProps {
  open: boolean;
  x: number;
  y: number;
  label: string;
  onSelect: () => void;
  onClose: () => void;
}

const MENU_FONT_PX = 12;
const MENU_LINE_PX = 18;
const MENU_PADDING_Y_PX = 4;
const MENU_PADDING_X_PX = 10;
const MENU_ICON_PX = 12;
const MENU_MIN_WIDTH_PX = 80;
const MENU_RADIUS_PX = 6;

const menuLength = (pixels: number, scale: number) => `calc(${pixels}px * ${scale})`;

/**
 * 数据链接的右键菜单。锚点 portal 到 body，按视口 clientX/Y 定位，
 * 避免大屏 CSS transform 把 fixed 算进缩放层。
 * 基准跟组件卡片一样紧凑（12px 字），再用倍数改字号、行高、内边距和圆角，不用 transform。
 * 弹出层带上当前 ConfigProvider 的 cssVar 类，大屏暗色主题不必留在主题容器内部。
 */
const InteractionDataMenu: React.FC<InteractionDataMenuProps> = ({
  open,
  x,
  y,
  label,
  onSelect,
  onClose,
}) => {
  const { t } = useTranslation();
  const surface = useInteractionSurface();
  const scale = useInteractionMenuScale();
  const canNavigate = shouldNavigateInteraction(surface);
  const disabledHint = t('dashboard.interactionViewModeOnly', '查看模式下可跳转');

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest('.ant-dropdown')) return;
      onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const onScroll = () => onClose();
    document.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [onClose, open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <Dropdown
      open
      autoAdjustOverflow
      getPopupContainer={() => document.body}
      overlayStyle={{ zIndex: 1100 }}
      menu={{
        items: [
          {
            key: 'open-link',
            disabled: !canNavigate,
            // 图标只作装饰。antd 默认把图标名写成 aria-label，会把菜单项读成 “link 链接名”。
            icon: (
              <LinkOutlined
                aria-hidden
                aria-label=""
                style={{ fontSize: menuLength(MENU_ICON_PX, scale) }}
              />
            ),
            label,
            title: canNavigate ? undefined : disabledHint,
            style: {
              fontSize: menuLength(MENU_FONT_PX, scale),
              lineHeight: menuLength(MENU_LINE_PX, scale),
              padding: `${menuLength(MENU_PADDING_Y_PX, scale)} ${menuLength(MENU_PADDING_X_PX, scale)}`,
              borderRadius: menuLength(MENU_RADIUS_PX, scale),
            },
          },
        ],
        style: {
          minWidth: menuLength(MENU_MIN_WIDTH_PX, scale),
          borderRadius: menuLength(MENU_RADIUS_PX, scale),
        },
        onClick: () => {
          if (!canNavigate) return;
          onSelect();
          onClose();
        },
      }}
    >
      <div
        data-interaction-menu-anchor=""
        className="pointer-events-none fixed h-px w-px"
        style={{ left: x, top: y }}
      />
    </Dropdown>,
    document.body,
  );
};

export default InteractionDataMenu;
