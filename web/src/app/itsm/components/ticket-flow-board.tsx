'use client';

import { Background, Controls, MiniMap, useReactFlow, Handle, Position, ReactFlow, ReactFlowProvider, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { Button, Modal, Popover, Select, Tag, Tooltip } from 'antd';
import { AimOutlined, DownOutlined, UpOutlined, UserOutlined, ZoomInOutlined } from '@ant-design/icons';
import { NodeGlyph } from './node-glyph';
import { NODE_PALETTE } from '../constants/node-catalog';
import { formatTicketTime } from './ticket-collaboration';
import { useMemo, useState } from 'react';
import type { TicketProgressEdge, TicketProgressNode } from '../types';

const NODE_WIDTH = 220;
const NODE_HEIGHT = 88;
const GATEWAY_TYPES = new Set(['parallel', 'parallel_condition', 'branch', 'branch_condition', 'exclusive', 'converge']);

interface FlowNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  state: TicketProgressNode['state'];
  outcome?: TicketProgressNode['outcome'];
  assignees: string[];
  started_at?: string;
  finished_at?: string;
}

const STATE_CLASS = {
  passed: '[--node-accent:var(--color-primary)]',
  accepted: '[--node-accent:var(--color-success)]',
  rejected: '[--node-accent:var(--color-fail)]',
  current: '[--node-accent:var(--color-warning)]',
  waiting: '[--node-accent:var(--color-border)]',
};
const FRAME_CLASS = 'bg-[linear-gradient(145deg,color-mix(in_srgb,var(--node-accent)_40%,var(--color-bg))_0%,var(--node-accent)_55%,color-mix(in_srgb,var(--node-accent)_75%,var(--color-border))_100%)]';

const STATE_LABEL = { passed: '已流转', accepted: '接受', rejected: '拒绝', current: '待处理', waiting: '未到达' };

