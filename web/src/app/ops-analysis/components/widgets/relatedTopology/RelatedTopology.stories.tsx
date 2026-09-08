import type { Meta, StoryObj } from '@storybook/nextjs';
import { Empty } from 'antd';
import RelatedTopologyGraphView from './graphView';
import { buildRelatedTopologyGraph } from './graphModel';
import type { RelatedTopologyResponse } from './types';

const CENTER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const NEIGHBOR = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const noisyCenter: RelatedTopologyResponse = {
  center_inst_uuid: CENTER,
  src_result: {
    inst_uuid: CENTER,
    inst_name: 'core-host',
    model_id: 'host',
    model_name: '主机',
    monitor_id: 'mon-center',
    alert_count: 12,
    max_level: 'error',
    children: [
      {
        inst_uuid: NEIGHBOR,
        inst_name: 'edge-switch',
        model_id: 'switch',
        model_name: '交换机',
        asst_name: '连接',
        monitor_id: '',
        alert_count: null,
        max_level: null,
        children: [],
      },
    ],
  },
  dst_result: {
    inst_uuid: CENTER,
    inst_name: 'core-host',
    model_id: 'host',
    children: [],
  },
};

const emptyGraph: RelatedTopologyResponse = {
  center_inst_uuid: CENTER,
  src_result: {
    inst_uuid: CENTER,
    inst_name: 'core-host',
    model_id: 'host',
    children: [],
  },
  dst_result: {
    inst_uuid: CENTER,
    inst_name: 'core-host',
    model_id: 'host',
    children: [],
  },
};

const meta: Meta = {
  title: 'ops-analysis/RelatedTopology',
};

export default meta;

export const WithNeighborBadge: StoryObj = {
  render: () => (
    <div className="h-[420px] w-full">
      <RelatedTopologyGraphView model={buildRelatedTopologyGraph(noisyCenter)} />
    </div>
  ),
};

export const EmptyAssociations: StoryObj = {
  render: () => (
    <div className="flex h-[280px] items-center justify-center">
      <Empty description="暂无关联" />
    </div>
  ),
};

export const QuietMappedCenter: StoryObj = {
  render: () => (
    <div className="h-[420px] w-full">
      <RelatedTopologyGraphView
        model={buildRelatedTopologyGraph({
          ...emptyGraph,
          src_result: {
            ...emptyGraph.src_result,
            monitor_id: 'mon-center',
            alert_count: 0,
            max_level: null,
          },
        })}
      />
    </div>
  ),
};
