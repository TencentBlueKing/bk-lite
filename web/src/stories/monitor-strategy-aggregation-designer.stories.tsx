import type { Meta, StoryObj } from '@storybook/nextjs';
import { useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Col,
  Divider,
  Radio,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import {
  ApartmentOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';

const { Text, Title } = Typography;

type MethodKey = 'avg' | 'max' | 'min' | 'sum' | 'count' | 'last';
type MetricKey = 'disk' | 'interface_status' | 'request_delta' | 'interface_inventory';
type MetricKind = 'gauge' | 'state' | 'delta' | 'inventory';

interface MethodDefinition {
  key: MethodKey;
  tag: string;
  label: string;
  summary: string;
  category: string;
  fit: string;
  caution?: string;
}

interface MetricDefinition {
  key: MetricKey;
  name: string;
  kind: MetricKind;
  metricName: string;
  description: string;
  defaultMethod: MethodKey;
  defaultGroups: string[];
  groupOptions: string[];
  recommendation: string;
  scenario: Record<MethodKey, string>;
}

const methods: MethodDefinition[] = [
  {
    key: 'avg',
    tag: 'AVG',
    label: 'Average',
    summary: 'Typical level across the observation window.',
    category: 'Numeric trend',
    fit: 'Usage, latency, load',
  },
  {
    key: 'max',
    tag: 'MAX',
    label: 'Maximum',
    summary: 'Worst high value across the observation window.',
    category: 'Numeric trend',
    fit: 'Disk usage, queues, error rate',
  },
  {
    key: 'min',
    tag: 'MIN',
    label: 'Minimum',
    summary: 'Worst low value across the observation window.',
    category: 'Numeric trend',
    fit: 'Availability, health score, remaining capacity',
  },
  {
    key: 'sum',
    tag: 'SUM',
    label: 'Accumulated',
    summary: 'Adds each grouped sample inside the window.',
    category: 'Delta amount',
    fit: 'Per-period increments',
    caution: 'SUM is usually not appropriate for gauge metrics because the result depends on sampling frequency.',
  },
  {
    key: 'count',
    tag: 'COUNT',
    label: 'Valid count',
    summary: 'Counts series that still have data in the window.',
    category: 'Presence',
    fit: 'Interface, disk, process inventory',
  },
  {
    key: 'last',
    tag: 'LAST',
    label: 'Latest value',
    summary: 'Uses the latest valid state in the window.',
    category: 'State snapshot',
    fit: 'Status, enum, up/down metrics',
  },
];

const metrics: MetricDefinition[] = [
  {
    key: 'disk',
    name: 'Disk usage',
    kind: 'gauge',
    metricName: 'disk_used_percent',
    description: 'Numeric gauge from multiple disks on the same instance.',
    defaultMethod: 'max',
    defaultGroups: ['instance_id'],
    groupOptions: ['instance_id', 'disk', 'mountpoint'],
    recommendation: 'Recommended: MAX for capacity risk, AVG for overall level.',
    scenario: {
      avg: 'Instance A has 4 disks. Each moment first averages disks by instance, then averages those instance values across the latest 5 minutes.',
      max: 'Instance A has 4 disks. Each moment first finds the fullest disk per instance, then keeps the worst value from the latest 5 minutes.',
      min: 'Instance A has 4 disks. Each moment first finds the lowest disk value per instance, then keeps the lowest value from the latest 5 minutes.',
      sum: 'Disk usage is a gauge. Accumulating sampled percentages is usually hard to explain, so SUM should be avoided here.',
      count: 'Counts how many disk series still reported data in the latest 5 minutes for each selected group.',
      last: 'Shows the latest sampled disk usage in the window. This is less useful than AVG or MAX for capacity alerts.',
    },
  },
  {
    key: 'interface_status',
    name: 'Interface status',
    kind: 'state',
    metricName: 'interface_oper_status',
    description: 'State metric where 1 means up and 0 means down.',
    defaultMethod: 'last',
    defaultGroups: ['instance_id', 'interface'],
    groupOptions: ['instance_id', 'interface', 'admin_status'],
    recommendation: 'Recommended: LAST. Group by instance_id and interface to get one status per port.',
    scenario: {
      avg: 'Averaging interface status can blur state. A 5 minute average of 0.6 is not a clear operator action.',
      max: 'MAX can tell whether an interface was ever up in the window, but it hides the latest state.',
      min: 'MIN can tell whether an interface was ever down in the window, but it does not answer the current state.',
      sum: 'SUM of states depends on sample count and should not be used as a status result.',
      count: 'Counts how many interfaces reported any status data in the latest 5 minutes.',
      last: 'Switch A has 10 interfaces. 3 latest values are down and 7 are up, so the result shows 10 interface-level status series.',
    },
  },
  {
    key: 'request_delta',
    name: 'Request increment',
    kind: 'delta',
    metricName: 'request_count_per_minute',
    description: 'Each sample is already the requests added during its collection interval.',
    defaultMethod: 'sum',
    defaultGroups: ['service'],
    groupOptions: ['service', 'instance_id', 'route'],
    recommendation: 'Recommended: SUM for period totals, MAX for burst detection.',
    scenario: {
      avg: 'Shows the average per-sample request increment inside the latest 5 minutes.',
      max: 'Shows the largest per-sample request increment inside the latest 5 minutes.',
      min: 'Shows the lowest per-sample request increment inside the latest 5 minutes.',
      sum: 'Adds each per-minute request increment inside the latest 5 minutes to produce the period total.',
      count: 'Counts how many request series still reported data in the latest 5 minutes.',
      last: 'Shows only the latest per-sample request increment, not the 5 minute total.',
    },
  },
  {
    key: 'interface_inventory',
    name: 'Interface inventory',
    kind: 'inventory',
    metricName: 'interface_info',
    description: 'Presence metric used to know which interface series still exist.',
    defaultMethod: 'count',
    defaultGroups: ['instance_id'],
    groupOptions: ['instance_id', 'interface', 'vendor'],
    recommendation: 'Recommended: COUNT to detect missing or changed series inventory.',
    scenario: {
      avg: 'Averaging inventory marker values usually has no business meaning.',
      max: 'MAX of inventory marker values only says whether at least one marker exists.',
      min: 'MIN of inventory marker values is rarely useful for inventory checks.',
      sum: 'SUM can resemble count only when all marker values are exactly 1, but COUNT is clearer.',
      count: 'Counts interfaces that still had data during the latest 5 minutes for each instance.',
      last: 'Shows the latest marker value. This is useful only when the marker carries state.',
    },
  },
];

const referenceQueries = [
  'avg_over_time((avg(metric) by (group_by))[5m:1m])',
  'max_over_time((max(metric) by (group_by))[5m:1m])',
  'min_over_time((min(metric) by (group_by))[5m:1m])',
  'sum_over_time((sum(metric) by (group_by))[5m:1m])',
  'count(last_over_time(metric[5m])) by (group_by)',
  'any(last_over_time(metric[5m])) by (group_by)',
];

const pageStyle = {
  minHeight: 760,
  width: '100vw',
  maxWidth: '100%',
  boxSizing: 'border-box' as const,
  overflowX: 'hidden' as const,
  background: '#f5f7fb',
  padding: 24,
};

const sectionStyle = {
  border: '1px solid #dde3ee',
  borderRadius: 8,
  background: '#fff',
  padding: 18,
};

const methodButtonStyle = (active: boolean) => ({
  width: '100%',
  minHeight: 92,
  height: 'auto',
  padding: 12,
  textAlign: 'left' as const,
  borderColor: active ? '#1677ff' : '#d9e0ea',
  background: active ? '#eef6ff' : '#fff',
});

const codeStyle = {
  display: 'block',
  whiteSpace: 'pre-wrap' as const,
  wordBreak: 'break-word' as const,
  border: '1px solid #d8dee9',
  borderRadius: 6,
  background: '#111827',
  color: '#e5eefb',
  padding: 12,
  fontSize: 12,
  lineHeight: 1.6,
};

const getMethod = (key: MethodKey) => methods.find((method) => method.key === key) || methods[0];
const getMetric = (key: MetricKey) => metrics.find((metric) => metric.key === key) || metrics[0];

const getQuery = (
  method: MethodKey,
  metricName: string,
  groups: string[],
  period = '5m',
  resolution = '1m'
) => {
  const groupClause = groups.length ? ` by (${groups.join(', ')})` : '';
  const groupToken = groups.length ? 'group_by' : 'all_series';

  if (method === 'count') {
    return groups.length
      ? `count(last_over_time(metric[${period}])) by (group_by)\n\nExample:\ncount(last_over_time(${metricName}[${period}])) by (${groups.join(', ')})`
      : `count(last_over_time(${metricName}[${period}]))`;
  }

  if (method === 'last') {
    return groups.length
      ? `any(last_over_time(metric[${period}])) by (group_by)\n\nExample:\nany(last_over_time(${metricName}[${period}])) by (${groups.join(', ')})`
      : `last_over_time(${metricName}[${period}])`;
  }

  const outerMap: Record<Exclude<MethodKey, 'count' | 'last'>, string> = {
    avg: 'avg_over_time',
    max: 'max_over_time',
    min: 'min_over_time',
    sum: 'sum_over_time',
  };
  const innerMap: Record<Exclude<MethodKey, 'count' | 'last'>, string> = {
    avg: 'avg',
    max: 'max',
    min: 'min',
    sum: 'sum',
  };
  const outer = outerMap[method];
  const inner = innerMap[method];
  return `${outer}((${inner}(metric) by (${groupToken}))[${period}:${resolution}])\n\nExample:\n${outer}((${inner}(${metricName})${groupClause})[${period}:${resolution}])`;
};

const getSteps = (method: MethodDefinition, metric: MetricDefinition, groups: string[], period: string) => [
  `Group by ${groups.join(' + ') || 'all series'} to produce alert objects.`,
  `Aggregation period is the observation window: look back over the latest ${period}.`,
  `${method.label} calculates the threshold value for each ${metric.kind} result.`,
];

const MethodSelector = ({
  value,
  metric,
  onChange,
}: {
  value: MethodKey;
  metric: MetricDefinition;
  onChange: (value: MethodKey) => void;
}) => (
  <Row gutter={[10, 10]}>
    {methods.map((method) => {
      const active = value === method.key;
      const recommended = metric.defaultMethod === method.key;
      return (
        <Col span={12} key={method.key}>
          <Button style={methodButtonStyle(active)} onClick={() => onChange(method.key)}>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Space>
                <Text strong>{method.label}</Text>
                <Tag color={active ? 'blue' : 'default'}>{method.tag}</Tag>
                {recommended && <Badge status="success" text="Recommended" />}
              </Space>
              <Text type="secondary">{method.summary}</Text>
              <Text style={{ fontSize: 12, color: '#536173' }}>{method.fit}</Text>
            </Space>
          </Button>
        </Col>
      );
    })}
  </Row>
);

const ScenarioPreview = ({
  metric,
  method,
}: {
  metric: MetricDefinition;
  method: MethodDefinition;
}) => (
  <div style={sectionStyle}>
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space>
        <DatabaseOutlined style={{ color: '#1677ff' }} />
        <Text strong>Scenario preview</Text>
      </Space>
      <Text>{metric.scenario[method.key]}</Text>
      {method.key === 'sum' && metric.kind === 'gauge' && (
        <Alert
          type="warning"
          showIcon
          message="Gauge caution"
          description="SUM is usually not appropriate for gauge metrics because sampling frequency changes the accumulated result."
        />
      )}
      {method.key === 'last' && (
        <Alert
          type="info"
          showIcon
          message="State grouping tip"
          description="For status metrics, include enough dimensions to identify the state object. Interface status usually needs instance_id and interface."
        />
      )}
    </Space>
  </div>
);

const RecommendationPanel = ({ metric }: { metric: MetricDefinition }) => (
  <div style={sectionStyle}>
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space>
        <BarChartOutlined style={{ color: '#16a34a' }} />
        <Text strong>Method recommendation</Text>
      </Space>
      <Text>{metric.recommendation}</Text>
      <Space wrap>
        <Tag color="blue">Metric type: {metric.kind}</Tag>
        <Tag color="green">Default: {getMethod(metric.defaultMethod).tag}</Tag>
        <Tag color="orange">Resolution: auto, example 1m</Tag>
      </Space>
    </Space>
  </div>
);

const MethodComparisonPanel = ({ metric }: { metric: MetricDefinition }) => (
  <div style={sectionStyle}>
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      <Space>
        <ApartmentOutlined style={{ color: '#7c3aed' }} />
        <Text strong>Method comparison</Text>
      </Space>
      <Row gutter={[12, 12]}>
        {methods.map((method) => (
          <Col span={8} key={method.key}>
            <div
              style={{
                border: '1px solid #e1e7f0',
                borderRadius: 8,
                padding: 12,
                minHeight: 146,
                background: method.key === metric.defaultMethod ? '#f0fdf4' : '#fbfdff',
              }}
            >
              <Space direction="vertical" size={8}>
                <Space>
                  <Text strong>{method.label}</Text>
                  <Tag>{method.tag}</Tag>
                </Space>
                <Text type="secondary">{method.summary}</Text>
                <Text style={{ fontSize: 12 }}>{metric.scenario[method.key]}</Text>
              </Space>
            </div>
          </Col>
        ))}
      </Row>
    </Space>
  </div>
);

const AggregationDesigner = ({
  initialMetric = 'disk',
  initialMethod,
  comparison = false,
}: {
  initialMetric?: MetricKey;
  initialMethod?: MethodKey;
  comparison?: boolean;
}) => {
  const initialMetricDefinition = getMetric(initialMetric);
  const [metricKey, setMetricKey] = useState<MetricKey>(initialMetric);
  const [methodKey, setMethodKey] = useState<MethodKey>(initialMethod || initialMetricDefinition.defaultMethod);
  const [period, setPeriod] = useState('5m');
  const metric = getMetric(metricKey);
  const method = getMethod(methodKey);
  const [groups, setGroups] = useState<string[]>(initialMetricDefinition.defaultGroups);

  const steps = useMemo(() => getSteps(method, metric, groups, period), [method, metric, groups, period]);
  const query = useMemo(
    () => getQuery(method.key, metric.metricName, groups, period, '1m'),
    [method.key, metric.metricName, groups, period]
  );

  const handleMetricChange = (next: MetricKey) => {
    const nextMetric = getMetric(next);
    setMetricKey(next);
    setMethodKey(nextMetric.defaultMethod);
    setGroups(nextMetric.defaultGroups);
  };

  return (
    <>
    <style>
      {`
        html,
        body,
        #storybook-root,
        #storybook-highlights-root {
          width: 100vw !important;
          max-width: 100vw !important;
          overflow-x: hidden !important;
        }

        #storybook-root * {
          box-sizing: border-box;
        }
      `}
    </style>
    <div style={pageStyle}>
      <section style={{ ...sectionStyle, marginBottom: 16 }}>
        <Space direction="vertical" size={6}>
          <Title level={3} style={{ margin: 0 }}>Strategy aggregation designer</Title>
          <Text type="secondary">
            Configure alert object, observation window, and calculation method without forcing users to reason from raw PromQL names.
          </Text>
        </Space>
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <section style={sectionStyle}>
            <Space direction="vertical" size={18} style={{ width: '100%' }}>
              <Space>
                <ApartmentOutlined style={{ color: '#1677ff' }} />
                <Text strong>Configuration</Text>
              </Space>

              <div>
                <Text strong>Metric</Text>
                <Select
                  value={metricKey}
                  onChange={handleMetricChange}
                  style={{ width: '100%', marginTop: 8 }}
                  options={metrics.map((item) => ({
                    label: `${item.name} (${item.kind})`,
                    value: item.key,
                  }))}
                />
                <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                  {metric.description}
                </Text>
              </div>

              <div>
                <Text strong>Group dimensions</Text>
                <Select
                  mode="multiple"
                  value={groups}
                  onChange={setGroups}
                  style={{ width: '100%', marginTop: 8 }}
                  options={metric.groupOptions.map((item) => ({ label: item, value: item }))}
                />
                <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                  Group dimensions decide which objects are judged and alerted independently.
                </Text>
              </div>

              <div>
                <Text strong>Aggregation period</Text>
                <Radio.Group
                  value={period}
                  onChange={(event) => setPeriod(event.target.value)}
                  style={{ display: 'block', marginTop: 8 }}
                >
                  <Radio.Button value="5m">5 min</Radio.Button>
                  <Radio.Button value="10m">10 min</Radio.Button>
                  <Radio.Button value="30m">30 min</Radio.Button>
                </Radio.Group>
                <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                  Aggregation period is the observation window, not the scan frequency.
                </Text>
              </div>

              <Divider style={{ margin: 0 }} />

              <div>
                <Text strong>Aggregation method</Text>
                <div style={{ marginTop: 10 }}>
                  <MethodSelector value={methodKey} metric={metric} onChange={setMethodKey} />
                </div>
              </div>
            </Space>
          </section>
        </Col>

        <Col xs={24} xl={14}>
          <section style={sectionStyle}>
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Space>
                <ClockCircleOutlined style={{ color: '#1677ff' }} />
                <Text strong>Calculation explanation</Text>
              </Space>
              <Row gutter={[12, 12]}>
                {steps.map((step, index) => (
                  <Col xs={24} md={8} key={step}>
                    <div style={{ border: '1px solid #e1e7f0', borderRadius: 8, padding: 12, minHeight: 104 }}>
                      <Tag color="blue">Step {index + 1}</Tag>
                      <div style={{ marginTop: 8 }}>{step}</div>
                    </div>
                  </Col>
                ))}
              </Row>
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <CodeOutlined style={{ color: '#475569' }} />
                  <Text strong>Advanced query semantics</Text>
                </Space>
                <code style={codeStyle}>{query}</code>
                <Text type="secondary" style={{ display: 'block', marginTop: 8, wordBreak: 'break-word' }}>
                  Reference forms: {referenceQueries.join(' | ')}
                </Text>
              </div>
              {method.caution && <Alert type="warning" showIcon message={method.caution} />}
            </Space>
          </section>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={comparison ? 24 : 12}>
          {comparison ? <MethodComparisonPanel metric={metric} /> : <ScenarioPreview metric={metric} method={method} />}
        </Col>
        {!comparison && (
          <Col xs={24} xl={12}>
            <RecommendationPanel metric={metric} />
          </Col>
        )}
      </Row>
    </div>
    </>
  );
};

export const AggregationDesignerFrame = () => <AggregationDesigner />;

const meta: Meta<typeof AggregationDesignerFrame> = {
  title: 'Monitor/StrategyAggregationDesigner',
  component: AggregationDesignerFrame,
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;

type Story = StoryObj<typeof AggregationDesigner>;

export const DefaultNumericMetric: Story = {
  render: () => <AggregationDesigner initialMetric="disk" initialMethod="max" />,
};

export const InterfaceStatusLast: Story = {
  render: () => <AggregationDesigner initialMetric="interface_status" initialMethod="last" />,
};

export const DeltaCounterSum: Story = {
  render: () => <AggregationDesigner initialMetric="request_delta" initialMethod="sum" />,
};

export const MethodComparison: Story = {
  render: () => <AggregationDesigner initialMetric="disk" initialMethod="avg" comparison />,
};
