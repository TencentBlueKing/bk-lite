'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactAce from 'react-ace';
import { Button, Tooltip, message } from 'antd';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-powershell';
import 'ace-builds/src-noconflict/mode-sh';
import 'ace-builds/src-noconflict/mode-toml';
import 'ace-builds/src-noconflict/theme-monokai';
import 'ace-builds/src-noconflict/theme-textmate';
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
  onChange?: (value: string) => void;
  className?: string;
  headerOptions?: EditorToolbarOptions;
  /** token：工具栏与编辑区走 bk-lite 语义色，避免灰白冲淡。 */
  appearance?: 'default' | 'token';
  [key: string]: unknown;
}

const CodeEditor: React.FC<CodeEditorProps> = ({
  value,
  onChange,
  headerOptions,
  className = '',
  appearance = 'default',
  ...restProps
}) => {
  const { t } = useTranslation();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const lastValueRef = useRef(typeof value === 'string' ? value : '');
  if (typeof value === 'string') {
    lastValueRef.current = value;
  }
  const editorValue = typeof value === 'string' ? value : lastValueRef.current;

  const enableCopy = headerOptions?.copy ?? false;
  const enableFullscreen = headerOptions?.fullscreen ?? false;
  const shouldShowHeader = enableCopy || enableFullscreen;
  const tokenSurface = appearance === 'token';
  const iconColor = tokenSurface ? 'var(--color-text-2)' : 'var(--color-text-3)';

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

  const handleChange = useCallback(
    (next: string) => {
      lastValueRef.current = next;
      if (typeof onChange === 'function') {
        onChange(next);
      }
    },
    [onChange]
  );

  const handleCopy = useCallback(async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(editorValue);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = editorValue;
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
  }, [editorValue, t]);

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
      className={`${tokenSurface ? 'code-editor-token' : ''} ${className} ${isFullscreen ? 'flex flex-col' : ''}`}
      style={{ position: 'relative' }}
    >
      {shouldShowHeader && (
        <div
          className={
            tokenSurface
              ? 'flex h-8 items-center justify-end gap-1 border-b border-[var(--color-border-3)] bg-[var(--color-fill-3)] px-2'
              : 'flex items-center justify-end gap-1 px-2'
          }
          style={
            tokenSurface
              ? undefined
              : {
                height: 32,
                background: 'linear-gradient(180deg, #2d2d30 0%, #252526 100%)',
                borderBottom: '1px solid #1e1e1e'
              }
          }
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
                icon={<CopyOutlined style={{ color: iconColor }} />}
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
                    <FullscreenExitOutlined style={{ color: iconColor }} />
                  ) : (
                    <FullscreenOutlined style={{ color: iconColor }} />
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
        setOptions={{
          showPrintMargin: false
        }}
        {...restProps}
        width={isFullscreen ? '100%' : (restProps.width as string)}
        value={editorValue}
        onChange={handleChange}
      />
    </div>
  );
};

export default CodeEditor;
