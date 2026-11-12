'use client';

import {
  Background,
  BaseEdge,
  ConnectionLineType,
  Controls,
  EdgeLabelRenderer,
  getSmoothStepPath,
  Handle,
  MarkerType,
  NodeToolbar,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodeId,
  useNodesState,
  useReactFlow,
  type Connection,
  type EdgeProps,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { Button, Checkbox, Input, Select, Switch, Tag } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  DEMO_FLOW,
  canvasFromDesign,
  designFromCanvas,
  type CanvasEdge,
  type CanvasNode,
  type CanvasNodeData,
  type FlowDesign,
} from '../constants/demo-flow';
import { NODE_ACTIONS, NODE_GROUPS, NODE_PALETTE, nodeLabelId } from '../constants/node-catalog';
import { ConditionBuilder } from './condition-builder';
import { CanvasTools } from './canvas-tools';
import { UserSelector } from './user-selector';
import { useTranslation } from '@/utils/i18n';

const NODE_WIDTH = 148;
const NODE_HEIGHT = 56;
const GATEWAY_TYPES = new Set(['parallel', 'parallel_condition', 'branch', 'branch_condition', 'exclusive', 'converge']);
const BRANCH_TYPES = new Set(['branch', 'branch_condition', 'exclusive']);

type ItsmFlowNodeType = Node<CanvasNodeData, 'itsm'>;

const flowActions: {
  copyNode: (id: string) => void;
  removeNode: (id: string) => void;
  removeEdge: (id: string) => void;
} = {
  copyNode: () => undefined,
  removeNode: () => undefined,
  removeEdge: () => undefined,
};

function ItsmNode({ data, selected }: NodeProps<ItsmFlowNodeType>) {
  const { t } = useTranslation();
  const nodeId = useNodeId();
  const typeLabel = t(nodeLabelId(data.nodeType));
  const handleClass = '!h-3 !w-3 !rounded-full !border-2 !border-[var(--color-bg)] !bg-[var(--color-primary)]';

  return (
    <div
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
      className={`relative flex items-center gap-2.5 rounded-lg border px-3 py-2 transition-all ${
        selected
          ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)] shadow-xs'
          : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-primary)]'
      }`}
    >
      {selected && nodeId ? (
        <NodeToolbar isVisible position={Position.Top} align="end" offset={4}>
          <CanvasTools onCopy={() => flowActions.copyNode(nodeId)} onDelete={() => flowActions.removeNode(nodeId)} />
        </NodeToolbar>
      ) : null}
      {data.nodeType === 'start' ? null : (
        <Handle type="target" position={Position.Left} isConnectableStart={false} className={handleClass} />
      )}
      <span className="h-8 w-1 shrink-0 rounded-full bg-[var(--color-primary)]" />
      <div className="flex min-w-0 flex-1 flex-col justify-center">
        <span className="truncate text-xs font-semibold text-[var(--color-text-1)]">{data.label}</span>
        <span className="truncate text-[11px] text-[var(--color-text-3)]">{typeLabel}</span>
      </div>
      {data.nodeType === 'end' ? null : (
        <Handle type="source" position={Position.Right} isConnectableEnd={false} className={handleClass} />
      )}
    </div>
  );
}

function ItsmEdge({ id, selected, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style }: EdgeProps) {
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} interactionWidth={16} />
      {selected ? (
        <EdgeLabelRenderer>
          <div className="pointer-events-auto absolute" style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}>
            <CanvasTools onDelete={() => flowActions.removeEdge(id)} />
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const NODE_TYPES = { itsm: ItsmNode };
const EDGE_TYPES = { itsm: ItsmEdge };

const INITIAL = canvasFromDesign(DEMO_FLOW);

interface FlowDesignerProps {
  design?: FlowDesign;
  fields?: string[];
  invalidNodeIds?: string[];
  onChange?: (design: FlowDesign) => void;
}

const layoutNodes = (nodes: CanvasNode[], edges: CanvasEdge[]): CanvasNode[] => {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 64 });
  nodes.forEach((node) => graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return nodes.map((node) => {
    const position = graph.node(node.id);
    return {
      ...node,
      position: {
        x: position.x - NODE_WIDTH / 2,
        y: position.y - NODE_HEIGHT / 2,
      },
    };
  });
};

