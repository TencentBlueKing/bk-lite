'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactAce from 'react-ace';
import { Button, Tooltip, message } from 'antd';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/theme-monokai';
import {
  CopyOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface EditorToolbarOptions {
  copy?: boolean;
  fullscreen?: boolean;
}

interface CodeEditorProps {
  value?: string;
  className?: string;
  headerOptions?: EditorToolbarOptions;
  [key: string]: unknown;
}

const CodeEditor: React.FC<CodeEditorProps> = ({
  value = '',
  headerOptions,
  className = '',
  ...restProps
}) => {
  const { t } = useTranslation();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const enableCopy = headerOptions?.copy ?? false;
  const enableFullscreen = headerOptions?.fullscreen ?? false;
  const shouldShowHeader = enableCopy || enableFullscreen;

  // 动态配置 message 的挂载容器
  useEffect(() => {
    // 切换全屏状态时，先销毁所有现有的 message
    message.destroy();

    if (isFullscreen && containerRef.current) {
      message.config({
        getContainer: () => containerRef.current!
      });
    } else {
      // 恢复默认挂载到 document.body
      message.config({
        getContainer: () => document.body
      });
    }
  }, [isFullscreen]);

  // 组件卸载时恢复默认配置
  useEffect(() => {
    return () => {
      message.config({
        getContainer: () => document.body
      });
    };
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = value;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      message.success(t('common.copySuccess'));
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      message.error(errorMsg);
    }
  }, [value, t]);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;

    if (!isFullscreen) {
      containerRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={`${className} ${isFullscreen ? 'flex flex-col' : ''}`}
      style={{ position: 'relative' }}
    >
      {shouldShowHeader && (
        <div
          className="flex items-center justify-end px-2 gap-1"
          style={{
            height: 32,
            background: 'linear-gradient(180deg, #2d2d30 0%, #252526 100%)',
            borderBottom: '1px solid #1e1e1e'
          }}
        >
          {enableCopy && (
            <Tooltip
              title={t('common.copy')}
              placement="bottom"
              getPopupContainer={
                isFullscreen ? () => containerRef.current! : undefined
              }
            >
              <Button
                type="text"
                size="small"
                icon={<CopyOutlined style={{ color: 'var(--color-text-3)' }} />}
                onClick={handleCopy}
                className="hover:!bg-[var(--color-bg-hover)]"
              />
            </Tooltip>
          )}
          {enableFullscreen && (
            <Tooltip
              title={
                isFullscreen
                  ? t('common.exitFullscreen')
                  : t('common.fullscreen')
              }
              placement="bottom"
              getPopupContainer={
                isFullscreen ? () => containerRef.current! : undefined
              }
            >
              <Button
                type="text"
                size="small"
                icon={
                  isFullscreen ? (
                    <FullscreenExitOutlined
                      style={{ color: 'var(--color-text-3)' }}
                    />
                  ) : (
                    <FullscreenOutlined
                      style={{ color: 'var(--color-text-3)' }}
                    />
                  )
                }
                onClick={toggleFullscreen}
                className="hover:!bg-[var(--color-bg-hover)]"
              />
            </Tooltip>
          )}
        </div>
      )}
      <ReactAce
        style={{
          marginTop: 0,
          ...(isFullscreen ? { flex: 1, height: '100%', width: '100%' } : {})
        }}
        width={isFullscreen ? '100%' : (restProps.width as string)}
        value={value}
        setOptions={{
          showPrintMargin: false
        }}
        {...restProps}
      />
    </div>
  );
};

export default CodeEditor;
