import type { Node } from '@xyflow/react';

/** 节点类型定义 */
export type NodeType = 'celery' | 'restful' | 'openai' | 'agents' | 'agui' | 'embedded_chat' | 'web_chat' | 'mobile' | 'condition' | 'http' | 'notification' | 'enterprise_wechat' | 'dingtalk' | 'wechat_official' | 'intent_classification';

/** 基础节点配置 */
interface BaseNodeConfig {
  inputParams?: string;
  outputParams?: string;
}

/** 定时触发节点配置 */
export interface CeleryNodeConfig extends BaseNodeConfig {
  frequency: 'daily' | 'weekly' | 'monthly' | 'custom';
  time: string | { format?: (pattern: string) => string };
  message: string;
  weekday?: number;
  day?: number;
}

/** HTTP 请求节点配置 */
export interface HttpNodeConfig extends BaseNodeConfig {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  url: string;
  params: Array<{ key: string; value: string }>;
  headers: Array<{ key: string; value: string }>;
  requestBody: string;
  timeout: number;
  outputMode: 'once' | 'stream';
}

/** 智能体节点配置 */
export interface AgentsNodeConfig extends BaseNodeConfig {
  agent: number | null;
  agentName: string;
  prompt: string;
  uploadedFiles: Array<{ name: string; url: string }>;
}

/** 条件分支节点配置 */
export interface ConditionNodeConfig extends BaseNodeConfig {
  conditionField: string;
  conditionOperator: 'equals' | 'contains' | 'startsWith' | 'endsWith' | 'regex';
  conditionValue: string;
}

/** 意图分类节点配置 */
export interface IntentClassificationNodeConfig extends BaseNodeConfig {
  agent: number | null;
  intents: Array<{ name: string; description?: string }>;
}

/** 企业微信节点配置 */
export interface EnterpriseWechatNodeConfig extends BaseNodeConfig {
  token: string;
  secret: string;
  aes_key: string;
  corp_id: string;
  agent_id: string;
}

/** 钉钉节点配置 */
export interface DingtalkNodeConfig extends BaseNodeConfig {
  client_id: string;
  client_secret: string;
}

/** 微信公众号节点配置 */
export interface WechatOfficialNodeConfig extends BaseNodeConfig {
  token: string;
  appid: string;
  secret: string;
  aes_key: string;
}

/** 通知节点配置 */
export interface NotificationNodeConfig extends BaseNodeConfig {
  notificationType: 'email' | 'wechat_bot';
  notificationMethod: string;
  notificationChannels: Array<{ id: string; name: string }>;
}

/** Web Chat 节点配置 */
export interface WebChatNodeConfig extends BaseNodeConfig {
  appName: string;
  appDescription: string;
}

/** Mobile 节点配置 */
export interface MobileNodeConfig extends BaseNodeConfig {
  appName: string;
  appTags: string[];
  appDescription: string;
}

/** 通用节点配置（用于 restful、openai 等简单节点） */
export interface SimpleNodeConfig extends BaseNodeConfig {
  name?: string;
}

/** 所有节点配置的联合类型 */
export type NodeConfig =
  | CeleryNodeConfig
  | HttpNodeConfig
  | AgentsNodeConfig
  | ConditionNodeConfig
  | IntentClassificationNodeConfig
  | EnterpriseWechatNodeConfig
  | DingtalkNodeConfig
  | WechatOfficialNodeConfig
  | NotificationNodeConfig
  | WebChatNodeConfig
  | MobileNodeConfig
  | SimpleNodeConfig;

export interface ChatflowNodeData {
  label: string;
  type: NodeType;
  config?: NodeConfig;
  description?: string;
  _timestamp?: number;
  [key: string]: unknown;
}

export interface ChatflowNode extends Node {
  data: ChatflowNodeData;
}

export interface ChatflowEditorRef {
  clearCanvas: () => void;
}

export interface ChatflowEditorProps {
  onSave?: (nodes: Node[], edges: import('@xyflow/react').Edge[]) => void;
  initialData?: { nodes: Node[], edges: import('@xyflow/react').Edge[] } | null;
}

export const isChatflowNode = (node: Node): node is ChatflowNode => {
  const data = node.data as ChatflowNodeData | undefined;
  return !!data &&
         typeof data.label === 'string' &&
         typeof data.type === 'string';
}
