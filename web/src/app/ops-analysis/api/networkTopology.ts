import { useCallback, useMemo } from 'react';
import useApiClient from '@/utils/request';
import type {
  NetworkTopologyConfig,
  NetworkTopologyDetail,
  NetworkTopologyRuntime,
  NetworkNodeLibraryItem,
  NetworkNodeModel,
  NetworkMetricRuntime,
} from '@/app/ops-analysis/types/networkTopology';

/**
 * 网络拓扑画布 API client。
 *
 * 实际后端路由(由 Worker A 实现,见 `server/apps/operation_analysis/views/network_topology_view.py`):
 * - 标准 canvas CRUD: `POST /network_topology/`, `GET/PUT/PATCH/DELETE /network_topology/<id>/`
 * - `POST /network_topology/test_connection/` —— 试探 base_url + token,不落库
 * - `GET /network_topology/<id>/runtime/` —— 节点 + 连线运行态(后端实时拉 WeOps;前端保留上次内存态兜底)
 * - `GET /network_topology/<id>/config` / `PUT /network_topology/<id>/config` —— view_sets JSON 读写
 * - WeOps 代理:
 *   - `GET /network_topology/<id>/weops/node_models/`
 *   - `GET /network_topology/<id>/weops/nodes/?all=true&bk_obj_id=&keyword=`
 *   - `GET /network_topology/<id>/weops/nodes/<encoded_node_ref>/interfaces/`
 *   - `GET /network_topology/<id>/weops/nodes/<encoded_node_ref>/metrics/`
 *   - `POST /network_topology/<id>/weops/dimension_values/`
 *
 * 设计要点(design.md §5、§6):
 * - 后端不返回明文 token,改返回 `token_set: boolean`
 * - 新建画布必传 `base_url` + `token`
 * - 更新画布时 `token` 字段为空或 `******` → 前端不发送,后端保持原值
 * - 传 `all=true` 一次性拉全部节点
 *
 * 注意:项目内 `config.drf.renderers.CustomRenderer` 会把任何返回再包成
 * `{result, data}` 形式。本模块返回的是已经解析过的 payload,
 * 由调用侧的 `request.ts` 拦截器统一拆包。
 */

export interface NetworkTopologySavePayload {
  base_url: string;
  /** 编辑模式下若 token 未填写则不传,后端保留原值。 */
  token?: string;
  view_sets?: NetworkTopologyConfig;
  refresh_interval?: number;
  desc?: string;
  name?: string;
  groups?: number[];
}

export interface NetworkTopologyCreatePayload extends NetworkTopologySavePayload {
  name: string;
  groups: number[];
}

export interface NetworkTopologyTestConnectionPayload {
  base_url: string;
  token?: string;
}

export interface NetworkTopologyTestConnectionResult {
  status: 'ok';
}

const encodeNodeRef = (nodeRef: Record<string, unknown>): string =>
  encodeURIComponent(JSON.stringify(nodeRef));

