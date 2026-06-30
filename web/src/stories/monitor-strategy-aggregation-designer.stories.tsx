import type { Meta, StoryObj } from '@storybook/nextjs';
import { useMemo, useState } from 'react';
import { Alert, Button, Divider, InputNumber, Select, Space, Tag, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';

const { Text } = Typography;

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

const collectTabs = ['主机（Telegraf）', '主机远程采集（Telegraf）', 'Windows WMI', 'rex-test'];

const groupMethods: Array<{ value: GroupMethod; label: string; help: string }> = [
  { value: 'avg', label: 'AVG（平均值）', help: '默认：AVG。同一分组下多条序列先求平均。' },
  { value: 'max', label: 'MAX（最大值）', help: '同一分组下多条序列先取最大值。' },
  { value: 'min', label: 'MIN（最小值）', help: '同一分组下多条序列先取最小值。' },
  { value: 'sum', label: 'SUM（求和）', help: '同一分组下多条序列先求和。' },
];

const windowMethods: Array<{ value: WindowMethod; label: string; help: string }> = [
  { value: 'avg_over_time', label: 'AVG_OVER_TIME', help: '默认：AVG_OVER_TIME。窗口内求平均。' },
  { value: 'max_over_time', label: 'MAX_OVER_TIME', help: '窗口内取最大值。' },
  { value: 'min_over_time', label: 'MIN_OVER_TIME', help: '窗口内取最小值。' },
  { value: 'sum_over_time', label: 'SUM_OVER_TIME', help: '窗口内累加。' },
  { value: 'count_over_time', label: 'COUNT_OVER_TIME', help: '窗口内统计有效数量。' },
  { value: 'last_over_time', label: 'LAST_OVER_TIME', help: '窗口内取最近有效值。' },
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
    recommendation: '默认双 AVG：先得到实例级平均磁盘使用率，再看最近一个聚合周期内的平均水平。',
    scenario: '实例 A 有 4 块磁盘。分组聚合方式 AVG 会先把 4 块磁盘合成实例级序列；聚合方式 AVG_OVER_TIME 再计算最近窗口内的平均值。',
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
    scenario: '服务 A 有多个实例。分组聚合方式 SUM 先合并实例增量；聚合方式 SUM_OVER_TIME 再得到最近窗口内请求总量。',
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
  ['AVG / AVG_OVER_TIME', '分组聚合 AVG + 聚合方式 AVG_OVER_TIME，简称双 AVG'],
  ['MAX / MAX_OVER_TIME', '分组聚合 MAX + 聚合方式 MAX_OVER_TIME，简称双 MAX'],
  ['MIN / MIN_OVER_TIME', '分组聚合 MIN + 聚合方式 MIN_OVER_TIME，简称双 MIN'],
  ['SUM / SUM_OVER_TIME', '分组聚合 SUM + 聚合方式 SUM_OVER_TIME，简称双 SUM'],
  ['COUNT', '分组聚合 SUM + 聚合方式 COUNT_OVER_TIME'],
  ['LAST_OVER_TIME', '分组聚合 AVG + 聚合方式 LAST_OVER_TIME'],
];

const pageStyle = {
  minHeight: 720,
  width: '100vw',
  maxWidth: '100%',
  boxSizing: 'border-box' as const,
  overflowX: 'hidden' as const,
  background:
    'linear-gradient(135deg, rgba(239,247,255,0.95) 0%, rgba(255,255,255,0.95) 48%, rgba(244,250,255,0.95) 100%)',
  padding: '34px 24px',
};

const shellStyle = {
  position: 'relative' as const,
  maxWidth: 980,
  margin: '0 auto',
  paddingLeft: 48,
};

const stepBadgeStyle = {
  position: 'absolute' as const,
  left: 0,
  top: 0,
  width: 32,
  height: 32,
  borderRadius: '50%',
  background: '#0f5bff',
  color: '#fff',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontWeight: 600,
};

const sectionTitleStyle = {
  fontSize: 18,
  fontWeight: 600,
  lineHeight: '32px',
  marginBottom: 18,
};

const formRowStyle = {
  display: 'grid',
  gridTemplateColumns: '124px minmax(0, 1fr)',
  columnGap: 12,
  alignItems: 'start',
  marginBottom: 18,
};

const formLabelStyle = {
  lineHeight: '32px',
  textAlign: 'right' as const,
  color: '#1f2937',
};

const formControlStyle = {
  width: '100%',
};

const groupByControlStyle = {
  display: 'grid',
  gridTemplateColumns: '184px 42px minmax(0, 1fr)',
  alignItems: 'center',
  border: '1px solid #1677ff',
  borderRadius: 5,
  background: '#fff',
  height: 36,
  overflow: 'hidden',
  boxShadow: '0 0 0 2px rgba(22, 119, 255, 0.08)',
};

const groupMethodSelectStyle = {
  width: '100%',
  height: 34,
};

const groupDimensionSelectStyle = {
  width: '100%',
  minWidth: 0,
  height: 34,
};

const groupBySelectClassName = 'aggregation-group-by-select';

const groupByDividerStyle = {
  height: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRight: '1px solid #edf1f6',
  borderLeft: '1px solid #edf1f6',
  background: '#fbfcff',
};

const byTextStyle = {
  textAlign: 'center' as const,
  color: '#6b7280',
  fontSize: 13,
};

const helperStyle = {
  display: 'block',
  marginTop: 8,
  color: '#5b789b',
  fontSize: 13,
};

const inlinePanelStyle = {
  marginLeft: 136,
  marginTop: 8,
  border: '1px solid #dbe7f3',
  borderRadius: 4,
  background: 'rgba(255,255,255,0.78)',
  padding: 12,
};

const codeStyle = {
  display: 'block',
  whiteSpace: 'pre-wrap' as const,
  wordBreak: 'break-word' as const,
  borderRadius: 4,
  background: '#f7f9fc',
  border: '1px solid #d8e2ef',
  color: '#26364a',
  padding: 10,
  fontSize: 12,
  lineHeight: 1.6,
};

const getMetric = (key: MetricKey) => metrics.find((metric) => metric.key === key) || metrics[0];

const getPeriodSeconds = (periodMinutes: number) => periodMinutes * 60;

const getStep = (periodMinutes: number) => {
  const seconds = Math.max(1, Math.floor(getPeriodSeconds(periodMinutes) / 30));
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
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
  periodMinutes: number
) => {
  const period = `${periodMinutes}m`;
  const groupToken = groups.length ? 'group_by' : 'all_series';
  const groupClause = groups.length ? ` by (${groups.join(', ')})` : '';
  const step = getStep(periodMinutes);

  return `${windowMethod}((${groupMethod}(metric) by (${groupToken}))[${period}:${step}])

示例：
${windowMethod}((${groupMethod}(${metricName})${groupClause})[${period}:${step}])`;
};

const getOptions = <T extends string>(items: Array<{ value: T; label: string; help: string }>) =>
  items.map((item) => ({
    value: item.value,
    label: `${item.label} - ${item.help}`,
  }));

const getCompactOptions = <T extends string>(items: Array<{ value: T; label: string }>) =>
  items.map((item) => ({
    value: item.value,
    label: item.label,
  }));

const RequiredLabel = ({ children }: { children: string }) => (
  <span>
    {children}
    <Text type="danger"> *</Text>
  </span>
);

const FormRow = ({
  label,
  required,
  children,
  helper,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
  helper?: string;
}) => (
  <div style={formRowStyle}>
    <div style={formLabelStyle}>{required ? <RequiredLabel>{label}</RequiredLabel> : label}</div>
    <div>
      {children}
      {helper && <Text style={helperStyle}>{helper}</Text>}
    </div>
  </div>
);

const MigrationPanel = () => (
  <div style={inlinePanelStyle}>
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Text strong>旧策略迁移规则</Text>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
        {migrationRows.map(([source, target]) => (
          <div key={source} style={{ border: '1px solid #e1e7f0', borderRadius: 4, padding: 8 }}>
            <Tag color="default">{source}</Tag>
            <Text style={{ display: 'block', marginTop: 6 }}>{target}</Text>
          </div>
        ))}
      </div>
    </Space>
  </div>
);

const AggregationForm = ({
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
  const [periodMinutes, setPeriodMinutes] = useState(5);
  const [groupMethod, setGroupMethod] = useState<GroupMethod>(
    initialGroupMethod || initialMetricDefinition.defaultGroupMethod
  );
  const [windowMethod, setWindowMethod] = useState<WindowMethod>(
    initialWindowMethod || initialMetricDefinition.defaultWindowMethod
  );

  const query = useMemo(
    () => getQuery(groupMethod, windowMethod, metric.metricName, groups, periodMinutes),
    [groupMethod, groups, metric.metricName, periodMinutes, windowMethod]
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

          .${groupBySelectClassName}.ant-select-single .ant-select-selector {
            height: 34px !important;
            padding-inline: 10px !important;
          }

          .${groupBySelectClassName}.ant-select-single .ant-select-selection-item,
          .${groupBySelectClassName}.ant-select-single .ant-select-selection-placeholder {
            line-height: 34px !important;
          }

          .${groupBySelectClassName}.ant-select-multiple .ant-select-selector {
            min-height: 34px !important;
            padding-inline: 8px !important;
          }

          .${groupBySelectClassName}.ant-select-multiple .ant-select-selection-overflow {
            align-items: center;
            min-height: 34px;
          }

          .${groupBySelectClassName}.ant-select-multiple .ant-select-selection-item {
            margin-top: 0;
            margin-bottom: 0;
          }
        `}
      </style>
      <div style={pageStyle}>
        <div style={shellStyle}>
          <div style={stepBadgeStyle}>2</div>
          <div style={sectionTitleStyle}>定义指标</div>

          <FormRow label="采集模板" required>
            <Space wrap>
              {collectTabs.map((tab, index) => (
                <Button key={tab} type={index === 0 ? 'primary' : 'text'}>
                  {tab}
                </Button>
              ))}
            </Space>
          </FormRow>

          <FormRow label="指标" required helper={metric.description}>
            <Select
              value={metricKey}
              onChange={handleMetricChange}
              style={formControlStyle}
              options={metrics.map((item) => ({
                label: `${item.name}（${item.kind}）`,
                value: item.key,
              }))}
            />
          </FormRow>

          <FormRow
            label="分组维度"
            required
            helper="左侧选择未指定维度的聚合算法，右侧选择最终告警对象维度。未指定的维度数据将统一聚合处理。"
          >
            <div style={groupByControlStyle}>
              <Select
                value={groupMethod}
                onChange={setGroupMethod}
                variant="borderless"
                className={groupBySelectClassName}
                style={groupMethodSelectStyle}
                options={getCompactOptions(groupMethods)}
              />
              <div style={groupByDividerStyle}>
                <Text style={byTextStyle}>by</Text>
              </div>
              <Select
                mode="multiple"
                value={groups}
                onChange={setGroups}
                variant="borderless"
                className={groupBySelectClassName}
                style={groupDimensionSelectStyle}
                options={metric.groupOptions.map((item) => ({ label: item, value: item }))}
              />
            </div>
          </FormRow>

          <FormRow label="条件维度" helper="配置维度过滤条件，多个条件之间为 AND 关系。">
            <Button icon={<PlusOutlined />} />
          </FormRow>

          <FormRow
            label="聚合周期"
            required
            helper="汇聚周期是观察窗口，step 根据聚合周期自动计算为 30 个计算点。"
          >
            <InputNumber
              min={1}
              value={periodMinutes}
              onChange={(value) => setPeriodMinutes(value || 5)}
              addonAfter="分钟"
              style={formControlStyle}
            />
          </FormRow>

          <FormRow
            label="聚合方式"
            required
            helper="默认：AVG_OVER_TIME。用于决定观察窗口内如何得到最终阈值判断值。"
          >
            <Select
              value={windowMethod}
              onChange={setWindowMethod}
              style={formControlStyle}
              options={getOptions(windowMethods)}
            />
          </FormRow>

          <div style={inlinePanelStyle}>
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Space wrap>
                <Tag color="blue">分组聚合：{getGroupLabel(groupMethod)}</Tag>
                <Tag color="blue">汇聚方式：{getWindowLabel(windowMethod)}</Tag>
                <Tag color="green">step：{getStep(periodMinutes)}</Tag>
                <Tag>30 个计算点</Tag>
              </Space>
              <Text type="secondary">{metric.recommendation}</Text>
              <Text type="secondary">{metric.scenario}</Text>
              <Divider style={{ margin: '4px 0' }} />
              <code style={codeStyle}>{query}</code>
              <Alert
                type="warning"
                showIcon
                message="COUNT_OVER_TIME 与 LAST_OVER_TIME 的最终 MetricsQL 表达式需要后端实现时再校准"
              />
            </Space>
          </div>

          {showMigration && <MigrationPanel />}
        </div>
      </div>
    </>
  );
};

export const AggregationDesignerFrame = () => <AggregationForm />;

const meta: Meta<typeof AggregationDesignerFrame> = {
  title: 'Monitor/StrategyAggregationDesigner',
  component: AggregationDesignerFrame,
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;

type Story = StoryObj<typeof AggregationForm>;

export const DefaultNumericMetric: Story = {
  render: () => <AggregationForm initialMetric="disk" initialGroupMethod="avg" initialWindowMethod="avg_over_time" />,
};

export const InterfaceStatusLast: Story = {
  render: () => (
    <AggregationForm initialMetric="interface_status" initialGroupMethod="avg" initialWindowMethod="last_over_time" />
  ),
};

export const DeltaCounterSum: Story = {
  render: () => (
    <AggregationForm initialMetric="request_delta" initialGroupMethod="sum" initialWindowMethod="sum_over_time" />
  ),
};

export const MethodComparison: Story = {
  render: () => <AggregationForm initialMetric="interface_inventory" showMigration />,
};
