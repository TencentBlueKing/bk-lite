import type { Meta, StoryObj } from '@storybook/nextjs';
import ComGauge from '@/app/ops-analysis/components/widgets/comGauge';

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
