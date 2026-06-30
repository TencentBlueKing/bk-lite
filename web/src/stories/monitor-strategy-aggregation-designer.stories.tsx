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

const metricKindLabels: Record<MetricKind, string> = {
  gauge: '瞬时值',
  state: '状态',
  delta: '增量',
  inventory: '清单',
};

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
    label: '平均值',
    summary: '观察窗口内的整体水平。',
    category: '趋势数值',
    fit: '适合使用率、延迟、负载',
  },
  {
    key: 'max',
    tag: 'MAX',
    label: '最大值',
    summary: '观察窗口内出现过的最高值。',
    category: '趋势数值',
    fit: '适合磁盘使用率、队列、错误率',
  },
  {
    key: 'min',
    tag: 'MIN',
    label: '最小值',
    summary: '观察窗口内出现过的最低值。',
    category: '趋势数值',
    fit: '适合可用率、健康分、剩余容量',
  },
  {
    key: 'sum',
    tag: 'SUM',
    label: '累计值',
    summary: '把窗口内每个分组采样值累加。',
    category: '增量累计',
    fit: '适合每周期增量指标',
    caution: 'SUM 通常不适合瞬时值指标，因为累计结果会受采样频率影响。',
  },
  {
    key: 'count',
    tag: 'COUNT',
    label: '有效数量',
    summary: '统计窗口内仍有数据的序列数量。',
    category: '存在性统计',
    fit: '适合接口、磁盘、进程数量',
  },
  {
    key: 'last',
    tag: 'LAST',
    label: '最近值',
    summary: '取窗口内最近一次有效状态值。',
    category: '状态快照',
    fit: '适合状态、枚举、up/down 指标',
  },
];

