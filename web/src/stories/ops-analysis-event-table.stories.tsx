import type { Meta, StoryObj } from '@storybook/nextjs';
import EventTable from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/eventTable/eventTable';
import { EventTableDetail } from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/eventTable/eventTableDetail';

const baseConfig = {
  tableConfig: {
    columns: [
      {
        key: 'timestamp',
        title: 'timestamp',
        visible: true,
        order: 0,
        width: 180,
      },
      {
        key: 'message',
        title: 'message',
        visible: true,
        order: 1,
        width: 420,
      },
      {
        key: 'metadataBeat',
        title: '@metadata.beat',
        visible: true,
        order: 2,
        width: 160,
      },
      {
        key: 'metadataType',
        title: '@metadata.type',
        visible: true,
        order: 3,
        width: 150,
      },
      {
        key: 'metadataVersion',
        title: '@metadata.version',
        visible: true,
        order: 4,
        width: 150,
      },
    ],
    filterFields: [],
  },
};

const meta: Meta<typeof EventTable> = {
  title: 'OpsAnalysis/Widgets/EventTable',
  component: EventTable,
  parameters: {
    layout: 'fullscreen',
  },
  render: (args) => (
    <div
      style={{
        minHeight: '100vh',
        padding: 24,
        background: 'linear-gradient(180deg, #f6f8fb 0%, #edf3fb 100%)',
      }}
    >
      <div
        style={{
          height: 560,
          width: '100%',
          border: '1px solid #dbe5f0',
          borderRadius: 16,
          padding: 16,
          background: '#ffffff',
          boxShadow: '0 18px 40px rgba(15, 23, 42, 0.08)',
        }}
      >
        <EventTable {...args} />
      </div>
    </div>
  ),
};

export default meta;

type Story = StoryObj<typeof EventTable>;

export const DefaultEvents: Story = {
  args: {
    config: baseConfig,
    rawData: [
      {
        timestamp: '2026-06-04 17:30:20',
        message:
          'missing _msg field; see https://docs.victoriametrics.com/victorialogs/keyconcepts/#message-field',
        metadataBeat: 'packetbeat',
        metadataType: '_doc',
        metadataVersion: '9.1.5',
        streamId: '0000000000000000c9b159bc866d5c1f143329f9562e3fd0',
        time: '2026-06-04T09:30:20.010Z',
        sourceType: 'logstash',
        instanceId: 'Packetbeat-icmp-d95291a4-b502-418c-89f5-67c78e91a31a',
      },
      {
        timestamp: '2026-06-04 17:29:51',
        message: 'icmp probe completed with missing mapped message field',
        metadataBeat: 'packetbeat',
        metadataType: '_doc',
        metadataVersion: '9.1.5',
        streamId: '0000000000000000c9b159bc866d5c1f143329f9562e3fd1',
        time: '2026-06-04T09:29:51.010Z',
        sourceType: 'logstash',
        instanceId: 'Packetbeat-icmp-d95291a4-b502-418c-89f5-67c78e91a31b',
      },
    ],
  },
};

export const PaginatedEvents: Story = {
  args: {
    config: baseConfig,
    rawData: {
      count: 42,
      items: [
        {
          timestamp: '2026-06-04T10:00:00Z',
          message: 'Abnormal login burst detected from a new ASN',
          metadataBeat: 'gateway',
          metadataType: '_doc',
          metadataVersion: '9.1.5',
          severity: 'high',
          request_id: 'req-0011223344',
        },
        {
          timestamp: '2026-06-04T09:58:00Z',
          message: 'Canary batch completed and traffic shifted to 25%',
          metadataBeat: 'release-controller',
          metadataType: '_doc',
          metadataVersion: '9.1.5',
          severity: 'info',
          release_id: 'rel-20260604-2',
        },
      ],
    },
  },
};

export const LongSummary: Story = {
  args: {
    config: baseConfig,
    rawData: [
      {
        timestamp: '2026-06-04T10:00:00Z',
        message:
          'This is an intentionally long event summary to verify truncation in table cells while keeping the full payload visible inside the expanded detail area. '.repeat(
            4,
          ),
        metadataBeat: 'policy-center',
        metadataType: '_doc',
        metadataVersion: '9.1.5',
        operator: 'system',
        scope: 'cluster-prod-a',
      },
    ],
  },
};

export const EmptyData: Story = {
  args: {
    config: baseConfig,
    rawData: [],
  },
};

export const ExpandedDetailPanel: Story = {
  render: () => (
    <div
      style={{
        minHeight: '100vh',
        padding: 24,
        background: 'linear-gradient(180deg, #f6f8fb 0%, #edf3fb 100%)',
      }}
    >
      <div
        style={{
          maxWidth: 1320,
          border: '1px solid #dbe5f0',
          borderRadius: 16,
          overflow: 'hidden',
          background: '#ffffff',
          boxShadow: '0 18px 40px rgba(15, 23, 42, 0.08)',
        }}
      >
        <EventTableDetail
          record={{
            timestamp: '2026-06-04T09:30:20.010Z',
            message:
              'missing _msg field; see https://docs.victoriametrics.com/victorialogs/keyconcepts/#message-field',
            metadataBeat: 'packetbeat',
            metadataType: '_doc',
            metadataVersion: '9.1.5',
            stream:
              '{instance_id="Packetbeat-icmp-d95291a4-b502-418c-89f5-67c78e91a31a",source_type="logstash"}',
            streamId: '0000000000000000c9b159bc866d5c1f143329f9562e3fd0',
            time: '2026-06-04T09:30:20.010Z',
            agentEphemeralId: '4bf72560-20d8-4805-8364-7505bf8e48d6',
            agentId: '78d82b91-8ce1-420d-8825-b776dac39940',
          }}
        />
      </div>
    </div>
  ),
};
