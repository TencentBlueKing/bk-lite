'use client';

import { AuditOutlined, PartitionOutlined, ThunderboltFilled } from '@ant-design/icons';

import Icon from '@/components/icon';

export type WorkflowNodeType = 'TRIGGER' | 'ACTION' | 'CONTROL' | 'RETURN';
export type WorkflowControlKind = 'condition' | 'approval';

const NODE_TYPE_ICON: Record<WorkflowNodeType, string> = {
  TRIGGER: 'blue-trigger',
  ACTION: 'dongzuo1',
  CONTROL: 'kongzhiqi',
  RETURN: 'huifu',
};

const ACTION_CATEGORY_ICON: Record<string, string> = {
  '数据处理': 'shujucaiji',
  '调试': 'gongju',
  '集成': 'shujujicheng',
  '通知': 'send-line',
  '节点管理': 'jiedianguanli',
  OpsPilot: 'opspilot',
  '主机巡检': 'mubiaojiance',
  '作业平台': 'job',
  '报告': 'Word',
  '智能体': 'opspilot',
  Agent: 'opspilot',
  '记忆': 'opspilot',
  Memory: 'opspilot',
};

export function workflowNodeIconName(nodeType: WorkflowNodeType, category?: string) {
  if (nodeType !== 'ACTION') return NODE_TYPE_ICON[nodeType];
  return ACTION_CATEGORY_ICON[category || ''] || NODE_TYPE_ICON.ACTION;
}

export function AtomIcon({
  nodeType,
  category,
  controlKind,
  className = 'text-4xl',
}: {
  nodeType: WorkflowNodeType;
  category?: string;
  controlKind?: WorkflowControlKind;
  className?: string;
}) {
  if (nodeType === 'CONTROL' && controlKind === 'condition') {
    return <ControlNodeIcon kind="condition" className={className} />;
  }
  if (nodeType === 'CONTROL' && controlKind === 'approval') {
    return <ControlNodeIcon kind="approval" className={className} />;
  }
  const icon = workflowNodeIconName(nodeType, category);
  return <AtomIconName icon={icon} className={className} />;
}

/** 列表与画布共用：条件 / 审批图标保持一致。 */
export function ControlNodeIcon({ kind, className = 'text-4xl' }: { kind: WorkflowControlKind; className?: string }) {
  const Glyph = kind === 'approval' ? AuditOutlined : PartitionOutlined;
  return (
    <span className={`inline-flex text-[var(--color-primary)] ${className}`} aria-hidden>
      <Glyph />
    </span>
  );
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