const metrics: MetricDefinition[] = [
  {
    key: 'disk',
    name: '磁盘使用率',
    kind: 'gauge',
    metricName: 'disk_used_percent',
    description: '同一实例下多块磁盘上报的数值型瞬时值指标。',
    defaultMethod: 'max',
    defaultGroups: ['instance_id'],
    groupOptions: ['instance_id', 'disk', 'mountpoint'],
    recommendation: '推荐：容量风险优先用 MAX；观察整体水平可用 AVG。',
    scenario: {
      avg: '实例 A 有 4 块磁盘。每个时刻先按实例求磁盘平均值，再计算最近 5 分钟内这些实例级值的平均值。',
      max: '实例 A 有 4 块磁盘。每个时刻先找出该实例最满的磁盘，再取最近 5 分钟内最危险的一次。',
      min: '实例 A 有 4 块磁盘。每个时刻先找出该实例最低的磁盘值，再取最近 5 分钟内最低的一次。',
      sum: '磁盘使用率是瞬时值指标。把多个采样百分比累加后很难解释，因此这里不建议使用 SUM。',
      count: '统计最近 5 分钟内每个分组下仍有上报数据的磁盘序列数量。',
      last: '展示窗口内最近一次磁盘使用率采样值。容量类告警通常不如 AVG 或 MAX 直观。',
    },
  },
  {
    key: 'interface_status',
    name: '接口状态',
    kind: 'state',
    metricName: 'interface_oper_status',
    description: '状态型指标，1 表示 up，0 表示 down。',
    defaultMethod: 'last',
    defaultGroups: ['instance_id', 'interface'],
    groupOptions: ['instance_id', 'interface', 'admin_status'],
    recommendation: '推荐：使用 LAST，并按 instance_id + interface 分组，得到每个接口一条状态。',
    scenario: {
      avg: '接口状态被平均后会模糊语义，例如 5 分钟平均值 0.6 很难直接指导处置。',
      max: 'MAX 可以表示窗口内是否曾经 up，但会掩盖最近状态。',
      min: 'MIN 可以表示窗口内是否曾经 down，但不能回答当前最近状态。',
      sum: '状态值求和会受采样次数影响，不适合作为最终状态。',
      count: '统计最近 5 分钟内有状态数据上报的接口数量。',
      last: '交换机 A 有 10 个接口，最近状态 3 个 down、7 个 up，结果会输出 10 条按接口分组的状态序列。',
    },
  },
  {
    key: 'request_delta',
    name: '请求增量',
    kind: 'delta',
    metricName: 'request_count_per_minute',
    description: '每个采样点已经表示该采集周期内新增的请求数。',
    defaultMethod: 'sum',
    defaultGroups: ['service'],
    groupOptions: ['service', 'instance_id', 'route'],
    recommendation: '推荐：周期总量用 SUM；突增检测可用 MAX。',
    scenario: {
      avg: '展示最近 5 分钟内每个采样增量的平均水平。',
      max: '展示最近 5 分钟内最大的单次采样增量。',
      min: '展示最近 5 分钟内最低的单次采样增量。',
      sum: '把最近 5 分钟内每分钟请求增量相加，得到周期总请求数。',
      count: '统计最近 5 分钟内仍有数据上报的请求序列数量。',
      last: '只展示最近一次采样增量，不代表 5 分钟总量。',
    },
  },
  {
    key: 'interface_inventory',
    name: '接口清单',
    kind: 'inventory',
    metricName: 'interface_info',
    description: '存在性指标，用于判断哪些接口序列仍然存在。',
    defaultMethod: 'count',
    defaultGroups: ['instance_id'],
    groupOptions: ['instance_id', 'interface', 'vendor'],
    recommendation: '推荐：使用 COUNT 发现序列缺失或清单变化。',
    scenario: {
      avg: '清单标记值做平均通常没有明确业务含义。',
      max: '清单标记值取 MAX 只能说明至少存在一个标记。',
      min: '清单标记值取 MIN 很少适用于清单检查。',
      sum: '只有所有标记值都严格为 1 时，SUM 才近似数量；但 COUNT 语义更清楚。',
      count: '统计最近 5 分钟内每个实例仍有数据的接口序列数量。',
      last: '展示最近一次标记值。只有标记值本身携带状态时才有意义。',
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
      ? `count(last_over_time(metric[${period}])) by (group_by)\n\n示例:\ncount(last_over_time(${metricName}[${period}])) by (${groups.join(', ')})`
      : `count(last_over_time(${metricName}[${period}]))`;
  }

  if (method === 'last') {
    return groups.length
      ? `any(last_over_time(metric[${period}])) by (group_by)\n\n示例:\nany(last_over_time(${metricName}[${period}])) by (${groups.join(', ')})`
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
  return `${outer}((${inner}(metric) by (${groupToken}))[${period}:${resolution}])\n\n示例:\n${outer}((${inner}(${metricName})${groupClause})[${period}:${resolution}])`;
};

const getPeriodLabel = (period: string) => {
  const periodLabels: Record<string, string> = {
    '5m': '5 分钟',
    '10m': '10 分钟',
    '30m': '30 分钟',
  };
  return periodLabels[period] || period;
};

const getSteps = (method: MethodDefinition, metric: MetricDefinition, groups: string[], period: string) => [
  `按 ${groups.join(' + ') || '全部序列'} 分组，确定最终告警对象。`,
  `汇聚周期是观察窗口：每次判断向前查看最近 ${getPeriodLabel(period)} 的数据。`,
  `使用${method.label}为每个分组计算阈值判断值。`,
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
                {recommended && <Badge status="success" text="推荐" />}
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
        <Text strong>场景预览</Text>
      </Space>
      <Text>{metric.scenario[method.key]}</Text>
      {method.key === 'sum' && metric.kind === 'gauge' && (
        <Alert
          type="warning"
          showIcon
          message="瞬时值指标提示"
          description="SUM 通常不适合瞬时值指标，因为累计结果会随采样频率变化。"
        />
      )}
      {method.key === 'last' && (
        <Alert
          type="info"
          showIcon
          message="状态分组提示"
          description="状态类指标需要选择足够的分组维度来识别状态对象。接口状态通常需要 instance_id 和 interface。"
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
        <Text strong>方法推荐</Text>
      </Space>
      <Text>{metric.recommendation}</Text>
      <Space wrap>
        <Tag color="blue">指标类型: {metricKindLabels[metric.kind]}</Tag>
        <Tag color="green">默认方法: {getMethod(metric.defaultMethod).tag}</Tag>
        <Tag color="orange">子查询分辨率: 自动，示例 1m</Tag>
      </Space>
    </Space>
  </div>
);

const MethodComparisonPanel = ({ metric }: { metric: MetricDefinition }) => (
  <div style={sectionStyle}>
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      <Space>
        <ApartmentOutlined style={{ color: '#7c3aed' }} />
        <Text strong>方法对比</Text>
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
          <Title level={3} style={{ margin: 0 }}>策略汇聚方式设计器</Title>
          <Text type="secondary">
            用“告警对象、观察窗口、计算方法”的方式配置策略，不要求用户先理解底层 PromQL 函数名。
          </Text>
        </Space>
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <section style={sectionStyle}>
            <Space direction="vertical" size={18} style={{ width: '100%' }}>
              <Space>
                <ApartmentOutlined style={{ color: '#1677ff' }} />
                <Text strong>配置</Text>
              </Space>

              <div>
                <Text strong>指标</Text>
                <Select
                  value={metricKey}
                  onChange={handleMetricChange}
                  style={{ width: '100%', marginTop: 8 }}
                  options={metrics.map((item) => ({
                    label: `${item.name}（${metricKindLabels[item.kind]}）`,
                    value: item.key,
                  }))}
                />
                <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                  {metric.description}
                </Text>
              </div>

              <div>
                <Text strong>分组维度</Text>
                <Select
                  mode="multiple"
                  value={groups}
                  onChange={setGroups}
                  style={{ width: '100%', marginTop: 8 }}
                  options={metric.groupOptions.map((item) => ({ label: item, value: item }))}
                />
                <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                  分组维度决定哪些对象会被独立判断并产生告警。
                </Text>
              </div>

              <div>
                <Text strong>汇聚周期</Text>
                <Radio.Group
                  value={period}
                  onChange={(event) => setPeriod(event.target.value)}
                  style={{ display: 'block', marginTop: 8 }}
                >
                  <Radio.Button value="5m">5 分钟</Radio.Button>
                  <Radio.Button value="10m">10 分钟</Radio.Button>
                  <Radio.Button value="30m">30 分钟</Radio.Button>
                </Radio.Group>
                <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                  汇聚周期是观察窗口，不是策略扫描频率。
                </Text>
              </div>

              <Divider style={{ margin: 0 }} />

              <div>
                <Text strong>汇聚方法</Text>
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
                <Text strong>计算说明</Text>
              </Space>
              <Row gutter={[12, 12]}>
                {steps.map((step, index) => (
                  <Col xs={24} md={8} key={step}>
                    <div style={{ border: '1px solid #e1e7f0', borderRadius: 8, padding: 12, minHeight: 104 }}>
                      <Tag color="blue">第 {index + 1} 步</Tag>
                      <div style={{ marginTop: 8 }}>{step}</div>
                    </div>
                  </Col>
                ))}
              </Row>
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <CodeOutlined style={{ color: '#475569' }} />
                  <Text strong>高级查询语义</Text>
                </Space>
                <code style={codeStyle}>{query}</code>
                <Text type="secondary" style={{ display: 'block', marginTop: 8, wordBreak: 'break-word' }}>
                  参考形式：{referenceQueries.join(' | ')}
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
