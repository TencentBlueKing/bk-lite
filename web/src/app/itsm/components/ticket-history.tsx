'use client';

import { Tag, Timeline } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import { NODE_PALETTE } from '../constants/node-catalog';
import type { TicketHistoryItem, TicketProgressNode } from '../types';
import { NodeGlyph } from './node-glyph';
import { formatTicketTime } from './ticket-collaboration';

export function TicketHistory({ items, nodes }: { items: TicketHistoryItem[]; nodes: TicketProgressNode[] }) {
  const nodeTypes = new Map(nodes.map((node) => [node.id, node.type === 'handle' ? 'manual' : node.type]));
  return <Timeline className="!pl-2 !pt-3" items={items.map((item) => {
    const type = nodeTypes.get(item.node_id) || 'unknown';
    const label = NODE_PALETTE.find((node) => node.type === type)?.label || '流程操作';
    return {
      key: item.id,
      dot: <span aria-label={label} className="inline-flex rounded-lg bg-[var(--color-bg)]"><NodeGlyph type={type} compact /></span>,
      children: <div className="ml-2 flex flex-col gap-1 pb-2">
        <span className="text-xs text-[var(--color-text-3)]">{formatTicketTime(item.finished_at || item.started_at)}</span>
        <span className="text-sm font-medium text-[var(--color-text-1)]">{item.name}</span>
        <div className="mt-1 flex flex-wrap gap-1">
          <Tag icon={<UserOutlined />}>{item.operator || '未分配'}</Tag>
          {item.state === 'current' ? <Tag color="processing">待处理</Tag> : null}
        </div>
      </div>,
    };
  })} />;
}
