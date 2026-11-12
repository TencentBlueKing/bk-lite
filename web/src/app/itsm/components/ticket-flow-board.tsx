'use client';

import { Background, Controls, Handle, Position, ReactFlow, ReactFlowProvider, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { Button } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import type { TicketProgressEdge, TicketProgressNode } from '../types';

const NODE_WIDTH = 168;
const NODE_HEIGHT = 64;
const GATEWAY_TYPES = new Set(['parallel', 'parallel_condition', 'branch', 'branch_condition', 'exclusive', 'converge']);

interface FlowNodeData extends Record<string, unknown> {
  label: string;
  state: TicketProgressNode['state'];
  assignees: string[];
}

const STATE_CLASS = {
  done: 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)]',
  current: 'border-[var(--color-primary)] bg-[var(--color-bg)] shadow-xs',
  waiting: 'border-[var(--color-border)] bg-[var(--color-bg)] opacity-60',
};

function ProgressNode({ data }: NodeProps<Node<FlowNodeData, 'progress'>>) {
  const { t } = useTranslation();
  const caption = data.state === 'current'
    ? t('itsm.ticket.currentHandler', undefined, { names: data.assignees.join('、') || t('itsm.ticket.unassigned') })
    : data.state === 'done'
      ? t('itsm.ticket.passed')
      : t('itsm.ticket.notReached');
  return (
    <div style={{ width: NODE_WIDTH, height: NODE_HEIGHT }} className={`relative flex flex-col justify-center rounded-lg border px-3 ${STATE_CLASS[data.state]}`}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-[var(--color-primary)]" />
      <span className="truncate text-xs font-semibold text-[var(--color-text-1)]">{data.label}</span>
      <span className="truncate text-[11px] text-[var(--color-text-3)]">{caption}</span>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-[var(--color-primary)]" />
    </div>
  );
}

const NODE_TYPES = { progress: ProgressNode };

const layout = (nodes: TicketProgressNode[], edges: TicketProgressEdge[]) => {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: 'LR', nodesep: 36, ranksep: 72 });
  nodes.forEach((node) => graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((edge) => {
    if (edge.from && edge.to) {
      graph.setEdge(edge.from, edge.to);
    }
  });
  dagre.layout(graph);
  return nodes.map((node) => {
    const position = graph.node(node.id);
    return {
      id: node.id,
      type: 'progress',
      position: { x: (position?.x || 0) - NODE_WIDTH / 2, y: (position?.y || 0) - NODE_HEIGHT / 2 },
      data: { label: node.name, state: node.state, assignees: node.assignees || [] },
    };
  });
};

const withPassedGateways = (nodes: TicketProgressNode[], edges: TicketProgressEdge[]): TicketProgressNode[] => {
  const state = new Map(nodes.map((node) => [node.id, node.state]));
  let changed = true;
  while (changed) {
    changed = false;
    nodes.forEach((node) => {
      if (!GATEWAY_TYPES.has(node.type) || state.get(node.id) !== 'waiting') {
        return;
      }
      const reached = edges.some((edge) => edge.from === node.id && state.get(edge.to) !== 'waiting');
      if (reached) {
        state.set(node.id, 'done');
        changed = true;
      }
    });
  }
  return nodes.map((node) => ({ ...node, state: state.get(node.id) || node.state }));
};

export function TicketFlowBoard({ nodes, edges }: { nodes: TicketProgressNode[]; edges: TicketProgressEdge[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const prepared = useMemo(() => withPassedGateways(nodes, edges), [nodes, edges]);
  const current = prepared.filter((node) => node.state === 'current');
  const passed = prepared.filter((node) => node.state === 'done').length;
  const flowNodes = useMemo(() => layout(prepared, edges), [prepared, edges]);
  const flowEdges = edges.filter((edge) => edge.from && edge.to).map((edge) => {
    const source = prepared.find((node) => node.id === edge.from);
    const target = prepared.find((node) => node.id === edge.to);
    const taken = source?.state !== 'waiting' && target?.state !== 'waiting';
    return {
      id: `${edge.from}-${edge.to}`,
      source: edge.from,
      target: edge.to,
      style: { stroke: taken ? 'var(--color-primary)' : 'var(--color-border)' },
    };
  });
  const summary = current.length
    ? current.map((node) => `${node.name}（${(node.assignees || []).join('、') || t('itsm.ticket.unassigned')}）`).join('、')
    : t('itsm.ticket.flowNone');

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <div className="min-w-0 text-sm text-[var(--color-text-1)]">
          <span className="font-medium">{t('itsm.ticket.flow')}</span>
          <span className="ml-2 text-xs text-[var(--color-text-3)]">{t('itsm.ticket.flowCurrent', undefined, { summary })} · {t('itsm.ticket.flowPassed', undefined, { count: passed })}</span>
        </div>
        <Button size="small" onClick={() => setOpen((value) => !value)}>{open ? t('itsm.ticket.collapseFlow') : t('itsm.ticket.expandFlow')}</Button>
      </div>
      {open ? (
        <div className="h-80 border-t border-[var(--color-border)]">
          <ReactFlowProvider>
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={NODE_TYPES}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              proOptions={{ hideAttribution: true }}
            >
              <Background />
              <Controls showInteractive={false} />
            </ReactFlow>
          </ReactFlowProvider>
        </div>
      ) : null}
    </div>
  );
}
