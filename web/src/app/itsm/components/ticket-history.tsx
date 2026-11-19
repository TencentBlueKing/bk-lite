'use client';

import { Button, Popconfirm, Tag, Timeline } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import { NODE_PALETTE } from '../constants/node-catalog';
import type { TicketHistoryItem, TicketProgressNode } from '../types';
import { NodeGlyph } from './node-glyph';
import { formatTicketTime } from './ticket-collaboration';

interface TicketHistoryProps {
  items: TicketHistoryItem[];
  nodes: TicketProgressNode[];
  retry?: (id: number) => Promise<void>;
  busy?: boolean;
}

export function TicketHistory({ items, nodes, retry, busy }: TicketHistoryProps) {
  const nodeTypes = new Map(nodes.map((node) => [node.id, node.type === 'handle' ? 'manual' : node.type]));
  return <Timeline className="!pl-2 !pt-3" items={items.map((item) => {
    const type = nodeTypes.get(item.node_id) || 'unknown';
    const label = NODE_PALETTE.find((node) => node.type === type)?.label || '流程操作';
    const executionId = item.execution_id;
    return {
      key: item.id,
      dot: <span aria-label={label} className="inline-flex rounded-lg bg-[var(--color-bg)]"><NodeGlyph type={type} compact /></span>,
      children: <div className="ml-2 flex flex-col gap-1 pb-2">
        <span className="text-xs text-[var(--color-text-3)]">{formatTicketTime(item.finished_at || item.started_at)}</span>
        <span className="text-sm font-medium text-[var(--color-text-1)]">{item.name}</span>
        <div className="mt-1 flex flex-wrap gap-1">
          <Tag icon={<UserOutlined />}>{item.operator || '未分配'}</Tag>
          {item.state === 'current' ? <Tag color="processing">{item.action === 'auto' ? item.action_label : '待处理'}</Tag> : null}
          {item.state === 'failed' ? <Tag color="error">执行失败</Tag> : null}
          {item.action === 'auto_retry' ? <Tag>{item.action_label}</Tag> : null}
        </div>
        {item.action === 'auto' && item.message ? <span className="text-xs text-[var(--color-text-2)]">{item.message}</span> : null}
        {item.can_retry && executionId && retry ? (
          <Popconfirm title={`重试「${item.name}」？`} description="系统会根据执行记录恢复此节点。" okText="确认重试" onConfirm={() => retry(executionId)}>
            <Button size="small" className="self-start" disabled={busy}>重试节点</Button>
          </Popconfirm>
        ) : null}
      </div>,
    };
  })} />;
}
