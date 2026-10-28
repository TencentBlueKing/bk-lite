'use client';

import { ThunderboltFilled } from '@ant-design/icons';

import Icon from '@/components/icon';
import type { WorkflowTriggerType } from '../lib/types';

export type WorkflowNodeType = 'TRIGGER' | 'ACTION' | 'CONTROL' | 'RETURN';
export type WorkflowControlKind = 'condition' | 'approval';

const NODE_TYPE_ICON: Record<WorkflowNodeType, string> = {
  TRIGGER: 'blue-trigger',
  ACTION: 'dongzuo1',
  CONTROL: 'kongzhiqi',
  RETURN: 'huifu',
};

const TRIGGER_ICON: Record<WorkflowTriggerType, string> = {
  FORM: 'biaodan',
  SCHEDULE: 'a-icon-dingshichufa1x',
  WEBHOOK: 'RESTfulAPI',
  NATS: 'WebSphereMQ',
};

const ACTION_ATOM_ICON: Record<string, string> = {
  bklite_agent: 'zhinengti',
  bklite_intent_classification: 'question-circle-fill',
  bklite_memory_read: 'zhishiku2',
  bklite_memory_write: 'zhishiku',
  bklite_notification: 'alarm',
  bklite_http_request: 'HTTP',
  bklite_data_transform: 'shujucaiji',
};

const ACTION_CATEGORY_ICON: Record<string, string> = {
  '数据处理': 'shujucaiji',
  '调试': 'gongju',
  '集成': 'shujujicheng',
  '通知': 'alarm',
  '节点管理': 'jiedianguanli',
  OpsPilot: 'opspilot',
  '主机巡检': 'mubiaojiance',
  '作业平台': 'job',
  '报告': 'Word',
  '智能体': 'zhinengti',
  Agent: 'zhinengti',
  '记忆': 'zhishiku2',
  Memory: 'zhishiku2',
};

export function workflowNodeIconName(
  nodeType: WorkflowNodeType,
  category?: string,
  atomKey?: string,
  triggerType?: WorkflowTriggerType,
) {
  if (nodeType === 'TRIGGER' && triggerType) return TRIGGER_ICON[triggerType];
  if (nodeType === 'ACTION' && atomKey && ACTION_ATOM_ICON[atomKey]) return ACTION_ATOM_ICON[atomKey];
  if (nodeType !== 'ACTION') return NODE_TYPE_ICON[nodeType];
  return ACTION_CATEGORY_ICON[category || ''] || NODE_TYPE_ICON.ACTION;
}

export function AtomIcon({
  nodeType,
  category,
  atomKey,
  controlKind,
  triggerType,
  className = 'text-4xl',
}: {
  nodeType: WorkflowNodeType;
  category?: string;
  atomKey?: string;
  controlKind?: WorkflowControlKind;
  triggerType?: WorkflowTriggerType;
  className?: string;
}) {
  if (nodeType === 'CONTROL' && controlKind === 'condition') {
    return <ControlNodeIcon kind="condition" className={className} />;
  }
  if (nodeType === 'CONTROL' && controlKind === 'approval') {
    return <ControlNodeIcon kind="approval" className={className} />;
  }
  const icon = workflowNodeIconName(nodeType, category, atomKey, triggerType);
  return <AtomIconName icon={icon} className={className} />;
}

/** 列表与画布共用：条件 / 审批图标保持一致。 */
export function ControlNodeIcon({ kind, className = 'text-4xl' }: { kind: WorkflowControlKind; className?: string }) {
  if (kind === 'condition') return <Icon type="tiaojianfenzhi" className={className} />;
  return <Icon type="rengongganyu" className={className} />;
}

export function AtomIconName({ icon, className = 'text-4xl' }: { icon: string; className?: string }) {
  if (icon === 'blue-trigger') {
    return (
      <span data-testid="atom-icon-trigger" className={`inline-flex text-[var(--color-primary)] ${className}`}>
        <ThunderboltFilled aria-hidden />
      </span>
    );
  }
  return <Icon type={icon} className={className} />;
}
