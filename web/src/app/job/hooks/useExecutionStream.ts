'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * 单个目标的实时输出累积结果。
 * key 为后端 target_key（node_id 或 target_id 字符串）。
 */
export interface TargetLiveOutput {
  stdout: string;
  stderr: string;
  status?: string;
  done: boolean;
}

export type LiveOutputMap = Record<string, TargetLiveOutput>;

interface StreamEventPayload {
  execution_id?: string;
  target_key?: string;
  stream?: 'stdout' | 'stderr';
  line?: string;
  type?: string; // 'done' | 'error' | 'history' | undefined(实时行)
  status?: string;
  message?: string;
}

interface UseExecutionStreamArgs {
  executionId: number | null;
  enabled: boolean;
  token: string | null;
  /** 所有目标都收到 done（或流自然结束）时回调，用于拉取权威最终结果。 */
  onAllDone?: () => void;
}

// 单个目标输出上限，防止超长脚本把内存撑爆（保留尾部）。
const MAX_CHARS_PER_TARGET = 500_000;

function appendCapped(prev: string, chunk: string): string {
  const next = prev + chunk;
  if (next.length <= MAX_CHARS_PER_TARGET) return next;
  return next.slice(next.length - MAX_CHARS_PER_TARGET);
}

/**
 * 订阅作业执行的 SSE 流式输出。
 *
 * - enabled 为真且有 executionId 时建立 fetch 流连接到
 *   `/api/proxy/job_mgmt/api/execution/{id}/stream/`，按行累积到 liveOutput。
 * - 后端事件：实时行 {target_key, stream, line}；历史回放 {type:'history',...}；
 *   结束哨兵 {type:'done', target_key, status}；流尾 `data: [DONE]`。
 * - 组件卸载/禁用/切换 executionId 时中断并清理。
 */
export function useExecutionStream({
  executionId,
  enabled,
  token,
  onAllDone,
}: UseExecutionStreamArgs) {
  const [liveOutput, setLiveOutput] = useState<LiveOutputMap>({});
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const onAllDoneRef = useRef(onAllDone);
  onAllDoneRef.current = onAllDone;

  const applyEvent = useCallback((payload: StreamEventPayload) => {
    const targetKey = payload.target_key;
    if (!targetKey) return;
    setLiveOutput((prev) => {
      const cur: TargetLiveOutput = prev[targetKey] || { stdout: '', stderr: '', done: false };
      const next: TargetLiveOutput = { ...cur };
      if (payload.type === 'done') {
        next.done = true;
        if (payload.status) next.status = payload.status;
      } else if (payload.line != null) {
        const chunk = payload.line + '\n';
        if (payload.stream === 'stderr') {
          next.stderr = appendCapped(cur.stderr, chunk);
        } else {
          next.stdout = appendCapped(cur.stdout, chunk);
        }
      }
      return { ...prev, [targetKey]: next };
    });
  }, []);

  useEffect(() => {
    if (!enabled || !executionId || !token) {
      return;
    }

    const abortController = new AbortController();
    abortRef.current = abortController;
    let cancelled = false;

    const run = async () => {
      setStreaming(true);
      console.log(`[exec-stream] 连接 SSE: execution_id=${executionId}`);
      try {
        const response = await fetch(
          `/api/proxy/job_mgmt/api/execution/${executionId}/stream/`,
          {
            method: 'GET',
            headers: { Authorization: `Bearer ${token}` },
            signal: abortController.signal,
          }
        );
        if (!response.ok || !response.body) {
          console.warn(`[exec-stream] 连接失败: status=${response.status}`);
          return;
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let done = false;
        while (!abortController.signal.aborted && !done) {
          const { done: streamDone, value } = await reader.read();
          if (streamDone) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE 事件以空行分隔
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() ?? '';
          for (const block of blocks) {
            const dataLine = block
              .split('\n')
              .find((l) => l.startsWith('data:'));
            if (!dataLine) continue;
            const payloadStr = dataLine.slice('data:'.length).trim();
            if (!payloadStr) continue;
            if (payloadStr === '[DONE]') {
              done = true;
              console.log(`[exec-stream] 收到 [DONE]，关闭: execution_id=${executionId}`);
              break;
            }
            try {
              applyEvent(JSON.parse(payloadStr) as StreamEventPayload);
            } catch {
              // 非 JSON 行忽略
            }
          }
        }
        if (!cancelled) {
          onAllDoneRef.current?.();
        }
      } catch (err) {
        // AbortError 属正常断开（卸载/切换），其它错误打印便于排查
        if ((err as Error)?.name !== 'AbortError') {
          console.warn(`[exec-stream] 流异常: execution_id=${executionId}`, err);
        }
      } finally {
        if (!cancelled) {
          setStreaming(false);
        }
      }
    };

    run();

    return () => {
      cancelled = true;
      abortController.abort();
      abortRef.current = null;
      setStreaming(false);
    };
  }, [executionId, enabled, token, applyEvent]);

  // 切换执行记录时清空累积，避免串台
  useEffect(() => {
    setLiveOutput({});
  }, [executionId]);

  return { liveOutput, streaming };
}
