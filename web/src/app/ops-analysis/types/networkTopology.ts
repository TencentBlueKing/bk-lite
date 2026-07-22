import type { DirItem } from './index';

/**
 * 网络拓扑画布专属类型定义。
 *
 * 数据所有权规则:
 * - BK-Lite: 画布基本信息 + `view_sets` JSON(节点/连线/端口对/指标/阈值) + WeOps 连接配置(`base_url` / `token`)
 * - WeOps:   节点详情、接口、指标、维度、运行时值通过 OpenAPI 实时拉取
 *
 * Token 在前端永远以 `token_set: boolean` 形式持有,绝不回显明文。
 */

export const PASSWORD_PLACEHOLDER = '******';

/** WeOps 单条监控来源(归一化字段名严格按 WeOps OpenAPI)。 */
export interface MonitorSource {
  network_collect_task_id: number;
  network_collect_instance_id: number;
  plugin_group_id: number | null;
  plugin_group_name?: string | null;
  plugin_template_id: number | string;
  plugin_template_name?: string | null;
  is_default?: boolean;
}

/** WeOps 节点库条目(API 字段直传,不重命名)。 */
export interface NetworkNodeLibraryItem {
  bk_obj_id: string;
  bk_inst_id: number;
  bk_inst_name: string;
  ip_addr?: string;
  collect_status?: string;
  monitor_sources: MonitorSource[];
}

/** WeOps 节点模型(P0 限网络设备)。 */
export interface NetworkNodeModel {
  bk_obj_id: string;
  display_name: string;
}

/** 画布持久化的节点(完整 view_sets 项之一)。 */
export interface NetworkTopologyNode {
  id: string;
  bk_obj_id: string;
  bk_inst_id: number;
  bk_inst_name: string;
  ip_addr?: string;
  network_collect_task_id: number;
  network_collect_instance_id: number;
  plugin_group_id?: number | null;
  plugin_group_name?: string | null;
  plugin_template_id: number | string;
  plugin_template_name?: string | null;
  position: { x: number; y: number };
  /** 按用户配置顺序保存,最后位置 = 最深命中 = 最高等级。 */
  metrics: NetworkTopologyMetric[];
}

/** 端口引用(显式配对的 source/target)。 */
export interface NetworkInterfaceRef {
  bk_obj_id: 'bk_interface';
  bk_inst_id: number;
  interface_name: string;
}

/** 一对端口(显式 1:1,见 design.md §2.4)。 */
export interface NetworkPortPair {
  source_interface: NetworkInterfaceRef;
  target_interface: NetworkInterfaceRef;
}

/** X6 连线拐点。 */
export interface NetworkTopologyPoint {
  x: number;
  y: number;
}

/** 画布持久化的连线。 */
export interface NetworkTopologyLink {
  id: string;
  source_node_id: string;
  target_node_id: string;
  /** X6 画布连接桩 ID，仅控制线条吸附位置，不代表真实设备接口。 */
  source_port_id?: string;
  /** X6 画布连接桩 ID，仅控制线条吸附位置，不代表真实设备接口。 */
  target_port_id?: string;
  port_pairs: NetworkPortPair[];
  /** WeOps 旧端口视图字段:用户选择要在链路/接口详情里展示的接口指标。 */
  interface_metrics?: string[];
  /** 用户在画布上拖拽出来的连线拐点,用于保持手工走线。 */
  vertices?: NetworkTopologyPoint[];
  /**
   * 草稿连线 —— 用户拖出端口磁铁后未完成端口配对时为 true。
   * 后端 canvas_config 校验允许草稿连线空 port_pairs，非草稿必须 ≥1。
   * 保存到数据库前应保持 is_draft=true，直到用户在链路 Drawer 里完成配对。
   */
  is_draft?: boolean;
}

export type NetworkMetricDisplayMode = "aggregate" | "dimension";
export type NetworkMetricAggregateType = "sum" | "max" | "min" | "mean" | "last";

/** WeOps conditionFilter: 一个维度字段可选择多个候选值，行与行之间按 AND 过滤。 */
export interface NetworkMetricConditionFilter {
  dimension_id: string;
  value: string[];
}

