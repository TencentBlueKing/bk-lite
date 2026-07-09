import { sortExecutionPreviewItems } from '../src/app/opspilot/components/chatflow/utils/executionPreviewOrder';
import type { WorkflowExecutionDetailItem } from '../src/app/opspilot/types/studio';

function assert(condition: unknown, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

const items = [
  {
    node_id: 'agents-1',
    node_name: '智能体',
    node_type: 'agents',
    node_index: null,
    status: 'running',
    error_message: null,
    start_time: null,
    end_time: null,
    duration_ms: null,
  },
  {
    node_id: 'enterprise_wechat_aibot-1',
    node_name: '企微机器人',
    node_type: 'enterprise_wechat_aibot',
    node_index: null,
    status: 'completed',
    error_message: null,
    start_time: null,
    end_time: null,
    duration_ms: null,
  },
  {
    node_id: 'memory_read-1',
    node_name: '记忆读取',
    node_type: 'memory_read',
    node_index: null,
    status: 'completed',
    error_message: null,
    start_time: null,
    end_time: null,
    duration_ms: null,
  },
] satisfies WorkflowExecutionDetailItem[];

const nodes = [
  { id: 'agents-1', position: { x: 300, y: 0 }, data: { label: '智能体', type: 'agents' } },
  { id: 'enterprise_wechat_aibot-1', position: { x: 0, y: 0 }, data: { label: '企微机器人', type: 'enterprise_wechat_aibot' } },
  { id: 'memory_read-1', position: { x: 150, y: 0 }, data: { label: '记忆读取', type: 'memory_read' } },
];

const edges = [
  { id: 'edge-aibot-memory', source: 'enterprise_wechat_aibot-1', target: 'memory_read-1' },
  { id: 'edge-memory-agent', source: 'memory_read-1', target: 'agents-1' },
];

const sorted = sortExecutionPreviewItems(items, nodes, edges);

assert(
  sorted.map((item) => item.node_id).join(',') === 'enterprise_wechat_aibot-1,memory_read-1,agents-1',
  'execution preview items must follow workflow topology instead of API/status order',
);

assert(items[0].node_id === 'agents-1', 'sortExecutionPreviewItems must not mutate source items');
const indexedItems = [
  { ...items[0], node_id: 'agents-2', node_index: 2 },
  { ...items[1], node_id: 'enterprise_wechat_aibot-2', node_index: 1 },
] satisfies WorkflowExecutionDetailItem[];

const sortedWithoutEdges = sortExecutionPreviewItems(
  indexedItems,
  [
    { id: 'agents-2', position: { x: 300, y: 0 }, data: { label: '智能体', type: 'agents' } },
    { id: 'enterprise_wechat_aibot-2', position: { x: 0, y: 0 }, data: { label: '企微机器人', type: 'enterprise_wechat_aibot' } },
  ],
  [],
);

assert(
  sortedWithoutEdges.map((item) => item.node_id).join(',') === 'enterprise_wechat_aibot-2,agents-2',
  'execution preview items must keep node_index fallback when there is no workflow topology',
);