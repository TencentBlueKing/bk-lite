export interface CatalogNode {
  type: string;
  label: string;
  group: string;
  actions?: string[];
}

export const NODE_GROUPS: Array<{ id: string; name: string; items: CatalogNode[] }> = [
  {
    id: 'event',
    name: '',
    items: [
      { type: 'start', label: '开始', group: 'event' },
      { type: 'end', label: '结束', group: 'event' },
    ],
  },
  {
    id: 'basic',
    name: '基础',
    items: [
      { type: 'submit', label: '提单节点', group: 'basic', actions: ['submit', 'save', 'template'] },
      { type: 'approval', label: '审批节点', group: 'basic', actions: ['approve', 'reject'] },
      { type: 'manual', label: '手动节点', group: 'basic', actions: ['submit', 'claim'] },
      { type: 'auto', label: '自动节点', group: 'basic', actions: ['retry', 'manual_run'] },
      { type: 'decision', label: '决策节点', group: 'basic' },
      { type: 'notice', label: '发送通知', group: 'basic' },
    ],
  },
  {
    id: 'gateway',
    name: '网关',
    items: [
      { type: 'parallel', label: '并行网关', group: 'gateway' },
      { type: 'branch', label: '分支网关', group: 'gateway' },
      { type: 'branch_condition', label: '分支条件网关', group: 'gateway' },
      { type: 'parallel_condition', label: '并行条件网关', group: 'gateway' },
      { type: 'converge', label: '汇聚网关', group: 'gateway' },
    ],
  },
  {
    id: 'dispatch',
    name: '派单',
    items: [
      { type: 'manual_trigger', label: '手动触发', group: 'dispatch' },
      { type: 'rule_trigger', label: '规则组触发', group: 'dispatch' },
      { type: 'auto_dispatch', label: '自动派单', group: 'dispatch' },
    ],
  },
  {
    id: 'subprocess',
    name: '子流程',
    items: [
      { type: 'subprocess', label: '子流程', group: 'subprocess' },
      { type: 'subprocess_submit', label: '子流程提交', group: 'subprocess' },
      { type: 'subprocess_handle', label: '子流程处理', group: 'subprocess', actions: ['submit', 'claim'] },
    ],
  },
  {
    id: 'knowledge',
    name: '知识',
    items: [
      { type: 'knowledge', label: '知识发布', group: 'knowledge' },
    ],
  },
];

export const NODE_PALETTE = NODE_GROUPS.flatMap((group) => group.items);

export const nodeLabelId = (type: string) => `itsm.node.${type}`;
export const nodeGroupId = (name: string) => `itsm.nodeGroup.${name}`;

export const NODE_ACTIONS = [
  { label: '提交', value: 'submit' },
  { label: '保存草稿', value: 'save' },
  { label: '保存模板', value: 'template' },
  { label: '同意', value: 'approve' },
  { label: '拒绝', value: 'reject' },
  { label: '认领', value: 'claim' },
  { label: '重试', value: 'retry' },
  { label: '手动执行', value: 'manual_run' },
];
