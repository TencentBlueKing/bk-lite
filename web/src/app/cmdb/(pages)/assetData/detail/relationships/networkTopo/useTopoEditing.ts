import { useEffect } from 'react';
import type { Graph } from '@antv/x6';
import { HUB_COLOR } from './constants';
import { relationshipIdFromEdgeId } from './topoEditingUtils';
import { NETWORK_TOPO_VISUAL } from './visualStyles';

export interface PendingLink {
  sourceId: string;
  targetId: string;
}

export interface ContextMenuInfo {
  kind: 'node' | 'edge';
  id: string;
  x: number;
  y: number;
}

interface UseTopoEditingArgs {
  graph: Graph | null;
  editing: boolean;
  // 已选「连线起点」（右键菜单点「新增连线」后设置）；非空时点击节点即选目标
  linkingSourceId: string | null;
  // 图数据版本：rebuild 后变化，用于对新渲染的边重应用光标、对起点重画高亮
  revision: number;
  onContextMenu: (info: ContextMenuInfo) => void;
  onPickTarget: (targetId: string) => void;
  onCancel: () => void;
}

// 右键菜单交互模型：左键拖动=移动设备；右键设备=连线菜单；右键连线=删除菜单。
// 不再使用磁吸拖拽连线，避免「移动节点」与「拉线」抢手势，且新加设备无需 magnet 即可连。
export const useTopoEditing = ({
  graph,
  editing,
  linkingSourceId,
  revision,
  onContextMenu,
  onPickTarget,
  onCancel,
}: UseTopoEditingArgs) => {
  // 节点始终可拖动（移动）；编辑态给边 context-menu 光标提示可右键删除
  useEffect(() => {
    if (!graph) return;
    graph.options.interacting = { nodeMovable: true, edgeMovable: false };
    graph
      .getEdges()
      .forEach((e) => e.attr('line/cursor', editing ? 'context-menu' : 'default'));
  }, [graph, editing, revision]);

  // 高亮当前连线起点
  useEffect(() => {
    if (!graph) return;
    graph.getNodes().forEach((n) => {
      const active = n.id === linkingSourceId;
      const baseBody = n.getData()?.isCenter
        ? NETWORK_TOPO_VISUAL.node.activeBody
        : NETWORK_TOPO_VISUAL.node.defaultBody;
      n.attr('body/strokeDasharray', active ? '6 4' : null);
      n.attr('body/stroke', active ? HUB_COLOR : baseBody.stroke);
      n.attr('body/strokeWidth', active ? 2 : baseBody.strokeWidth);
      n.attr('body/filter', active ? NETWORK_TOPO_VISUAL.node.activeBody.filter : baseBody.filter);
    });
  }, [graph, linkingSourceId, revision]);

  // 右键节点/边 -> 通知父级在点击位置弹上下文菜单
  useEffect(() => {
    if (!graph || !editing) return;
    const onNodeCtx = ({ e, node }: any) => {
      e?.preventDefault?.();
      onContextMenu({ kind: 'node', id: node.id, x: e.clientX, y: e.clientY });
    };
    const onEdgeCtx = ({ e, edge }: any) => {
      e?.preventDefault?.();
      onContextMenu({
        kind: 'edge',
        id: relationshipIdFromEdgeId(edge.id as string),
        x: e.clientX,
        y: e.clientY,
      });
    };
    graph.on('node:contextmenu', onNodeCtx);
    graph.on('edge:contextmenu', onEdgeCtx);
    return () => {
      graph.off('node:contextmenu', onNodeCtx);
      graph.off('edge:contextmenu', onEdgeCtx);
    };
  }, [graph, editing, onContextMenu]);

  // 连线进行中：点击节点=选目标；点击空白=取消
  useEffect(() => {
    if (!graph || !editing) return;
    const onNodeClick = ({ node }: any) => {
      if (linkingSourceId) onPickTarget(node.id as string);
    };
    const onBlank = () => {
      if (linkingSourceId) onCancel();
    };
    graph.on('node:click', onNodeClick);
    graph.on('blank:click', onBlank);
    return () => {
      graph.off('node:click', onNodeClick);
      graph.off('blank:click', onBlank);
    };
  }, [graph, editing, linkingSourceId, onPickTarget, onCancel]);
};
