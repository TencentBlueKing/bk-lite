import type { Meta, StoryObj } from '@storybook/nextjs';
import ConfigAnalysisReportCard from '@/app/opspilot/components/custom-chat-sse/ConfigAnalysisReportCard';
import type { ConfigAnalysisReport } from '@/app/opspilot/types/global';

const report: ConfigAnalysisReport = {
  report_id: 'analysis-001',
  title: 'Kubernetes Workload Configuration Analysis',
  cluster_name: 'bk-lite-prod',
  scope: {
    cluster_name: 'bk-lite-prod',
    namespace: 'monitoring',
    target_name: 'Deployment',
  },
  scan_range: {
    offset: 0,
    limit: 25,
    has_more: true,
  },
  summary: {
    total: 48,
    problematic: 11,
    healthy: 37,
    top_recommendation: '优先补齐高风险工作负载的探针和资源限制，降低发布后不可用风险。',
  },
  severity_sections: [
    {
      severity: 'high',
      title: '探针配置缺失',
      issues: [
        {
          issue: '未配置 readinessProbe',
          count: 6,
          workloads: [
            'api-gateway',
            'alert-worker',
            'event-collector',
            'log-processor',
            'cmdb-sync',
            'node-agent',
          ],
          risk: '服务启动或异常恢复期间可能提前接流量，造成请求失败。',
        },
      ],
    },
    {
      severity: 'medium',
      title: '资源限制不完整',
      issues: [
        {
          issue: '未设置 memory limit',
          count: 5,
          workloads: ['dashboard-api', 'ops-console', 'rule-engine'],
          risk: '负载突增时可能影响同节点其他服务稳定性。',
        },
      ],
    },
  ],
  recommendations: [
    {
      priority: 'P1',
      action: '为高流量服务添加 readinessProbe 和 livenessProbe',
      target: 'monitoring namespace',
      benefit: '提升滚动发布和故障恢复期间的流量保护能力。',
    },
    {
      priority: 'P2',
      action: '补齐关键容器的 memory limit',
      target: 'worker workloads',
      benefit: '降低资源争用导致的节点级抖动。',
    },
  ],
  markdown: '',
  fallback_markdown: '',
  received_at: Date.now(),
};

const healthyReport: ConfigAnalysisReport = {
  ...report,
  report_id: 'analysis-healthy',
  title: 'Healthy Scan Result',
  summary: {
    total: 16,
    problematic: 0,
    healthy: 16,
    top_recommendation: '',
  },
  severity_sections: [],
  recommendations: [],
};

const meta = {
  title: 'OpsPilot/ConfigAnalysisReportCard',
  component: ConfigAnalysisReportCard,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 980, padding: 16, background: '#f8fafc' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ConfigAnalysisReportCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithIssues: Story = {
  args: {
    report,
  },
};

export const Healthy: Story = {
  args: {
    report: healthyReport,
  },
};
