import type { Meta, StoryObj } from '@storybook/nextjs';
import DiffReportCard from '@/app/opspilot/components/custom-chat-sse/DiffReportCard';

const meta: Meta<typeof DiffReportCard> = {
  component: DiffReportCard,
  title: 'OpsPilot/DiffReportCard',
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#f5f5f5' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof DiffReportCard>;

const report = {
  report_id: 'report-1',
  title: 'Kubernetes Config Fix Preview',
  cluster_name: 'prod-cluster',
  received_at: Date.now(),
  items: [
    {
      workload_name: 'nginx-web',
      workload_type: 'Deployment',
      namespace: 'default',
      severity: 'high' as const,
      summary: 'Add resource requests and limits for container nginx.',
      before_yaml: `resources: {}`,
      after_yaml: `resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi`,
    },
    {
      workload_name: 'worker-job',
      workload_type: 'StatefulSet',
      namespace: 'ops',
      severity: 'warning' as const,
      summary: 'Add a readiness probe to avoid routing traffic too early.',
      before_yaml: `readinessProbe: null`,
      after_yaml: `readinessProbe:
  tcpSocket:
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10`,
    },
  ],
};

export const Default: Story = {
  args: {
    report,
  },
};

export const CriticalOnly: Story = {
  args: {
    report: {
      ...report,
      items: [
        {
          workload_name: 'privileged-agent',
          workload_type: 'DaemonSet',
          namespace: 'security',
          severity: 'critical',
          summary: 'Disable privileged mode and host PID usage.',
          before_yaml: `securityContext:
  privileged: true
hostPID: true`,
          after_yaml: `securityContext:
  privileged: false
hostPID: false`,
        },
      ],
    },
  },
};
