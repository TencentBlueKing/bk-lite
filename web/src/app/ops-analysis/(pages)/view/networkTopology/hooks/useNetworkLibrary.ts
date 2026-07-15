import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  NetworkNodeLibraryItem,
  NetworkNodeModel,
} from '@/app/ops-analysis/types/networkTopology';
import { useTranslation } from '@/utils/i18n';

/**
 * 网络拓扑设备库 hook(不分页,design.md §3.2 / §7.3):
 * - 一次性拉全部已监控网络设备(后端强制 all=true)
 * - 支持按模型 / 关键字筛选
 * - 多源/单源设备的本地判别
 */

export interface UseNetworkLibraryParams {
  canvasId: string | number | undefined;
  loadModels: (canvasId: string | number) => Promise<NetworkNodeModel[]>;
  loadNodes: (
    canvasId: string | number,
    params?: { bk_obj_id?: string; keyword?: string },
  ) => Promise<{ count: number; results: NetworkNodeLibraryItem[] }>;
}

export interface UseNetworkLibraryReturn {
  models: NetworkNodeModel[];
  nodes: NetworkNodeLibraryItem[];
  modelFilter?: string;
  keyword: string;
  loading: boolean;
  error: string | null;
  setModelFilter: (bkObjId: string | undefined) => void;
  setKeyword: (value: string) => void;
  setError: (msg: string | null) => void;
  reload: () => Promise<void>;
  /** 设备是否只有单一有效监控来源(便于自动选择)。 */
  isSingleSource: (item: NetworkNodeLibraryItem) => boolean;
}

export const useNetworkLibrary = ({
  canvasId,
  loadModels,
  loadNodes,
}: UseNetworkLibraryParams): UseNetworkLibraryReturn => {
  const { t } = useTranslation();
  const [models, setModels] = useState<NetworkNodeModel[]>([]);
  const [nodes, setNodes] = useState<NetworkNodeLibraryItem[]>([]);
  const [modelFilter, setModelFilter] = useState<string | undefined>(undefined);
  const [keyword, setKeyword] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadModelsRef = useRef(loadModels);
  const loadNodesRef = useRef(loadNodes);
  const inFlightRef = useRef<{ key: string; promise: Promise<void> } | null>(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    loadModelsRef.current = loadModels;
    loadNodesRef.current = loadNodes;
  }, [loadModels, loadNodes]);

  const fetchAll = useCallback(async () => {
    if (canvasId === undefined || canvasId === null || canvasId === '') {
      requestSeqRef.current += 1;
      inFlightRef.current = null;
      setModels([]);
      setNodes([]);
      setLoading(false);
      return;
    }
    const requestKey = JSON.stringify({
      canvasId,
      modelFilter: modelFilter ?? '',
      keyword: keyword || '',
    });
    if (inFlightRef.current?.key === requestKey) {
      return inFlightRef.current.promise;
    }
    const seq = requestSeqRef.current + 1;
    requestSeqRef.current = seq;
    setLoading(true);
    setError(null);
    const request = {
      key: requestKey,
      promise: Promise.resolve() as Promise<void>,
    };
    const promise = (async () => {
      try {
        const [modelList, nodePage] = await Promise.all([
          loadModelsRef.current(canvasId),
          loadNodesRef.current(canvasId, {
            bk_obj_id: modelFilter,
            keyword: keyword || undefined,
          }),
        ]);
        if (requestSeqRef.current !== seq) return;
        setModels(modelList);
        setNodes(nodePage.results);
      } catch (err) {
        if (requestSeqRef.current !== seq) return;
        setError(
          err instanceof Error
            ? err.message
            : t('opsAnalysis.networkTopology.library.loadFailed'),
        );
        setNodes([]);
      } finally {
        if (requestSeqRef.current === seq) {
          setLoading(false);
        }
        if (inFlightRef.current === request) {
          inFlightRef.current = null;
        }
      }
    })();
    request.promise = promise;
    inFlightRef.current = request;
    return promise;
  }, [canvasId, keyword, modelFilter]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const isSingleSource = useCallback(
    (item: NetworkNodeLibraryItem) =>
      Array.isArray(item.monitor_sources) && item.monitor_sources.length === 1,
    [],
  );

  return useMemo(
    () => ({
      models,
      nodes,
      modelFilter,
      keyword,
      loading,
      error,
      setModelFilter,
      setKeyword,
      setError,
      reload: fetchAll,
      isSingleSource,
    }),
    [models, nodes, modelFilter, keyword, loading, error, fetchAll, isSingleSource],
  );
};