export function ProgressNode({ data }: NodeProps<Node<FlowNodeData, 'progress'>>) {
  const outcome = data.state === 'done' ? data.outcome || 'passed' : data.state;
  const typeLabel = NODE_PALETTE.find((item) => item.type === (data.nodeType === 'handle' ? 'manual' : data.nodeType))?.label || '流程节点';
  return (
    <Popover trigger={['hover', 'focus']} title={data.label} content={
      <div className="flex max-w-xs flex-col gap-2 text-xs">
        <div className="flex flex-wrap gap-1"><Tag>{typeLabel}</Tag><Tag>{STATE_LABEL[outcome]}</Tag></div>
        {data.assignees.length ? <div className="flex flex-wrap gap-1">{data.assignees.map((name) => <Tag key={name} icon={<UserOutlined />}>{name}</Tag>)}</div> : null}
        {data.started_at ? <span>到达时间 {formatTicketTime(data.started_at)}</span> : null}
        {data.finished_at ? <span>处理时间 {formatTicketTime(data.finished_at)}</span> : null}
      </div>
    }>
      <div tabIndex={0} aria-current={data.state === 'current' ? 'step' : undefined} aria-label={`${data.label}，${STATE_LABEL[outcome]}`} style={{ width: NODE_WIDTH, height: NODE_HEIGHT }} className={`relative rounded-xl p-[2px] shadow-[0_2px_4px_color-mix(in_srgb,var(--color-text-1)_8%,transparent)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] ${FRAME_CLASS} ${STATE_CLASS[outcome]}`}>
        {data.state === 'current' ? <span className="absolute -top-7 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-full border border-[var(--color-warning)] bg-[var(--color-bg)] px-2 py-0.5 text-xs font-medium text-[var(--color-warning)]"><AimOutlined />当前节点</span> : null}
        <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-[var(--color-border)]" />
        <div className="flex h-full flex-col justify-center gap-2 rounded-[10px] bg-[var(--color-bg)] px-3 shadow-[inset_0_1px_2px_color-mix(in_srgb,var(--color-text-1)_4%,transparent)]">
          <div className="flex min-w-0 items-center gap-2"><NodeGlyph type={data.nodeType} compact /><span className="truncate text-xs font-semibold text-[var(--color-text-1)]">{data.label}</span></div>
          {data.assignees.length ? <div className="flex min-w-0 items-center gap-1">
            <Tag icon={<UserOutlined />} className="!m-0 !flex !max-w-[150px] !items-center !gap-1"><span className="truncate">{data.assignees[0]}</span></Tag>
            {data.assignees.length > 1 ? <Tag className="!m-0">+{data.assignees.length - 1}</Tag> : null}
          </div> : null}
        </div>
        <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-[var(--color-border)]" />
      </div>
    </Popover>
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
      data: { label: node.name, nodeType: node.type, state: node.state, outcome: node.outcome, assignees: node.assignees || [], started_at: node.started_at, finished_at: node.finished_at },
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
  return nodes.map((node) => ({ ...node, state: state.get(node.id) || node.state, outcome: state.get(node.id) !== node.state ? 'passed' : node.outcome }));
};

function FlowNavigation({ nodes, focusIds }: { nodes: TicketProgressNode[]; focusIds: string[] }) {
  const { fitView } = useReactFlow();
  const focus = (ids: string[]) => { void fitView({ nodes: ids.map(id => ({ id })), minZoom: .75, maxZoom: 1, padding: .3, duration: 250 }); };
  return <div className="flex shrink-0 items-center gap-2 pb-2">
    <Select aria-label="定位流程节点" placeholder="搜索并定位节点" className="w-64" showSearch optionFilterProp="label" value={null}
      options={nodes.map(node => ({ value: node.id, label: node.name }))} onChange={id => focus([id])} />
    <Button size="small" aria-label="定位当前节点" onClick={() => focus(focusIds)} icon={<AimOutlined />}>定位当前</Button>
    <Button size="small" aria-label="查看全图" onClick={() => { void fitView({ minZoom: .1, maxZoom: 1, padding: .15, duration: 250 }); }}>全图</Button>
    <span className="text-xs text-[var(--color-text-3)]">拖动画布或缩放查看</span>
  </div>;
}

export function TicketFlowBoard({ nodes, edges }: { nodes: TicketProgressNode[]; edges: TicketProgressEdge[] }) {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const prepared = useMemo(() => withPassedGateways(nodes, edges), [nodes, edges]);
  const current = prepared.filter((node) => node.state === 'current');
  const focusIds = current.length ? current.map(node => node.id) : prepared.slice(0, 1).map(node => node.id);
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
  const canvas = <ReactFlowProvider><div className="flex h-full flex-col"><FlowNavigation nodes={prepared} focusIds={focusIds} /><div className="min-h-0 flex-1"><ReactFlow key={current.map((node) => node.id).join(',')}
    nodes={flowNodes} edges={flowEdges} nodeTypes={NODE_TYPES}
    minZoom={0.1} fitView fitViewOptions={{ nodes: focusIds.map(id => ({ id })), minZoom: .75, maxZoom: 1, padding: .3 }}
    nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} proOptions={{ hideAttribution: true }}
  ><Background /><Controls showFitView={false} showInteractive={false} /><MiniMap pannable zoomable nodeColor="var(--color-primary)" maskColor="var(--color-fill-2)" bgColor="var(--color-bg)" /></ReactFlow></div></div></ReactFlowProvider>;
  return (
    <div className="relative">
      <Button onClick={() => setOpen(!open)} size="small" aria-label="流程图" aria-expanded={open} className="!absolute !-top-7 !left-1/2 !z-30 !flex !-translate-x-1/2 !items-center !gap-1 !bg-[var(--color-bg)]">
        流程图 {open ? <DownOutlined /> : <UpOutlined />}
      </Button>
      {open ? <section aria-label="工单流程图" className="relative rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
        <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-3 text-xs text-[var(--color-text-3)]" aria-label="节点状态图例">
          {(['waiting', 'passed', 'accepted', 'rejected', 'current'] as const).map((state) => <span key={state} className="flex items-center gap-1"><span className={`h-3 w-4 rounded-sm p-[1.5px] ${FRAME_CLASS} ${STATE_CLASS[state]}`}><span className="block h-full w-full rounded-[1px] bg-[var(--color-bg)]" /></span>{STATE_LABEL[state]}</span>)}
        </div>
        <div className="absolute right-3 top-3 z-10"><Tooltip title="全屏查看流程"><Button aria-label="全屏查看流程" size="small" icon={<ZoomInOutlined />} onClick={() => setFullscreen(true)} /></Tooltip></div>
        <div className="h-96 max-h-[42vh] pt-8">{!fullscreen ? canvas : null}</div>
      </section> : null}
      <Modal title="工单流程" open={fullscreen} onCancel={() => setFullscreen(false)} footer={null} width="100vw" className="!top-0 !max-w-none !pb-0" destroyOnHidden>
        <div className="h-[calc(100dvh-110px)]">{fullscreen ? canvas : null}</div>
      </Modal>
    </div>
  );
}