export function FlowDesigner(props: FlowDesignerProps) {
  return (
    <ReactFlowProvider>
      <FlowDesignerBody {...props} />
    </ReactFlowProvider>
  );
}

function FlowDesignerBody({ design, fields = [], invalidNodeIds = [], onChange }: FlowDesignerProps) {
  const { t } = useTranslation();
  const seeded = design?.nodes?.length ? canvasFromDesign(design) : INITIAL;
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(
    layoutNodes(seeded.nodes, seeded.edges).map((node) => ({
      ...node,
      type: node.type || 'itsm',
      style: invalidNodeIds.includes(node.id) ? { border: '1px solid var(--color-primary)' } : undefined,
    }))
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<CanvasEdge>(seeded.edges);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const selected = nodes.find((node) => node.id === selectedId);
  const { screenToFlowPosition } = useReactFlow();
  const nodeSeq = useRef(nodes.length);

  const styledEdges = useMemo(
    () =>
      edges.map((edge) => {
        const strokeColor = edge.id === selectedEdgeId || edge.selected ? 'var(--color-primary)' : 'var(--color-border)';
        return {
          ...edge,
          selected: edge.id === selectedEdgeId,
          interactionWidth: 16,
          type: 'itsm',
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: strokeColor,
          },
          style: {
            stroke: strokeColor,
            strokeWidth: edge.selected ? 2 : 1.5,
          },
        };
      }),
    [edges, selectedEdgeId]
  );

  useEffect(() => {
    onChange?.(designFromCanvas(nodes, edges));
  }, [edges, nodes, onChange]);

  const removeNode = (id: string) => {
    setNodes((current) => current.filter((node) => node.id !== id));
    setEdges((current) => current.filter((edge) => edge.source !== id && edge.target !== id));
    setSelectedId((current) => (current === id ? null : current));
    setSelectedEdgeId(null);
  };

  const removeEdge = (id: string) => {
    setEdges((current) => current.filter((edge) => edge.id !== id));
    setSelectedEdgeId((current) => (current === id ? null : current));
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Backspace' && event.key !== 'Delete') {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }
      if (selectedEdgeId) {
        event.preventDefault();
        removeEdge(selectedEdgeId);
        return;
      }
      if (selectedId) {
        event.preventDefault();
        removeNode(selectedId);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedEdgeId, selectedId]);

  const patchSelected = (patch: Partial<CanvasNode['data']>) => {
    if (!selected) {
      return;
    }
    setNodes((current) => current.map((node) => (
      node.id === selected.id ? { ...node, data: { ...node.data, ...patch } } : node
    )));
  };

  const copyNode = (id: string) => {
    const source = nodes.find((node) => node.id === id);
    if (!source) {
      return;
    }
    const created = makeNode(source.data.nodeType, source.data.label, {
      x: source.position.x + 28,
      y: source.position.y + 28,
    });
    created.data = { ...source.data };
    setNodes((current) => [...current.map((node) => ({ ...node, selected: false })), { ...created, selected: true }]);
    setSelectedId(created.id);
    setSelectedEdgeId(null);
  };

  const makeNode = (type: string, label: string, position: { x: number; y: number }, id?: string): CanvasNode => {
    nodeSeq.current += 1;
    return {
      id: id || `${type}_${nodeSeq.current}`,
      type: 'itsm',
      position,
      data: {
        label,
        nodeType: type,
        assignees: [],
        orSign: type === 'approval',
        actions: NODE_PALETTE.find((item) => item.type === type)?.actions || [],
      },
    };
  };

  const link = (source: string, target: string, isDefault = false): CanvasEdge => ({
    id: `e_${source}_${target}`,
    type: 'itsm',
    source,
    target,
    data: isDefault ? { isDefault: true } : undefined,
  });

  const addNode = (type: string, label: string, position?: { x: number; y: number }, sourceId?: string | null) => {
    const anchor = nodes.find((node) => node.id === selectedId);
    const origin = position || {
      x: anchor ? anchor.position.x + NODE_WIDTH + 72 : 80,
      y: anchor ? anchor.position.y : 80,
    };
    const created = makeNode(type, label, origin);
    const extra: CanvasNode[] = [];
    const createdEdges: CanvasEdge[] = [];
    if (sourceId && sourceId !== created.id) {
      const from = nodes.find((node) => node.id === sourceId);
      const needsDefault = Boolean(from && BRANCH_TYPES.has(from.data.nodeType) && !edges.some((edge) => edge.source === sourceId && edge.data?.isDefault));
      createdEdges.push(link(sourceId, created.id, needsDefault));
    }
    if (GATEWAY_TYPES.has(type) && type !== 'converge') {
      const upper = makeNode('manual', t('itsm.node.manual'), { x: origin.x + 220, y: origin.y - 80 });
      const lower = makeNode('manual', t('itsm.node.manual'), { x: origin.x + 220, y: origin.y + 80 });
      extra.push(upper, lower);
      const branching = BRANCH_TYPES.has(type);
      createdEdges.push(link(created.id, upper.id, false));
      createdEdges.push(link(created.id, lower.id, branching));
      if (type === 'parallel' || type === 'parallel_condition') {
        const join = makeNode('converge', t('itsm.node.converge'), { x: origin.x + 440, y: origin.y });
        extra.push(join);
        createdEdges.push(link(upper.id, join.id));
        createdEdges.push(link(lower.id, join.id));
      }
    }
    setNodes((current) => [...current, created, ...extra]);
    if (createdEdges.length) {
      setEdges((current) => [...current, ...createdEdges]);
    }
    setSelectedId(created.id);
  };

  const onDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  };

  const onDrop = (event: React.DragEvent) => {
    event.preventDefault();
    const raw = event.dataTransfer.getData('application/itsm-node');
    if (!raw) {
      return;
    }
    const payload = JSON.parse(raw) as { type?: string; label?: string };
    if (!payload.type || !payload.label) {
      return;
    }
    addNode(payload.type, payload.label, screenToFlowPosition({ x: event.clientX, y: event.clientY }), null);
  };

  const canConnect = (sourceId?: string | null, targetId?: string | null) => {
    if (!sourceId || !targetId || sourceId === targetId) {
      return false;
    }
    const source = nodes.find((node) => node.id === sourceId);
    const target = nodes.find((node) => node.id === targetId);
    if (!source || !target || source.data.nodeType === 'end' || target.data.nodeType === 'start') {
      return false;
    }
    return !edges.some((edge) => edge.source === sourceId && edge.target === targetId);
  };

  const onConnectEnd = (event: MouseEvent | TouchEvent, state: { isValid: boolean | null; fromNode: { id: string } | null; toNode: { id: string } | null }) => {
    if (!state.fromNode || state.isValid) {
      return;
    }
    const source = nodes.find((node) => node.id === state.fromNode?.id);
    if (!source || source.data.nodeType === 'end') {
      return;
    }
    const element = event.target as HTMLElement | null;
    const hoveredId = state.toNode?.id || element?.closest('.react-flow__node')?.getAttribute('data-id');
    if (hoveredId && canConnect(source.id, hoveredId)) {
      connect({ source: source.id, target: hoveredId, sourceHandle: null, targetHandle: null });
      return;
    }
    if (hoveredId || element?.closest('.react-flow__controls') || element?.closest('.react-flow__minimap')) {
      return;
    }
    const point = 'changedTouches' in event ? event.changedTouches[0] : event;
    if (!point) {
      return;
    }
    const position = screenToFlowPosition({ x: point.clientX, y: point.clientY });
    addNode('manual', t('itsm.node.manual'), { x: position.x, y: position.y - NODE_HEIGHT / 2 }, source.id);
  };

  const connect = (connection: Connection) => {
    if (!canConnect(connection.source, connection.target)) {
      return;
    }
    setEdges((current) => {
      if (current.some((edge) => edge.source === connection.source && edge.target === connection.target)) {
        return current;
      }
      const from = nodes.find((node) => node.id === connection.source);
      const needsDefault = Boolean(from && BRANCH_TYPES.has(from.data.nodeType) && !current.some((edge) => edge.source === connection.source && edge.data?.isDefault));
      return addEdge({
        ...connection,
        type: 'itsm',
        data: needsDefault ? { isDefault: true } : undefined,
      }, current);
    });
  };

  flowActions.copyNode = copyNode;
  flowActions.removeNode = removeNode;
  flowActions.removeEdge = removeEdge;

  return (
    <div className="grid h-full min-h-0 items-stretch overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]" style={{ gridTemplateColumns: `${leftOpen ? 220 : 28}px minmax(0,1fr) ${rightOpen ? 320 : 28}px` }}>
      <div className={`relative flex h-full min-h-0 flex-col justify-between gap-4 border-r border-[var(--color-border)] bg-[var(--color-bg)] ${leftOpen ? 'p-4' : 'p-1'}`}>
        <button type="button" aria-label={leftOpen ? t('itsm.admin.collapseNodes') : t('itsm.admin.expandNodes')} className="absolute top-1/2 -right-3 z-20 flex h-12 w-6 -translate-y-1/2 items-center justify-center rounded-full bg-[var(--color-primary)] text-white shadow-md" onClick={() => setLeftOpen((open) => !open)}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d={leftOpen ? 'M9 2.5 L4.5 7 L9 11.5' : 'M5 2.5 L9.5 7 L5 11.5'} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {leftOpen ? <>
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="border-b border-[var(--color-border)] pb-2.5">
            <div className="text-sm font-medium text-[var(--color-text-1)]">{t('itsm.admin.nodePanel')}</div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
            {NODE_GROUPS.map((group) => (
              <div key={group.id} className="flex flex-col gap-1.5">
                {group.name ? <div className="text-xs font-medium text-[var(--color-text-3)]">{t(`itsm.nodeGroup.${group.id}`)}</div> : null}
                {group.items.map((item) => (
                  <div
                    key={item.type}
                    role="button"
                    tabIndex={0}
                    draggable
                    className="group flex cursor-grab items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-2 text-left transition-all hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)] active:cursor-grabbing"
                    onDragStart={(event) => {
                      event.dataTransfer.setData('application/itsm-node', JSON.stringify({ type: item.type, label: t(nodeLabelId(item.type)) }));
                      event.dataTransfer.effectAllowed = 'move';
                    }}
                    onClick={() => addNode(item.type, t(nodeLabelId(item.type)), undefined, null)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        addNode(item.type, t(nodeLabelId(item.type)), undefined, null);
                      }
                    }}
                  >
                    <span className="h-3.5 w-1 shrink-0 rounded-full bg-[var(--color-primary)]" />
                    <span className="truncate text-xs font-medium text-[var(--color-text-1)] group-hover:text-[var(--color-primary)]">
                      {t(nodeLabelId(item.type))}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div className="border-t border-[var(--color-border)] pt-3">
          <Button
            block
            onClick={() => setNodes((current) => layoutNodes(current, edges))}
          >
            整理布局
          </Button>
        </div>
        </> : null}
      </div>

      <div className="flex h-full min-h-0 flex-col bg-[var(--color-fill-1)] p-3">
        <div className="h-full min-h-0 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] shadow-xs">
          <ReactFlow
            nodes={nodes}
            edges={styledEdges}
            nodeTypes={NODE_TYPES}
            edgeTypes={EDGE_TYPES}
            defaultEdgeOptions={{
              type: 'itsm',
              markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--color-border)' },
              style: { stroke: 'var(--color-border)', strokeWidth: 1.5 },
            }}
            defaultViewport={{ x: 48, y: 120, zoom: 1 }}
            minZoom={0.4}
            maxZoom={2}
            nodesDraggable
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            deleteKeyCode={null}
            onConnect={connect}
            onConnectEnd={onConnectEnd}
            isValidConnection={(connection) => canConnect(connection.source, connection.target)}
            connectionRadius={40}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onNodeClick={(_event, node) => { setSelectedId(node.id); setSelectedEdgeId(null); setRightOpen(true); }}
            onEdgeClick={(_event, edge) => { setSelectedEdgeId(edge.id); setSelectedId(null); setRightOpen(true); }}
            onPaneClick={() => { setSelectedId(null); setSelectedEdgeId(null); }}
            connectionLineType={ConnectionLineType.SmoothStep}
            connectionLineStyle={{ stroke: 'var(--color-primary)', strokeWidth: 1.5 }}
          >
            <Background />
            <Controls showFitView={false} showInteractive={false} />
          </ReactFlow>
        </div>
      </div>

      <div className={`relative flex h-full min-h-0 flex-col gap-3 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-bg)] ${rightOpen ? 'p-4' : 'overflow-hidden p-1'}`}>
        <button type="button" aria-label={rightOpen ? '收起属性' : '展开属性'} className="absolute top-1/2 -left-3 z-20 flex h-12 w-6 -translate-y-1/2 items-center justify-center rounded-full bg-[var(--color-primary)] text-white shadow-md" onClick={() => setRightOpen((open) => !open)}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d={rightOpen ? 'M5 2.5 L9.5 7 L5 11.5' : 'M9 2.5 L4.5 7 L9 11.5'} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {rightOpen ? <>
        <div className="border-b border-[var(--color-border)] pb-2.5">
          <div className="text-sm font-medium text-[var(--color-text-1)]">节点属性</div>
        </div>
        {selected ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between rounded-lg bg-[var(--color-fill-1)] px-3 py-2">
              <span className="text-xs font-medium text-[var(--color-text-2)]">节点类型</span>
              <Tag className="m-0">{t(nodeLabelId(selected.data.nodeType))}</Tag>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--color-text-2)]">节点名称</span>
              <Input value={selected.data.label} onChange={(event) => patchSelected({ label: event.target.value })} />
            </div>
            {['approval', 'handle', 'manual', 'submit', 'subprocess_handle'].includes(selected.data.nodeType) ? (
              <>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-[var(--color-text-2)]">处理人</span>
                  <UserSelector value={selected.data.assignees} onChange={(assignees) => patchSelected({ assignees })} />
                </div>
                <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2">
                  <span className="text-xs font-medium text-[var(--color-text-1)]">多人或签</span>
                  <Switch checked={selected.data.orSign} onChange={(orSign) => patchSelected({ orSign })} />
                </div>
                <div className="flex flex-col gap-1.5 rounded-lg border border-[var(--color-border)] p-3">
                  <span className="text-xs font-medium text-[var(--color-text-2)]">可执行操作</span>
                  <Checkbox.Group
                    value={selected.data.actions}
                    options={NODE_ACTIONS}
                    onChange={(actions) => patchSelected({ actions: actions.map(String) })}
                  />
                </div>
                <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2">
                  <span className="text-xs font-medium text-[var(--color-text-1)]">节点流转通知</span>
                  <Switch checked={Boolean(selected.data.notify)} onChange={(notify) => patchSelected({ notify })} />
                </div>
                {fields.length ? (
                  <div className="flex flex-col gap-2 border-t border-[var(--color-border)] pt-3">
                    <span className="text-xs font-semibold text-[var(--color-text-2)]">字段权限</span>
                    <div className="flex flex-col gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-2.5">
                      {fields.map((field) => (
                        <div key={field} className="flex items-center justify-between gap-2">
                          <span className="text-xs text-[var(--color-text-1)]">{field}</span>
                          <SelectPerm
                            value={selected.data.fieldPerm?.[field] || 'edit'}
                            onChange={(perm) => patchSelected({ fieldPerm: { ...selected.data.fieldPerm, [field]: perm } })}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </>
            ) : null}
            <div className="flex flex-col gap-2 border-t border-[var(--color-border)] pt-3">
              <span className="text-xs font-semibold text-[var(--color-text-2)]">流转条件</span>
              <ConditionBuilder
                fields={fields}
                onChange={(condition) => {
                  patchSelected({ condition });
                  setEdges((current) => {
                    const outgoing = current.filter((edge) => edge.source === selected.id);
                    if (outgoing.length < 2) {
                      return current;
                    }
                    return current.map((edge) => {
                      if (edge.source !== selected.id) {
                        return edge;
                      }
                      if (edge.id === outgoing[0].id) {
                        return { ...edge, data: { ...(edge.data || {}), isDefault: true } };
                      }
                      return { ...edge, data: { ...(edge.data || {}), condition, isDefault: false } };
                    });
                  });
                }}
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-xs text-[var(--color-text-3)]">选择节点</div>
        )}
        </> : null}
      </div>
    </div>
  );
}

function SelectPerm({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Select
      size="small"
      className="w-28"
      value={value}
      options={[
        { value: 'edit', label: '可编辑' },
        { value: 'read', label: '只读' },
        { value: 'hidden', label: '隐藏' },
      ]}
      onChange={onChange}
    />
  );
}
