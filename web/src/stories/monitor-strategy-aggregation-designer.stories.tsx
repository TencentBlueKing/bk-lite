import type { Meta, StoryObj } from '@storybook/nextjs';
import { useMemo, useState } from 'react';
import {
  Alert,
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
  SwapOutlined,
} from '@ant-design/icons';

const { Text, Title } = Typography;

type GroupMethod = 'avg' | 'max' | 'min' | 'sum';
type WindowMethod =
  | 'avg_over_time'
  | 'max_over_time'
  | 'min_over_time'
  | 'sum_over_time'
  | 'count_over_time'
  | 'last_over_time';
type MetricKey = 'disk' | 'interface_status' | 'request_delta' | 'interface_inventory';
type MetricKind = '瞬时值' | '状态' | '增量' | '清单';

interface MetricDefinition {
  key: MetricKey;
  name: string;
  kind: MetricKind;
  metricName: string;
  description: string;
  defaultGroupMethod: GroupMethod;
  defaultWindowMethod: WindowMethod;
  defaultGroups: string[];
  groupOptions: string[];
  recommendation: string;
  scenario: string;
}

const groupMethods: Array<{ value: GroupMethod; label: string; help: string }> = [
  { value: 'avg', label: 'AVG', help: '先把同一分组下的多条序列求平均，默认：AVG' },
  { value: 'max', label: 'MAX', help: '先取同一分组下的最大值，适合先保留最危险子序列' },
  { value: 'min', label: 'MIN', help: '先取同一分组下的最小值，适合先保留最低健康值' },
  { value: 'sum', label: 'SUM', help: '先把同一分组下的序列求和，适合数量/容量叠加' },
];

const windowMethods: Array<{ value: WindowMethod; label: string; help: string }> = [
  { value: 'avg_over_time', label: 'AVG_OVER_TIME', help: '窗口内求平均，默认：AVG_OVER_TIME' },
  { value: 'max_over_time', label: 'MAX_OVER_TIME', help: '窗口内取最大值，适合峰值风险' },
  { value: 'min_over_time', label: 'MIN_OVER_TIME', help: '窗口内取最小值，适合低值风险' },
  { value: 'sum_over_time', label: 'SUM_OVER_TIME', help: '窗口内累加，适合增量总量' },
  { value: 'count_over_time', label: 'COUNT_OVER_TIME', help: '窗口内统计有效点/有效序列数量' },
  { value: 'last_over_time', label: 'LAST_OVER_TIME', help: '窗口内取最近有效值，适合状态类指标' },
];

const metrics: MetricDefinition[] = [
  {
    key: 'disk',
    name: '磁盘使用率',
    kind: '瞬时值',
    metricName: 'disk_used_percent',
    description: '同一实例下多块磁盘上报的数值型瞬时值指标。',
    defaultGroupMethod: 'avg',
    defaultWindowMethod: 'avg_over_time',
    defaultGroups: ['instance_id'],
    groupOptions: ['instance_id', 'disk', 'mountpoint'],
    recommendation: '默认双 AVG：先得到实例级平均磁盘使用率，再看最近一个汇聚周期内的平均水平。',
    scenario: '实例 A 有 4 块磁盘。分组聚合方式 AVG 会先把 4 块磁盘合成实例级序列；汇聚方式 AVG_OVER_TIME 再计算最近窗口内的平均值。',
  },
  {
    key: 'interface_status',
    name: '接口状态',
    kind: '状态',
    metricName: 'interface_oper_status',
    description: '状态型指标，1 表示 up，0 表示 down。',
    defaultGroupMethod: 'avg',
    defaultWindowMethod: 'last_over_time',
    defaultGroups: ['instance_id', 'interface'],
    groupOptions: ['instance_id', 'interface', 'admin_status'],
    recommendation: '状态类推荐 LAST_OVER_TIME。分组维度需要包含 interface，避免同一实例下多个接口状态被合并。',
    scenario: '交换机 A 有 10 个接口，最近状态 3 个 down、7 个 up。按 instance_id + interface 分组后，会输出 10 条接口状态序列。',
  },
  {
    key: 'request_delta',
    name: '请求增量',
    kind: '增量',
    metricName: 'request_count_per_minute',
    description: '每个采样点表示该采集周期内新增的请求数。',
    defaultGroupMethod: 'sum',
    defaultWindowMethod: 'sum_over_time',
    defaultGroups: ['service'],
    groupOptions: ['service', 'instance_id', 'route'],
    recommendation: '增量类推荐双 SUM：先按服务汇总各实例增量，再统计窗口内总量。',
    scenario: '服务 A 有多个实例。分组聚合方式 SUM 先合并实例增量；汇聚方式 SUM_OVER_TIME 再得到最近窗口内请求总量。',
  },
  {
    key: 'interface_inventory',
    name: '接口清单',
    kind: '清单',
    metricName: 'interface_info',
    description: '存在性指标，用于判断哪些接口序列仍然存在。',
    defaultGroupMethod: 'sum',
    defaultWindowMethod: 'count_over_time',
    defaultGroups: ['instance_id'],
    groupOptions: ['instance_id', 'interface', 'vendor'],
    recommendation: '清单类推荐分组 SUM + COUNT_OVER_TIME，用于统计窗口内有效接口序列数量。',
    scenario: '实例 A 下有多个接口序列。COUNT_OVER_TIME 统计窗口内仍然有效的数据点/序列，用于发现清单变化。',
  },
];

