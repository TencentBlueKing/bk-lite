import React, { useCallback, useEffect, useState } from 'react';
import { FullscreenExitOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';

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
      return;
    }

    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverflow = document.documentElement.style.overflow;

    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';

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

export const AppViewFullscreenExit: React.FC<AppViewFullscreenExitProps> = ({
  visible,
  onExit,
  className,
}) => {
  const { t } = useTranslation();

  if (!visible) {
    return null;
  }

  return (
    <div className={className || 'absolute right-4 top-3 z-30'}>
      <Tooltip title={t('common.exitFullscreen')}>
        <Button
          type="default"
          shape="circle"
          aria-label={t('common.exitFullscreen')}
          icon={<FullscreenExitOutlined style={{ fontSize: 16 }} />}
          onClick={onExit}
        />
      </Tooltip>
    </div>
  );
};