/** 节点指标(单条 + 用户配置阈值)。 */
export interface NetworkTopologyMetric {
  metric_field: string;
  result_table_id: string;
  display_name: string;
  unit: string;
  /** 展示/计算方式:聚合值或指定维度。 */
  display_mode?: NetworkMetricDisplayMode;
  /** 聚合值模式下使用的聚合函数。 */
  aggregate_type?: NetworkMetricAggregateType;
  /** 维度键值对,可选。 */
  dimensions?: Record<string, string>;
  /** 指定维度过滤条件,对齐 WeOps monitor_collect/get_variable_value 与仪表盘 conditionFilter 语义。 */
  condition_filter?: NetworkMetricConditionFilter[];
  /** 配置顺序(从 0 开始递增),节点颜色平局取第一个指标。 */
  sort_order: number;
  /** 阈值,完全由用户配置:[{value, color}],不预设严重级。 */
  thresholds: NetworkTopologyThreshold[];
  /** 单条指标的运行时错误码,前端按 WeOps §5.5 归类展示。 */
  error_code?: string | null;
}

export interface NetworkTopologyThreshold {
  value: number;
  color: string;
}

/** view_sets JSON 根结构(与其他画布一致)。 */
export interface NetworkTopologyConfig {
  nodes: NetworkTopologyNode[];
  links: NetworkTopologyLink[];
}

/** 接口的运行态摘要项。 */
export interface NetworkInterfaceRuntime {
  request_id?: string;
  endpoint?: 'source' | 'target';
  bk_inst_id?: number;
  interface_name?: string;
  source_node_key?: string;
  target_node_key?: string;
  source_interface?: NetworkInterfaceRef;
  target_interface?: NetworkInterfaceRef;
  admin_status?: 'up' | 'down' | 'testing' | 'unknown';
  oper_status?: 'up' | 'down' | 'testing' | 'unknown';
  status?: 'ok' | 'error';
  error_code?: string;
  error_message?: string;
  stale?: boolean;
  freshness_window?: string;
  metrics?: Record<string, { value: number | string | null; unit: string }>;
}

/** 单个指标的运行值(由 WeOps batch 接口返回)。 */
export interface NetworkMetricRuntime {
  request_id?: string;
  node_id?: string;
  metric_field: string;
  result_table_id: string;
  sort_order?: number;
  value: number | string | null;
  unit?: string;
  status?: 'ok' | 'error' | 'loading';
  error_code?: string;
  error_message?: string;
  sample_time?: string | null;
  stale?: boolean;
  freshness_window?: string;
  display_mode?: NetworkMetricDisplayMode;
  aggregate_type?: NetworkMetricAggregateType;
  condition_filter?: NetworkMetricConditionFilter[];
}

/** 单个节点的运行态聚合。 */
export interface NetworkNodeRuntime {
  /**
   * 与画布内 `NetworkTopologyNode.id` 一致 —— 即
   * `bk_obj_id:bk_inst_id` 形式（见 buildNetworkNodeClientId）。
   * 后端 runtime 端点在每个节点上输出此字段，索引时用此字段做 key。
   */
  id: string;
  outer_color: string | null;
  metrics: NetworkMetricRuntime[];
  interface_summary?: { total: number; up: number; down: number; unknown: number };
  status: 'normal' | 'critical' | 'unknown';
  error_code?: string;
  error_message?: string;
}

/** 单条连线的运行态聚合。 */
export interface NetworkLinkRuntime {
  id: string;
  source_node_id?: string;
  target_node_id?: string;
  status: 'normal' | 'critical' | 'unknown';
  reason?: string;
  interface_metrics?: string[];
  interfaces: NetworkInterfaceRuntime[];
}

/** 完整运行时响应。 */
export interface NetworkTopologyRuntime {
  nodes: NetworkNodeRuntime[];
  links: NetworkLinkRuntime[];
  stale?: boolean;
  errors?: Array<{ code?: string; message?: string; source?: string }>;
}

/** 画布详情(运行时从后端返回)。后端永远不返回明文 token。 */
export interface NetworkTopologyDetail {
  id: number | string;
  name: string;
  desc?: string;
  groups?: number[];
  /** 仅用于展示"已设置",不暴露真实值。 */
  token_set: boolean;
  base_url: string;
  refresh_interval: number;
  status?: string;
  is_build_in?: boolean;
}

/** 创建 / 更新画布表单数据。token 字段在编辑模式下若为空或 `******` 则前端不发送。 */
export interface NetworkTopologyFormValues {
  base_url: string;
  token?: string;
}

/** page props。 */
export interface NetworkTopologyProps {
  selectedNetworkTopology?: DirItem | null;
}
