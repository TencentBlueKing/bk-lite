'use client';
import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Button, message, Tooltip } from 'antd';
import {
  FullscreenOutlined,
  FullscreenExitOutlined,
  ClearOutlined,
  PauseOutlined,
  CaretRightOutlined,
} from '@ant-design/icons';
import { LogTerminalProps, LogTerminalRef } from '@/app/log/types/search';
import terminalstyles from './index.module.scss';
import { useAuth } from '@/context/auth';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import SearchHighlight from '@/app/log/components/search-highlight';
import { extractHighlightTerms } from '@/app/log/utils/searchHighlight';
import {
  createSseLogStreamState,
  parseSseLogChunk,
} from './sseLogStream';

const MAX_LOGS_COUNT = 1000;

const LogTerminal = forwardRef<LogTerminalRef, LogTerminalProps>(
  ({ query, highlightQuery, className = '', fetchData }, ref) => {
    const { isLoading } = useApiClient();
    const { t } = useTranslation();
    const authContext = useAuth();
    const token = authContext?.token || null;
    const isStreaming = useRef(false);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [logs, setLogs] = useState<string[]>([]);
    const [isPaused, setIsPaused] = useState(false);
    const logContainerRef = useRef<HTMLDivElement>(null);
    const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(
      null
    );
    const containerRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);
    const sseParseStateRef = useRef(createSseLogStreamState());
    const streamGenerationRef = useRef(0);
    const fetchDataRef = useRef(fetchData);
    fetchDataRef.current = fetchData;
    const highlightTerms = useMemo(
      () => extractHighlightTerms(highlightQuery ?? query.query),
      [highlightQuery, query.query]
    );

    // 自动滚动到底部
    const scrollToBottom = useCallback(() => {
      if (logContainerRef.current && !isPaused) {
        logContainerRef.current.scrollTo({
          top: logContainerRef.current.scrollHeight,
          behavior: 'smooth',
        });
      }
    }, [isPaused]);

    // 处理全屏切换
    const toggleFullscreen = useCallback(() => {
      if (!containerRef.current) return;
      if (!isFullscreen) {
        containerRef.current.requestFullscreen?.();
      } else {
        document.exitFullscreen?.();
      }
    }, [isFullscreen]);

    // 停止日志流。abort 必须同步发生，调用方才能在发下一个请求前断开上游。
    const stopLogStream = useCallback(() => {
      streamGenerationRef.current += 1;
      isStreaming.current = false;
      const abortController = abortControllerRef.current;
      abortControllerRef.current = null;
      abortController?.abort();
      const reader = readerRef.current;
      readerRef.current = null;
      if (reader) {
        reader.cancel().catch(() => {
          // 读取已经结束或锁已释放
        });
      }
      fetchDataRef.current?.(false);
    }, []);

    // 清空日志
    const clearLogs = useCallback(() => {
      setLogs([]);
    }, []);

    const appendLogs = useCallback((newLogs: string[]) => {
      setLogs((prevLogs) => {
        const logList = [...prevLogs, ...newLogs];
        return logList.slice(-MAX_LOGS_COUNT);
      });
    }, []);

    const streamIsCurrent = (
      generation: number,
      abortController: AbortController
    ) =>
      generation === streamGenerationRef.current &&
      !abortController.signal.aborted;

    // 开始日志流
    const startLogStream = useCallback(async (preserveLogs = false) => {
      // 先停掉上一条。新的代际在 stop 之后再加，避免把自己作废。
      const previousGeneration = streamGenerationRef.current;
      stopLogStream();
      const generation = previousGeneration + 1;
      setIsPaused(false);
      if (!preserveLogs) {
        setLogs([]);
      }
      if (!token || generation !== streamGenerationRef.current) return;
      const groups = query.log_groups || [];
      const queryParams = new URLSearchParams({
        query: query.query || '*',
        log_groups: groups.join(','),
      });
      if (!groups?.length) {
        message.error(t('log.search.searchError'));
        return;
      }
      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      let streamReader: ReadableStreamDefaultReader<Uint8Array> | null = null;
      try {
        isStreaming.current = true;
        fetchDataRef.current?.(true);
        const response = await fetch(
          `/api/proxy/log/search/tail?${queryParams.toString()}`,
          {
            method: 'GET',
            headers: {
              Accept: 'text/event-stream',
              Authorization: `Bearer ${token}`,
            },
            signal: abortController.signal,
          }
        );
        if (!streamIsCurrent(generation, abortController)) {
          return;
        }
        fetchDataRef.current?.(false);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        if (!response.body) {
          isStreaming.current = false;
          return;
        }
        const reader = response.body.getReader();
        streamReader = reader;
        readerRef.current = reader;
        const decoder = new TextDecoder();
        sseParseStateRef.current = createSseLogStreamState();
        while (streamIsCurrent(generation, abortController)) {
          try {
            const { done, value } = await reader.read();
            if (!streamIsCurrent(generation, abortController)) break;
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const messages = parseSseLogChunk(chunk, sseParseStateRef.current);
            if (messages.length) {
              appendLogs(messages);
            }
          } catch (error: any) {
            if (error?.name !== 'AbortError') {
              console.log(error);
            }
            break;
          }
        }
      } catch (error: any) {
        if (error?.name !== 'AbortError') {
          console.log(error);
        }
        if (generation === streamGenerationRef.current) {
          fetchDataRef.current?.(false);
        }
      } finally {
        if (streamReader && readerRef.current === streamReader) {
          readerRef.current = null;
          streamReader.cancel().catch(() => {
            // 读取已经结束或锁已释放
          });
        }
        if (abortControllerRef.current === abortController) {
          abortControllerRef.current = null;
          isStreaming.current = false;
        }
      }
    }, [query, stopLogStream, t, token, appendLogs]);

    // 暂停会真正关闭实时查询；继续时从当前时刻建立新的 tail 连接。
    const togglePause = useCallback(async () => {
      if (isPaused) {
        await startLogStream(true);
        return;
      }
      setIsPaused(true);
      stopLogStream();
    }, [isPaused, startLogStream, stopLogStream]);

    // 通过 ref 暴露方法
    useImperativeHandle(
      ref,
      () => ({
        startLogStream,
        stopLogStream,
      }),
      [startLogStream, stopLogStream]
    );

    // 自动滚动效果
    useEffect(() => {
      scrollToBottom();
    }, [logs, scrollToBottom]);

    // 组件挂载时自动开始日志流
    useEffect(() => {
      if (!isLoading) {
        startLogStream();
      }
      return () => {
        stopLogStream();
      };
    }, [stopLogStream, isLoading, token]);

    // 监听全屏状态变化
    useEffect(() => {
      const handleFullscreenChange = () => {
        setIsFullscreen(!!document.fullscreenElement);
      };
      document.addEventListener('fullscreenchange', handleFullscreenChange);
      return () => {
        document.removeEventListener(
          'fullscreenchange',
          handleFullscreenChange
        );
      };
    }, []);

    return (
      <div
        ref={containerRef}
        className={`${terminalstyles.logTerminal} ${
          isFullscreen ? terminalstyles.fullscreen : ''
        } ${className}`}
      >
        <div className={terminalstyles.terminalHeader}>
          <div className={terminalstyles.controls}>
            <Tooltip
              autoAdjustOverflow
              getPopupContainer={(trigger) =>
                trigger.parentElement || document.body
              }
              title={
                isPaused
                  ? t('log.search.resumeLogs')
                  : t('log.search.pauseLogs')
              }
            >
              <Button
                size="small"
                aria-label={
                  isPaused
                    ? t('log.search.resumeLogs')
                    : t('log.search.pauseLogs')
                }
                aria-pressed={isPaused}
                icon={isPaused ? <CaretRightOutlined /> : <PauseOutlined />}
                onClick={togglePause}
              />
            </Tooltip>
            <Tooltip
              title={t('log.search.clearLogs')}
              autoAdjustOverflow
              getPopupContainer={(trigger) =>
                trigger.parentElement || document.body
              }
            >
              <Button
                size="small"
                aria-label={t('log.search.clearLogs')}
                icon={<ClearOutlined />}
                onClick={clearLogs}
              />
            </Tooltip>
            <Tooltip
              title={isFullscreen ? t('log.search.exit') : t('log.search.full')}
              autoAdjustOverflow
              getPopupContainer={(trigger) =>
                trigger.parentElement || document.body
              }
            >
              <Button
                size="small"
                aria-label={
                  isFullscreen ? t('log.search.exit') : t('log.search.full')
                }
                icon={
                  isFullscreen ? (
                    <FullscreenExitOutlined />
                  ) : (
                    <FullscreenOutlined />
                  )
                }
                onClick={toggleFullscreen}
              />
            </Tooltip>
          </div>
        </div>
        <div ref={logContainerRef} className={terminalstyles.logContainer}>
          {logs.map((log, index) => (
            <div key={index} className={terminalstyles.logLine}>
              <span className={terminalstyles.lineNumber}>{index + 1}</span>
              <span className={terminalstyles.logContent}>
                <SearchHighlight text={log} terms={highlightTerms} empty="" />
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }
);

LogTerminal.displayName = 'LogTerminal';

export default LogTerminal;
