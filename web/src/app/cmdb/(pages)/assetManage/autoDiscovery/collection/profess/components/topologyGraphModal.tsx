'use client';

import React, { useEffect, useMemo } from 'react';
import { Modal, Empty } from 'antd';
import { Graph } from '@antv/x6';
import {
  XFlow,
  XFlowGraph,
  Grid,
  Minimap,
  useGraphStore,
  useGraphInstance,
} from '@antv/xflow';
import { useTranslation } from '@/utils/i18n';
import { getIconUrl } from '@/app/cmdb/utils/common';
import type { TopologyLinkRow } from '@/app/cmdb/types/autoDiscovery';

interface TopologyGraphModalProps {
  open: boolean;
  onClose: () => void;
  links: TopologyLinkRow[];
}

// 设备节点尺寸（拓扑里设备是「对象」，端口不单独成节点）
const NODE_WIDTH = 260;
const NODE_HEIGHT = 72;
const DEVICE_NODE_SHAPE = 'topo-collect-device';
const HUB_COLOR = '#0070fa';

// 未激活 / 激活（蓝框高亮）两套卡片描边样式，注册默认值与点击切换共用
const DEFAULT_BODY_ATTRS = {
  stroke: 'var(--color-border-1)',
  strokeWidth: 1,
  filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.08))',
};
const ACTIVE_BODY_ATTRS = {
  stroke: HUB_COLOR,
  strokeWidth: 2,
  filter: 'drop-shadow(0 2px 10px rgba(0,112,250,0.35))',
};

// 拓扑链路快照里 inst_name 形如 `${device}-${端口名}`，展示端口时剥掉设备前缀
const stripDevicePrefix = (
  instName?: string,
  device?: string
): string | undefined => {
  if (!instName) return instName;
  if (device && instName.startsWith(`${device}-`)) {
    return instName.slice(device.length + 1);
  }
  return instName;
};

// 设备节点形状只注册一次：图标 + 设备名，不带展开按钮
let deviceNodeRegistered = false;
const ensureDeviceNodeRegistered = () => {
  if (deviceNodeRegistered) return;
  Graph.registerNode(
    DEVICE_NODE_SHAPE,
    {
      inherit: 'rect',
      markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'image', selector: 'img' },
        { tagName: 'title', selector: 'tt' },
        { tagName: 'text', selector: 'lbl' },
      ],
      attrs: {
        body: {
          rx: 10,
          ry: 10,
          fill: 'var(--color-bg-1)',
          cursor: 'pointer',
          // 轻微投影，做出卡片浮起的质感
          ...DEFAULT_BODY_ATTRS,
        },
        img: {
          width: 44,
          height: 44,
          x: 18,
          y: (NODE_HEIGHT - 44) / 2,
        },
        lbl: {
          // 图标右侧左对齐、垂直居中；用比例锚点避开绝对 x/y + textWrap 跑框外的坑
          refX: 0.27,
          refY: 0.5,
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          fontSize: 16,
          fontWeight: 600,
          fill: 'var(--color-text-1)',
          textWrap: { width: NODE_WIDTH - 84, height: 24, ellipsis: true },
        },
      },
    },
    true
  );
  deviceNodeRegistered = true;
};

interface BuiltGraph {
  nodes: any[];
  edges: any[];
}

