import type { Meta, StoryObj } from '@storybook/react';
import ComGauge from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comGauge';
import ComMessage from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comMessage';

const gaugeMeta: Meta<typeof ComGauge> = {
  title: 'OpsAnalysis/Widgets/Gauge',
  component: ComGauge,
  parameters: {
    layout: 'padded',
  },
  render: (args) => (
    <div
      style={{
        height: 300,
        width: '100%',
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        padding: 8,
      }}
    >
      <ComGauge {...args} />
    </div>
  ),
};

export default gaugeMeta;

type GaugeStory = StoryObj<typeof ComGauge>;

export const GaugeDefault: GaugeStory = {
  args: {
    rawData: {
      cpu_usage: 73.4,
    },
    config: {
      selectedFields: ['cpu_usage'],
      unit: '%',
      gaugeMin: 0,
      gaugeMax: 100,
      gaugeShape: 'semicircle',
      thresholdColors: [
        { value: '60', color: '#2dcb56' },
        { value: '80', color: '#ff9c01' },
        { value: '90', color: '#ea3536' },
      ],
    },
  },
};

export const GaugeCircle: GaugeStory = {
  args: {
    rawData: {
      latency: 286,
    },
    config: {
      selectedFields: ['latency'],
      unit: 'ms',
      gaugeMin: 0,
      gaugeMax: 500,
      gaugeShape: 'circle',
      thresholdColors: [
        { value: '200', color: '#2dcb56' },
        { value: '350', color: '#ff9c01' },
        { value: '450', color: '#ea3536' },
      ],
    },
  },
};

export const GaugeEmpty: GaugeStory = {
  args: {
    rawData: {},
    config: {
      selectedFields: ['cpu_usage'],
      gaugeMin: 0,
      gaugeMax: 100,
      gaugeShape: 'semicircle',
    },
  },
};

export const MessageTable: StoryObj<typeof ComMessage> = {
  name: 'Message Default',
  render: (args) => (
    <div
      style={{
        height: 340,
        width: '100%',
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        padding: 8,
      }}
    >
      <ComMessage {...args} />
    </div>
  ),
  args: {
    rawData: [
      {
        event_time: '2026-01-04T14:23:10Z',
        level: 'info',
        source: 'node-exporter',
        message: 'Disk usage collection completed',
      },
      {
        event_time: '2026-01-04T14:20:03Z',
        level: 'warning',
        source: 'collector-agent',
        message: 'Response time increased to 420ms',
      },
      {
        event_time: '2026-01-04T14:15:45Z',
        level: 'error',
        source: 'api-gateway',
        message: 'NATS publish failed: timeout',
      },
      {
        event_time: '2026-01-04T14:11:09Z',
        level: 'critical',
        source: 'node-manager',
        message: 'Collector heartbeat missing for 5 minutes',
      },
    ],
  },
};

export const MessageWrappedItems: StoryObj<typeof ComMessage> = {
  name: 'Message Wrapped Items',
  render: (args) => (
    <div
      style={{
        height: 340,
        width: '100%',
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        padding: 8,
      }}
    >
      <ComMessage {...args} />
    </div>
  ),
  args: {
    rawData: {
      items: [
        {
          time: '2026-01-04T10:00:00Z',
          severity: 'warn',
          service_name: 'monitor',
          content: 'CPU threshold exceeded',
        },
        {
          time: '2026-01-04T09:58:00Z',
          severity: 'info',
          service_name: 'monitor',
          content: 'Recovered to normal range',
        },
      ],
    },
  },
};