export const useNetworkTopologyApi = () => {
  const { get, post, put, del } = useApiClient();

  const getNetworkTopologyDetail = useCallback(
    (id: string | number) =>
      get<NetworkTopologyDetail>(`/operation_analysis/api/network_topology/${id}/`),
    [get],
  );

  const createNetworkTopology = useCallback(
    (payload: NetworkTopologyCreatePayload) =>
      post<NetworkTopologyDetail>(
        '/operation_analysis/api/network_topology/',
        payload,
      ),
    [post],
  );

  const updateNetworkTopology = useCallback(
    (id: string | number, payload: NetworkTopologySavePayload) =>
      put<NetworkTopologyDetail>(
        `/operation_analysis/api/network_topology/${id}/`,
        payload,
      ),
    [put],
  );

  const deleteNetworkTopology = useCallback(
    (id: string | number) =>
      del(`/operation_analysis/api/network_topology/${id}/`),
    [del],
  );

  /** 读取画布 view_sets JSON(后端实际为 `/config`)。 */
  const getViewSets = useCallback(
    (id: string | number) =>
      get<NetworkTopologyConfig>(
        `/operation_analysis/api/network_topology/${id}/config/`,
      ),
    [get],
  );

  /** 全量替换画布 view_sets JSON(后端实际为 `PUT /config`)。 */
  const saveViewSets = useCallback(
    (id: string | number, view_sets: NetworkTopologyConfig) =>
      put<NetworkTopologyConfig>(
        `/operation_analysis/api/network_topology/${id}/config/`,
        view_sets,
      ),
    [put],
  );

  const getRuntime = useCallback(
    (id: string | number) =>
      get<NetworkTopologyRuntime>(
        `/operation_analysis/api/network_topology/${id}/runtime/`,
      ),
    [get],
  );

  /** 验证 WeOps 连接(form 临时传 token,后端不落库)。 */
  const testConnection = useCallback(
    (payload: NetworkTopologyTestConnectionPayload) =>
      post<NetworkTopologyTestConnectionResult>(
        '/operation_analysis/api/network_topology/test_connection/',
        payload,
      ),
    [post],
  );

  /** 验证已保存画布的 WeOps 连接；编辑态可复用已保存 token。 */
  const testSavedConnection = useCallback(
    (canvasId: string | number, payload: Partial<NetworkTopologyTestConnectionPayload>) =>
      post<NetworkTopologyTestConnectionResult>(
        `/operation_analysis/api/network_topology/${canvasId}/test_connection/`,
        payload,
      ),
    [post],
  );

  /** 节点模型(后端转发到 WeOps `/node_models/`)。 */
  const getNodeModels = useCallback(
    (canvasId: string | number) =>
      get<NetworkNodeModel[]>(
        `/operation_analysis/api/network_topology/${canvasId}/weops/node_models/`,
      ),
    [get],
  );

  /** 节点库(后端转发 all=true,一次拉全部)。 */
  const getNodes = useCallback(
    (
      canvasId: string | number,
      params?: { bk_obj_id?: string; keyword?: string },
    ) =>
      get<{ count: number; results: NetworkNodeLibraryItem[] }>(
        `/operation_analysis/api/network_topology/${canvasId}/weops/nodes/`,
        {
          params: { all: true, ...(params || {}) },
        },
      ),
    [get],
  );

  /** 节点接口列表 —— 后端编码 node_ref 后放在 URL 段。 */
  const getNodeInterfaces = useCallback(
    (canvasId: string | number, nodeRef: Record<string, unknown>) =>
      get<{
        items?: Array<{
          interface_key: string;
          bk_obj_id: 'bk_interface';
          bk_inst_id: number;
          interface_name: string;
          admin_status: 'up' | 'down' | 'testing' | 'unknown';
          oper_status: 'up' | 'down' | 'testing' | 'unknown';
          metrics?: Record<string, { value: number | string | null; unit: string }>;
          status?: string;
          error_code?: string;
        }>;
        summary?: { total: number; up: number; down: number; unknown: number };
        status?: string;
        error_code?: string;
        error_message?: string;
      }>(
        `/operation_analysis/api/network_topology/${canvasId}/weops/nodes/${encodeNodeRef(nodeRef)}/interfaces/`,
      ),
    [get],
  );

  /** 节点指标 —— 后端编码 node_ref 后放在 URL 段。 */
  const getNodeMetrics = useCallback(
    (canvasId: string | number, nodeRef: Record<string, unknown>) =>
      get<{
        items?: Array<{
          metric_field: string;
          field_name: string;
          field_cn_name?: string;
          result_table_id: string;
          unit?: string;
          display_name?: string;
          supported_dimensions?: string[];
        }>;
        status?: string;
      }>(
        `/operation_analysis/api/network_topology/${canvasId}/weops/nodes/${encodeNodeRef(nodeRef)}/metrics/`,
      ),
    [get],
  );

  /** 维度值。 */
  const getDimensionValues = useCallback(
    (
      canvasId: string | number,
      payload: {
        node_ref: Record<string, unknown>;
        metric_ref: { metric_field: string; result_table_id: string };
        dimension_keys: string[];
      },
    ) =>
      post<{
        items?: Array<{
          dimension: string;
          list: Array<{ label: string; value: string }>;
        }>;
        status?: string;
      }>(
        `/operation_analysis/api/network_topology/${canvasId}/weops/dimension_values/`,
        payload,
      ),
    [post],
  );

  const getMetricValues = useCallback(
    (
      canvasId: string | number,
      items: Array<{
        request_id: string;
        node_ref: Record<string, unknown>;
        metric_ref: { metric_field: string; result_table_id: string };
        dimensions?: Record<string, string>;
        condition_filter?: Array<{ dimension_id: string; value: string[] }>;
        display_mode?: "aggregate" | "dimension";
        aggregate_type?: "sum" | "max" | "min" | "mean" | "last";
      }>,
    ) =>
      post<{ items?: NetworkMetricRuntime[] }>(
        `/operation_analysis/api/network_topology/${canvasId}/weops/metric_values/`,
        { items },
      ),
    [post],
  );

  return useMemo(
    () => ({
      // 画布 CRUD
      getNetworkTopologyDetail,
      createNetworkTopology,
      updateNetworkTopology,
      deleteNetworkTopology,
      // view_sets 读写
      getViewSets,
      saveViewSets,
      // 运行态
      getRuntime,
      // 连接测试
      testConnection,
      testSavedConnection,
      // WeOps 节点库
      getNodeModels,
      getNodes,
      getNodeInterfaces,
      getNodeMetrics,
      getDimensionValues,
      getMetricValues,
    }),
    [
      getNetworkTopologyDetail,
      createNetworkTopology,
      updateNetworkTopology,
      deleteNetworkTopology,
      getViewSets,
      saveViewSets,
      getRuntime,
      testConnection,
      testSavedConnection,
      getNodeModels,
      getNodes,
      getNodeInterfaces,
      getNodeMetrics,
      getDimensionValues,
      getMetricValues,
    ],
  );
};

/**
 * 规范化 base_url:去除首尾空白 + 尾部斜杠。
 * 设计要求(operational.md 中关于 base_url 清理):
 * - 必须以 http:// 或 https:// 开头
 * - 去掉尾部 /
 * - 失败时返回原值,让上层 antd Form 规则抛错
 */
export const cleanBaseUrl = (input?: string | null): string => {
  if (typeof input !== 'string') return '';
  const trimmed = input.trim();
  return trimmed.replace(/\/+$/, '');
};

/** 用于侧边栏新建/编辑表单的 token 行为判定(design.md §6.1 + 命名空间模式):
 * - 编辑模式下,若 token 为空或 `******` 则不发送
 * - 新建模式下 token 必须有值
 */
export const shouldSendTokenOnUpdate = (
  currentRow: unknown,
  token: unknown,
): boolean => {
  if (!currentRow) return true; // 新建总是发送
  if (typeof token !== 'string') return false;
  const trimmed = token.trim();
  if (!trimmed) return false;
  if (token === '******') return false;
  return true;
};
