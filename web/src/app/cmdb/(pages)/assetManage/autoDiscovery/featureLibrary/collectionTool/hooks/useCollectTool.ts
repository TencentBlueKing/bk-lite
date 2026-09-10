import { useState, useRef, useCallback, useEffect } from 'react';
import type {
  ExecStatus,
  CollectToolExecuteResponse,
  CollectToolResultResponse,
  CollectToolSubmitResponse,
  Protocol,
  Action,
} from '@/app/cmdb/types/collectTool';
import { useCollectToolApi } from '@/app/cmdb/api/collectTool';
import { createLatestRequestGuard } from '@/context/latestRequestGuard';
import {
  commitCollectToolFailure,
  commitCollectToolPoll,
  commitCollectToolSubmit,
} from './collectToolRequest';

interface UseCollectToolOptions {
  protocol: Protocol;
}

const resolveErrorMessage = (err: unknown, fallback: string): string => {
  if (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string') {
    return err.message;
  }
  return fallback;
};

export const useCollectTool = ({ protocol }: UseCollectToolOptions) => {
  const { executeCollectTool, getCollectToolResult } = useCollectToolApi();
  const [requestGuard] = useState(createLatestRequestGuard);
  const [execStatus, setExecStatus] = useState<ExecStatus>('idle');
  const [activeAction, setActiveAction] = useState<Action | null>(null);
  const [result, setResult] = useState<CollectToolExecuteResponse | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const activeActionRef = useRef<Action | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startTimer = useCallback(() => {
    setElapsedSeconds(0);
    timerRef.current = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      requestGuard.invalidate();
      stopPolling();
      stopTimer();
    };
  }, [requestGuard, stopPolling, stopTimer]);

  const clearResultState = useCallback(() => {
    activeActionRef.current = null;
    setActiveAction(null);
    setExecStatus('idle');
    setResult(null);
    setElapsedSeconds(0);
  }, []);

  const applyFinalResult = useCallback(
    (response: CollectToolResultResponse['result']) => {
      stopTimer();
      if (!response) {
        setActiveAction(null);
        setExecStatus('error');
        return;
      }
      setResult(response);
      setActiveAction(null);
      setExecStatus(response.success ? 'success' : 'error');
    },
    [stopTimer]
  );

  const pollResult = useCallback(
    async (debugId: string, intervalMs: number, requestId: number) => {
      try {
        const response = await getCollectToolResult(debugId);
        const resultResponse = response as CollectToolResultResponse;
        commitCollectToolPoll(requestGuard, requestId, () => {
          if (resultResponse.status === 'pending' || resultResponse.status === 'running') {
            setExecStatus('running');
            pollingRef.current = setTimeout(() => {
              pollResult(debugId, resultResponse.poll_interval_ms || intervalMs, requestId);
            }, resultResponse.poll_interval_ms || intervalMs);
            return;
          }

          if (resultResponse.status === 'success' || resultResponse.status === 'error') {
            applyFinalResult(resultResponse.result);
            return;
          }

          stopTimer();
          setActiveAction(null);
          setExecStatus('error');
        });
      } catch (err: unknown) {
        commitCollectToolFailure(requestGuard, requestId, () => {
          stopTimer();
          setActiveAction(null);
          setResult({
            request_id: debugId,
            protocol,
            action: activeActionRef.current || 'test_connection',
            executor: 'stargazer',
            success: false,
            stage: 'timeout',
            summary: resolveErrorMessage(err, '轮询结果失败'),
            raw_log: String(err),
            duration_ms: 0,
            meta: { target: '', port: 0 },
          });
          setExecStatus('error');
        });
      }
    },
    [applyFinalResult, getCollectToolResult, protocol, requestGuard, stopTimer]
  );

  const execute = useCallback(
    async (payload: Parameters<typeof executeCollectTool>[0]) => {
      const requestId = requestGuard.begin();
      stopPolling();
      clearResultState();
      activeActionRef.current = payload.action as Action;
      setActiveAction(payload.action as Action);
      setExecStatus('submitting');
      startTimer();

      try {
        const response = (await executeCollectTool(payload)) as CollectToolSubmitResponse;
        let shouldPoll = false;
        commitCollectToolSubmit(requestGuard, requestId, () => {
          if (response.status === 'error' && response.result) {
            applyFinalResult(response.result);
            return;
          }
          setExecStatus('running');
          shouldPoll = true;
        });
        if (shouldPoll) {
          await pollResult(response.debug_id, response.poll_interval_ms || 2000, requestId);
        }
      } catch (err: unknown) {
        commitCollectToolFailure(requestGuard, requestId, () => {
          stopTimer();
          stopPolling();
          const errorResult: CollectToolExecuteResponse = {
            request_id: '',
            protocol,
            action: payload.action as Action,
            executor: 'stargazer',
            success: false,
            stage: 'timeout',
            summary: resolveErrorMessage(err, '请求超时或网络异常'),
            raw_log: String(err),
            duration_ms: 0,
            meta: { target: payload.target, port: payload.port },
          };
          setResult(errorResult);
          activeActionRef.current = null;
          setActiveAction(null);
          setExecStatus('error');
        });
      }
    },
    [applyFinalResult, clearResultState, executeCollectTool, pollResult, protocol, requestGuard, startTimer, stopPolling, stopTimer]
  );

  const pause = useCallback(() => {
    requestGuard.invalidate();
    stopPolling();
    stopTimer();
    activeActionRef.current = null;
    setActiveAction(null);
    setExecStatus((prev) => (prev === 'running' || prev === 'submitting' ? 'idle' : prev));
  }, [requestGuard, stopPolling, stopTimer]);

  const formatTimer = (seconds: number) => {
    const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
    const ss = String(seconds % 60).padStart(2, '0');
    return `${mm}:${ss}`;
  };

  return {
    execStatus,
    activeAction,
    result,
    elapsedSeconds,
    timerDisplay: formatTimer(elapsedSeconds),
    execute,
    pause,
  };
};