// 把采集到的链路转成「设备为节点、端口关系为连线」的图数据
const buildGraphData = (
  links: TopologyLinkRow[],
  portLabelFill: string
): BuiltGraph => {
  const deviceIcon = getIconUrl({ icn: '', model_id: 'network' });

  // 收集去重后的设备，作为节点
  const deviceSet = new Set<string>();
  const normalizedLinks = links
    .map((link) => {
      const localDevice = link.source_device;
      const remoteDevice = link.target_device || link.remote_device_name;
      if (!localDevice || !remoteDevice) return null;
      const localPort =
        stripDevicePrefix(link.source_inst_name, link.source_device) ||
        link.source_port_id ||
        '';
      const remotePort =
        link.remote_port_name ||
        stripDevicePrefix(link.target_inst_name, link.target_device) ||
        link.target_port_id ||
        '';
      deviceSet.add(localDevice);
      deviceSet.add(remoteDevice);
      return { localDevice, remoteDevice, localPort, remotePort };
    })
    .filter(Boolean) as Array<{
    localDevice: string;
    remoteDevice: string;
    localPort: string;
    remotePort: string;
  }>;

  const devices = Array.from(deviceSet);

  // 统计每台设备的连接数，连接最多的作为「中心设备」高亮（对应参考图里的蓝框）
  const degree: Record<string, number> = {};
  normalizedLinks.forEach((link) => {
    degree[link.localDevice] = (degree[link.localDevice] || 0) + 1;
    degree[link.remoteDevice] = (degree[link.remoteDevice] || 0) + 1;
  });
  const maxDegree = devices.reduce((max, d) => Math.max(max, degree[d] || 0), 0);
  // 只取一台作为初始激活的中心设备，避免并列时多个一起高亮
  const hubDevice =
    maxDegree >= 2
      ? devices.find((d) => (degree[d] || 0) === maxDegree)
      : undefined;

  // 环形布局：设备均匀分布在一个圆上
  const count = devices.length;
  const radius = Math.max(300, count * 64);
  const centers: Record<string, { x: number; y: number }> = {};
  const nodes = devices.map((device, index) => {
    const angle =
      count === 1 ? 0 : (index / count) * Math.PI * 2 - Math.PI / 2;
    const cx = count === 1 ? 0 : Math.cos(angle) * radius;
    const cy = count === 1 ? 0 : Math.sin(angle) * radius;
    const x = cx - NODE_WIDTH / 2;
    const y = cy - NODE_HEIGHT / 2;
    centers[device] = { x: cx, y: cy };

    // 默认激活连接数最多的「中心设备」，之后可点击切换到其它设备
    const bodyAttrs = device === hubDevice ? ACTIVE_BODY_ATTRS : {};

    return {
      id: device,
      x,
      y,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      shape: DEVICE_NODE_SHAPE,
      attrs: {
        body: bodyAttrs,
        img: { 'xlink:href': deviceIcon },
        tt: { text: device },
        lbl: { text: device, title: device },
      },
    };
  });

  // 同一对设备之间可能有多条端口链路，按设备对分组以便错开扇形展开
  const pairCount: Record<string, number> = {};
  const pairIndex: Record<string, number> = {};
  normalizedLinks.forEach((link) => {
    const key = [link.localDevice, link.remoteDevice].sort().join('__');
    pairCount[key] = (pairCount[key] || 0) + 1;
  });

  const portLabel = (position: number, text: string) => ({
    position,
    markup: [
      { tagName: 'rect', selector: 'bg' },
      { tagName: 'text', selector: 'txt' },
    ],
    attrs: {
      txt: {
        text: text || '--',
        fill: portLabelFill,
        fontSize: 11,
        textAnchor: 'middle',
        textVerticalAnchor: 'middle',
      },
      bg: {
        ref: 'txt',
        refWidth: '130%',
        refHeight: '130%',
        refX: '-15%',
        refY: '-15%',
        fill: 'var(--color-bg-1)',
        stroke: 'var(--color-border-3)',
        rx: 3,
        ry: 3,
      },
    },
  });

  const edges = normalizedLinks.map((link, index) => {
    const key = [link.localDevice, link.remoteDevice].sort().join('__');
    const total = pairCount[key];
    const idx = pairIndex[key] || 0;
    pairIndex[key] = idx + 1;

    // 多条平行连线沿垂直方向错开，避免重叠
    let vertices: Array<{ x: number; y: number }> | undefined;
    if (total > 1) {
      const a = centers[link.localDevice];
      const b = centers[link.remoteDevice];
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = Math.hypot(dx, dy) || 1;
      const px = -dy / len;
      const py = dx / len;
      const offset = (idx - (total - 1) / 2) * 48;
      if (offset !== 0) {
        vertices = [{ x: mx + px * offset, y: my + py * offset }];
      }
    }

    return {
      id: `edge-${index}`,
      source: link.localDevice,
      target: link.remoteDevice,
      vertices,
      connector: { name: 'smooth' },
      attrs: {
        line: {
          stroke: 'var(--color-border-3)',
          strokeWidth: 1,
          targetMarker: null,
        },
      },
      labels: [
        portLabel(0.22, link.localPort),
        portLabel(0.78, link.remotePort),
      ],
    };
  });

  return { nodes, edges };
};

// XFlow 内部子组件：把图数据灌进画布，并支持点击切换激活的设备
const GraphLoader: React.FC<{ data: BuiltGraph }> = ({ data }) => {
  const initData = useGraphStore((state) => state.initData);
  const graph = useGraphInstance();

  useEffect(() => {
    ensureDeviceNodeRegistered();
    initData({ nodes: data.nodes, edges: data.edges });
  }, [initData, data]);

  // 点击设备节点：激活当前节点的蓝框高亮，其余节点恢复默认
  useEffect(() => {
    if (!graph) return;
    const handleNodeClick = ({ node }: { node: any }) => {
      graph.getNodes().forEach((cell) => {
        cell.setAttrs({
          body: cell.id === node.id ? ACTIVE_BODY_ATTRS : DEFAULT_BODY_ATTRS,
        });
      });
    };
    graph.on('node:click', handleNodeClick);
    return () => {
      graph.off('node:click', handleNodeClick);
    };
  }, [graph]);

  return null;
};

const TopologyGraphModal: React.FC<TopologyGraphModalProps> = ({
  open,
  onClose,
  links,
}) => {
  const { t } = useTranslation();

  const graphData = useMemo(
    () => buildGraphData(links || [], 'var(--color-text-4)'),
    [links]
  );

  const hasGraph = graphData.nodes.length > 0;

  return (
    <Modal
      title={t('Collection.taskDetail.topologyGraph')}
      open={open}
      onCancel={onClose}
      footer={null}
      width="80vw"
      destroyOnClose
      styles={{ body: { padding: 0 } }}
    >
      <div style={{ height: '72vh', position: 'relative' }}>
        {hasGraph ? (
          <XFlow>
            <XFlowGraph
              zoomable
              pannable
              minScale={0.2}
              maxScale={4}
              fitView
            />
            <Grid type="dot" options={{ color: '#ccc', thickness: 1 }} />
            <Minimap
              width={200}
              height={120}
              style={{
                border: '1px solid var(--color-border-3)',
                bottom: '10px',
                right: '10px',
                position: 'absolute',
              }}
            />
            <GraphLoader data={graphData} />
          </XFlow>
        ) : (
          <div className="flex items-center justify-center h-full">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('Collection.taskDetail.noTopologyGraph')}
            />
          </div>
        )}
      </div>
    </Modal>
  );
};

export default TopologyGraphModal;