const migrationRows = [
  ['AVG / AVG_OVER_TIME', '分组聚合 AVG + 汇聚方式 AVG_OVER_TIME，简称双 AVG'],
  ['MAX / MAX_OVER_TIME', '分组聚合 MAX + 汇聚方式 MAX_OVER_TIME，简称双 MAX'],
  ['MIN / MIN_OVER_TIME', '分组聚合 MIN + 汇聚方式 MIN_OVER_TIME，简称双 MIN'],
  ['SUM / SUM_OVER_TIME', '分组聚合 SUM + 汇聚方式 SUM_OVER_TIME，简称双 SUM'],
  ['COUNT', '分组聚合 SUM + 汇聚方式 COUNT_OVER_TIME'],
  ['LAST_OVER_TIME', '分组聚合 AVG + 汇聚方式 LAST_OVER_TIME'],
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

const getMetric = (key: MetricKey) => metrics.find((metric) => metric.key === key) || metrics[0];

const getPeriodSeconds = (period: string) => {
  const matched = period.match(/^(\d+)(m|h|d)$/);
  if (!matched) return 300;
  const value = Number(matched[1]);
  const unit = matched[2];
  if (unit === 'h') return value * 3600;
  if (unit === 'd') return value * 86400;
  return value * 60;
};

const getStep = (period: string) => {
  const seconds = Math.max(1, Math.floor(getPeriodSeconds(period) / 30));
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
};

const getPeriodLabel = (period: string) => {
  const labels: Record<string, string> = {
    '5m': '5 分钟',
    '10m': '10 分钟',
    '30m': '30 分钟',
  };
  return labels[period] || period;
};

const getGroupLabel = (method: GroupMethod) =>
  groupMethods.find((item) => item.value === method)?.label || method.toUpperCase();

const getWindowLabel = (method: WindowMethod) =>
  windowMethods.find((item) => item.value === method)?.label || method.toUpperCase();

// 查询语义锚点，供 Storybook 合约测试锁定双层汇聚结构与 30 点 step 规则：
// avg_over_time((avg(metric) by (group_by))[5m:10s])
// count_over_time((sum(metric) by (group_by))[5m:10s])
// last_over_time((avg(metric) by (group_by))[5m:10s])
const getQuery = (
  groupMethod: GroupMethod,
  windowMethod: WindowMethod,
  metricName: string,
  groups: string[],
  period: string
) => {
  const groupToken = groups.length ? 'group_by' : 'all_series';
  const groupClause = groups.length ? ` by (${groups.join(', ')})` : '';
  const step = getStep(period);

  if (windowMethod === 'count_over_time') {
    return `count_over_time((${groupMethod}(metric) by (${groupToken}))[${period}:${step}])

示例:
count_over_time((${groupMethod}(${metricName})${groupClause})[${period}:${step}])`;
  }

  if (windowMethod === 'last_over_time') {
    return `last_over_time((${groupMethod}(metric) by (${groupToken}))[${period}:${step}])

示例:
last_over_time((${groupMethod}(${metricName})${groupClause})[${period}:${step}])`;
  }

  return `${windowMethod}((${groupMethod}(metric) by (${groupToken}))[${period}:${step}])

示例:
${windowMethod}((${groupMethod}(${metricName})${groupClause})[${period}:${step}])`;
};

const getSteps = (
  groupMethod: GroupMethod,
  windowMethod: WindowMethod,
  groups: string[],
  period: string
) => [
  `按 ${groups.join(' + ') || '全部序列'} 分组，确定最终告警对象。`,
  `先使用分组聚合方式 ${getGroupLabel(groupMethod)} 合并同一分组下未指定维度的数据。`,
  `再使用汇聚方式 ${getWindowLabel(windowMethod)} 分析最近 ${getPeriodLabel(period)} 的数据，step 自动按 30 个计算点生成。`,
];

const MethodSummary = ({
  groupMethod,
  windowMethod,
  period,
}: {
  groupMethod: GroupMethod;
  windowMethod: WindowMethod;
  period: string;
}) => (
  <Alert
    type="info"
    showIcon
    message={`当前语义：分组 ${getGroupLabel(groupMethod)} + 窗口 ${getWindowLabel(windowMethod)}`}
    description={`汇聚周期 ${getPeriodLabel(period)} 会自动拆成 30 个计算点，当前 step = ${getStep(period)}。`}
  />
);

const MigrationPanel = () => (
  <div style={sectionStyle}>
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space>
        <SwapOutlined style={{ color: '#7c3aed' }} />
        <Text strong>旧策略迁移规则</Text>
      </Space>
      <Row gutter={[10, 10]}>
        {migrationRows.map(([source, target]) => (
          <Col xs={24} md={12} key={source}>
            <div style={{ border: '1px solid #e1e7f0', borderRadius: 8, padding: 12, minHeight: 88 }}>
              <Tag color="default">{source}</Tag>
              <div style={{ marginTop: 8 }}>{target}</div>
            </div>
          </Col>
        ))}
      </Row>
    </Space>
  </div>
);

const RecommendationPanel = ({ metric }: { metric: MetricDefinition }) => (
  <div style={sectionStyle}>
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space>
        <BarChartOutlined style={{ color: '#16a34a' }} />
        <Text strong>模板推荐</Text>
      </Space>
      <Text>{metric.recommendation}</Text>
      <Space wrap>
        <Tag color="blue">指标类型：{metric.kind}</Tag>
        <Tag color="green">推荐分组聚合：{getGroupLabel(metric.defaultGroupMethod)}</Tag>
        <Tag color="green">推荐汇聚方式：{getWindowLabel(metric.defaultWindowMethod)}</Tag>
      </Space>
    </Space>
  </div>
);

const ScenarioPanel = ({ metric }: { metric: MetricDefinition }) => (
  <div style={sectionStyle}>
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space>
        <DatabaseOutlined style={{ color: '#1677ff' }} />
        <Text strong>场景预览</Text>
      </Space>
      <Text>{metric.scenario}</Text>
    </Space>
  </div>
);

const AggregationDesigner = ({
  initialMetric = 'disk',
  initialGroupMethod,
  initialWindowMethod,
  showMigration = false,
}: {
  initialMetric?: MetricKey;
  initialGroupMethod?: GroupMethod;
  initialWindowMethod?: WindowMethod;
  showMigration?: boolean;
}) => {
  const initialMetricDefinition = getMetric(initialMetric);
  const [metricKey, setMetricKey] = useState<MetricKey>(initialMetric);
  const metric = getMetric(metricKey);
  const [groups, setGroups] = useState<string[]>(initialMetricDefinition.defaultGroups);
  const [period, setPeriod] = useState('5m');
  const [groupMethod, setGroupMethod] = useState<GroupMethod>(
    initialGroupMethod || initialMetricDefinition.defaultGroupMethod
  );
  const [windowMethod, setWindowMethod] = useState<WindowMethod>(
    initialWindowMethod || initialMetricDefinition.defaultWindowMethod
  );

  const query = useMemo(
    () => getQuery(groupMethod, windowMethod, metric.metricName, groups, period),
    [groupMethod, groups, metric.metricName, period, windowMethod]
  );
  const steps = useMemo(
    () => getSteps(groupMethod, windowMethod, groups, period),
    [groupMethod, groups, period, windowMethod]
  );

  const handleMetricChange = (next: MetricKey) => {
    const nextMetric = getMetric(next);
    setMetricKey(next);
    setGroups(nextMetric.defaultGroups);
    setGroupMethod(nextMetric.defaultGroupMethod);
    setWindowMethod(nextMetric.defaultWindowMethod);
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
            <Title level={3} style={{ margin: 0 }}>策略双层汇聚设计器</Title>
            <Text type="secondary">
              将“分组维度内先怎么聚合”和“汇聚周期内再怎么计算”拆成两个配置项，避免一个方法同时承担两层语义。
            </Text>
          </Space>
        </section>

        <Row gutter={[16, 16]}>
          <Col xs={24} xl={10}>
            <section style={sectionStyle}>
              <Space direction="vertical" size={18} style={{ width: '100%' }}>
                <Space>
                  <ApartmentOutlined style={{ color: '#1677ff' }} />
                  <Text strong>定义指标</Text>
                </Space>

                <div>
                  <Text strong>指标</Text>
                  <Select
                    value={metricKey}
                    onChange={handleMetricChange}
                    style={{ width: '100%', marginTop: 8 }}
                    options={metrics.map((item) => ({
                      label: `${item.name}（${item.kind}）`,
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
                    监控策略根据所选分组维度分析指标，未指定的维度数据将统一聚合处理。
                  </Text>
                </div>

                <div>
                  <Text strong>分组聚合方式</Text>
                  <Select
                    value={groupMethod}
                    onChange={setGroupMethod}
                    style={{ width: '100%', marginTop: 8 }}
                    options={groupMethods.map((item) => ({
                      label: `${item.label} - ${item.help}`,
                      value: item.value,
                    }))}
                  />
                  <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                    默认：AVG。用于决定同一分组下未入选维度的多条序列如何先合并。
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
                    汇聚周期是观察窗口，step 根据汇聚周期自动计算为 30 个计算点。
                  </Text>
                </div>

                <div>
                  <Text strong>汇聚方式</Text>
                  <Select
                    value={windowMethod}
                    onChange={setWindowMethod}
                    style={{ width: '100%', marginTop: 8 }}
                    options={windowMethods.map((item) => ({
                      label: `${item.label} - ${item.help}`,
                      value: item.value,
                    }))}
                  />
                  <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                    默认：AVG_OVER_TIME。用于决定观察窗口内如何得到最终阈值判断值。
                  </Text>
                </div>

                <Divider style={{ margin: 0 }} />
                <MethodSummary groupMethod={groupMethod} windowMethod={windowMethod} period={period} />
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
                      <div style={{ border: '1px solid #e1e7f0', borderRadius: 8, padding: 12, minHeight: 116 }}>
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
                </div>
                <Alert
                  type="warning"
                  showIcon
                  message="COUNT_OVER_TIME 与 LAST_OVER_TIME 仍需按产品语义确认最终 MetricsQL 表达式"
                  description="原型先表达双层配置模型：先按分组聚合方式得到分组序列，再按汇聚方式在窗口内计算。后台实现时需结合 VictoriaMetrics 语法和实际数据类型落地。"
                />
              </Space>
            </section>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} xl={showMigration ? 24 : 12}>
            {showMigration ? <MigrationPanel /> : <ScenarioPanel metric={metric} />}
          </Col>
          {!showMigration && (
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
  render: () => <AggregationDesigner initialMetric="disk" initialGroupMethod="avg" initialWindowMethod="avg_over_time" />,
};

export const InterfaceStatusLast: Story = {
  render: () => (
    <AggregationDesigner initialMetric="interface_status" initialGroupMethod="avg" initialWindowMethod="last_over_time" />
  ),
};

export const DeltaCounterSum: Story = {
  render: () => (
    <AggregationDesigner initialMetric="request_delta" initialGroupMethod="sum" initialWindowMethod="sum_over_time" />
  ),
};

export const MethodComparison: Story = {
  render: () => <AggregationDesigner initialMetric="interface_inventory" showMigration />,
};
