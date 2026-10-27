import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FullscreenExitOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';

export const APP_VIEW_FULLSCREEN_EVENT = 'bk-app-view-fullscreen';
const APP_VIEW_FULLSCREEN_ATTR = 'data-app-view-fullscreen';

export function setAppViewFullscreenActive(active: boolean) {
  if (typeof document === 'undefined') {
    return;
  }
  if (active) {
    document.documentElement.setAttribute(APP_VIEW_FULLSCREEN_ATTR, '');
  } else {
    document.documentElement.removeAttribute(APP_VIEW_FULLSCREEN_ATTR);
  }
  window.dispatchEvent(new Event(APP_VIEW_FULLSCREEN_EVENT));
}

export function isAppViewFullscreenActive() {
  return (
    typeof document !== 'undefined' &&
    document.documentElement.hasAttribute(APP_VIEW_FULLSCREEN_ATTR)
  );
}

export const useAppViewFullscreen = () => {
  const [isFullscreen, setIsFullscreen] = useState(false);

  const enterFullscreen = useCallback(() => {
    setIsFullscreen(true);
  }, []);

  const exitFullscreen = useCallback(() => {
    setIsFullscreen(false);
  }, []);

  useEffect(() => {
    if (!isFullscreen) {
      setAppViewFullscreenActive(false);
      return;
    }

    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverflow = document.documentElement.style.overflow;

    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    setAppViewFullscreenActive(true);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setIsFullscreen(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousHtmlOverflow;
      document.removeEventListener('keydown', handleKeyDown);
      setAppViewFullscreenActive(false);
    };
  }, [isFullscreen]);

  return {
    isFullscreen,
    enterFullscreen,
    exitFullscreen,
  };
};

export interface AppViewFullscreenExitProps {
  visible: boolean;
  onExit: () => void;
  className?: string;
}

const ESC_TIP_VISIBLE_MS = 3000;
// 大屏拖拽控件会临时升到 z-index 10000，退出层要留在画布之上。
const FULLSCREEN_CHROME_LAYER = 'z-[10050]';

export const AppViewFullscreenExit: React.FC<AppViewFullscreenExitProps> = ({
  visible,
  onExit,
  className,
}) => {
  const { t } = useTranslation();
  const hotZoneRef = useRef<HTMLDivElement>(null);
  const [tipVisible, setTipVisible] = useState(false);
  const [cornerHovered, setCornerHovered] = useState(false);

  useEffect(() => {
    if (!visible) {
      setTipVisible(false);
      setCornerHovered(false);
      return;
    }

    setTipVisible(true);
    const timer = window.setTimeout(() => {
      setTipVisible(false);
    }, ESC_TIP_VISIBLE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [visible]);

  if (!visible) {
    return null;
  }

  return (
    <>
      {tipVisible ? (
        <div
          role="status"
          data-testid="app-view-fullscreen-esc-tip"
          className={`pointer-events-none absolute left-1/2 top-4 ${FULLSCREEN_CHROME_LAYER} -translate-x-1/2 rounded-full border border-[var(--color-border-2)] bg-[var(--color-bg-1)]/90 px-4 py-1.5 text-sm leading-5 text-[var(--color-text-1)] shadow-md`}
        >
          {t('common.pressEscToExitFullscreen')}
        </div>
      ) : null}
      <div
        ref={hotZoneRef}
        data-testid="app-view-fullscreen-exit-hotzone"
        className={className || `absolute right-0 top-0 ${FULLSCREEN_CHROME_LAYER} h-20 w-20`}
        onMouseEnter={() => setCornerHovered(true)}
        onMouseLeave={() => setCornerHovered(false)}
      >
        <div
          data-testid="app-view-fullscreen-exit-button"
          data-shown={cornerHovered ? 'true' : 'false'}
          className={`absolute right-4 top-3 transition-opacity duration-150 ${
            cornerHovered ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        >
          <Tooltip
            title={t('common.exitFullscreen')}
            placement="bottomRight"
            getPopupContainer={() => hotZoneRef.current ?? document.body}
          >
            <Button
              type="default"
              shape="circle"
              aria-label={t('common.exitFullscreen')}
              aria-hidden={cornerHovered ? undefined : true}
              tabIndex={cornerHovered ? 0 : -1}
              icon={<FullscreenExitOutlined style={{ fontSize: 16 }} />}
              onClick={onExit}
            />
          </Tooltip>
        </div>
      </div>
    </>
  );
};
