import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type {
  CollectToolExecuteRequest,
  CollectToolPrefillResponse,
  CollectToolSubmitResponse,
  CollectToolResultResponse,
} from '@/app/cmdb/types/collectTool';

export const useCollectToolApi = () => {
  const { get, post } = useApiClient();

  /**
   * 提交一次协议诊断任务（SNMP 或 IPMI），立即返回 debug_id。
   */
  const executeCollectTool = useCallback(
    (payload: CollectToolExecuteRequest) =>
      post<CollectToolSubmitResponse>('/cmdb/api/collect_tool/execute/', payload),
    [post]
  );

  const getCollectToolResult = useCallback(
    (debugId: string) =>
      get<CollectToolResultResponse>('/cmdb/api/collect_tool/result/', {
        params: { debug_id: debugId },
      }),
    [get]
  );

  /**
   * 根据失败任务 ID 获取预填上下文。
   */
  const getCollectToolPrefill = useCallback(
    (taskId: number, protocol: string) =>
      get<CollectToolPrefillResponse>('/cmdb/api/collect_tool/prefill/', {
        params: { task_id: taskId, protocol },
      }),
    [get]
  );

  return { executeCollectTool, getCollectToolResult, getCollectToolPrefill };
};
