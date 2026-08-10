import type { Meta, StoryObj } from '@storybook/nextjs';
import { useMemo, useState } from 'react';
import {
  Button,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import { CloseOutlined, FunctionOutlined, PlusOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface ConditionLine {
  connector: 'AND' | 'OR';
  dimension: string;
  method: string;
  value: string;
}

interface MetricLine {
  ref: string;
  metric: string;
  conditions: ConditionLine[];
  groupMethod: string;
  groupBy: string[];
}

const metrics = [
  { label: 'CPU 使用率', value: 'cpu_usage', query: '100 - cpu_usage_idle{__$labels__}' },
  { label: 'HTTP 5xx 请求数', value: 'http_5xx_total', query: 'rate(http_requests_total{status=~"5..", __$labels__}[5m])' },
  { label: 'HTTP 总请求数', value: 'http_requests_total', query: 'rate(http_requests_total{__$labels__}[5m])' },
  { label: '磁盘已用容量', value: 'disk_used_bytes', query: 'disk_used_bytes{__$labels__}' },
  { label: '磁盘总容量', value: 'disk_total_bytes', query: 'disk_total_bytes{__$labels__}' },
];

const groupMethods = [
  { label: 'avg by', value: 'avg' },
  { label: 'max by', value: 'max' },
  { label: 'sum by', value: 'sum' },
  { label: 'min by', value: 'min' },
  { label: 'count by', value: 'count' },
];

const groupByOptions = ['instance_id', 'service', 'endpoint', 'disk', 'mountpoint'].map((item) => ({
  label: item,
  value: item,
}));

const conditionDimensionOptions = ['instance_id', 'service', 'endpoint', 'status', 'disk', 'mountpoint'].map((item) => ({
  label: item,
  value: item,
}));

const conditionMethodOptions = [
  { label: '=', value: '=' },
  { label: '!=', value: '!=' },
  { label: '=~', value: '=~' },
  { label: '!~', value: '!~' },
];

const connectorOptions = [
  { label: 'AND', value: 'AND' },
  { label: 'OR', value: 'OR' },
];

const windowMethods = [
  { label: 'AVG_OVER_TIME', value: 'avg_over_time' },
  { label: 'MAX_OVER_TIME', value: 'max_over_time' },
  { label: 'SUM_OVER_TIME', value: 'sum_over_time' },
  { label: 'LAST_OVER_TIME', value: 'last_over_time' },
];

const pageStyle = {
  minHeight: 760,
  width: '100vw',
  maxWidth: '100%',
  boxSizing: 'border-box' as const,
  overflowX: 'hidden' as const,
  background: '#f3f7fc',
  padding: '28px',
  color: '#172033',
};

const layoutStyle = {
  display: 'grid',
  gridTemplateColumns: 'minmax(760px, 880px) minmax(420px, 1fr)',
  gap: 24,
  alignItems: 'start',
  maxWidth: 1480,
  margin: '0 auto',
};

const panelStyle = {
  background: '#fff',
  border: '1px solid #dbe5f0',
  borderRadius: 8,
  padding: 20,
};

const stickyPanelStyle = {
  ...panelStyle,
  position: 'sticky' as const,
  top: 24,
};

const stepTitleStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  marginBottom: 18,
};

const stepBadgeStyle = {
  width: 32,
  height: 32,
  borderRadius: '50%',
  background: '#1f5eff',
  color: '#fff',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontWeight: 600,
};

const titleStyle = {
  fontSize: 18,
  fontWeight: 600,
};

const formRowStyle = {
  display: 'grid',
  gridTemplateColumns: '112px minmax(0, 1fr)',
  gap: 12,
  alignItems: 'start',
  marginBottom: 18,
};

const labelStyle = {
  lineHeight: '32px',
  textAlign: 'right' as const,
  color: '#26364a',
};

const helperStyle = {
  display: 'block',
  marginTop: 8,
  color: '#5f7898',
  fontSize: 13,
};

const metricEditorStyle = {
  border: '1px solid #cbd8e7',
  borderRadius: 6,
  background: '#fbfdff',
  overflow: 'hidden',
};

const editorHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  minHeight: 42,
  padding: '0 12px',
  borderBottom: '1px solid #e4ebf4',
  background: '#f7faff',
};

const editorBodyStyle = {
  padding: 12,
};

const metricBlockStyle = {
  border: '1px solid #dce6f1',
  borderRadius: 6,
  background: '#fff',
  padding: 10,
  marginBottom: 10,
};

const metricLineStyle = {
  display: 'flex',
  flexWrap: 'wrap' as const,
  gap: 8,
  alignItems: 'center',
};

const conditionLineStyle = {
  display: 'flex',
  flexWrap: 'wrap' as const,
  gap: 8,
  alignItems: 'center',
  marginTop: 8,
  paddingLeft: 42,
};

const refStyle = {
  height: 32,
  border: '1px solid #cbd8e7',
  borderRadius: 4,
  background: '#f2f6fb',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: '#42607d',
  fontWeight: 600,
};

const formulaLineStyle = {
  display: 'grid',
  gridTemplateColumns: '34px minmax(170px, 0.5fr) 24px minmax(220px, 1fr)',
  gap: 8,
  alignItems: 'center',
  marginTop: 10,
};

const codeStyle = {
  display: 'block',
  minHeight: 142,
  whiteSpace: 'pre-wrap' as const,
  wordBreak: 'break-word' as const,
  borderRadius: 6,
  background: '#f7f9fc',
  border: '1px solid #d8e2ef',
  color: '#26364a',
  padding: 12,
  fontSize: 12,
  lineHeight: 1.7,
};

const chartStyle = {
  height: 158,
  border: '1px solid #e0e8f2',
  borderRadius: 6,
  background: 'linear-gradient(180deg, rgba(24, 94, 255, 0.08), rgba(24, 94, 255, 0.01))',
  position: 'relative' as const,
  overflow: 'hidden',
};

const RequiredLabel = ({ children }: { children: string }) => (
  <span>
    {children}
    <Text type="danger"> *</Text>
  </span>
);

const FormRow = ({
  label,
  required,
  helper,
  children,
}: {
  label: string;
  required?: boolean;
  helper?: string;
  children: React.ReactNode;
}) => (
  <div style={formRowStyle}>
    <div style={labelStyle}>{required ? <RequiredLabel>{label}</RequiredLabel> : label}</div>
    <div>
      {children}
      {helper && <Text style={helperStyle}>{helper}</Text>}
    </div>
  </div>
);

const conditionsToFilter = (conditions: ConditionLine[]) =>
  conditions
    .filter((condition) => condition.dimension && condition.method && condition.value)
    .map((condition, index) => {
      const clause = `${condition.dimension}${condition.method}"${condition.value}"`;
      return index === 0 ? clause : `${condition.connector} ${clause}`;
    })
    .join(', ');

const metricQuery = (metric: string, conditions: ConditionLine[]) => {
  const item = metrics.find((metricItem) => metricItem.value === metric);
  const filter = conditionsToFilter(conditions);
  const labels = filter ? `${filter}, ` : '';
  return (item?.query || metric).replace('__$labels__', labels).replace(', }', '}');
};

const periodStep = (period: number) => {
  const seconds = Math.max(1, Math.floor((period * 60) / 30));
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
};

const MetricEditorCompanion = ({
  initialLines,
}: {
  initialLines?: MetricLine[];
}) => {
  const [metricLines, setMetricLines] = useState<MetricLine[]>(
    initialLines || [
      {
        ref: 'a',
        metric: 'http_5xx_total',
        conditions: [{ connector: 'AND', dimension: 'service', method: '=', value: 'checkout' }],
        groupMethod: 'sum',
        groupBy: ['instance_id'],
      },
      {
        ref: 'b',
        metric: 'http_requests_total',
        conditions: [{ connector: 'AND', dimension: 'service', method: '=', value: 'checkout' }],
        groupMethod: 'sum',
        groupBy: ['instance_id'],
      },
    ]
  );
  const [formula, setFormula] = useState('a / b * 100');
  const [resultName, setResultName] = useState('HTTP 5xx 错误率');
  const [period, setPeriod] = useState(5);
  const [windowMethod, setWindowMethod] = useState('avg_over_time');

  const updateLine = (index: number, patch: Partial<MetricLine>) => {
    setMetricLines((lines) => lines.map((line, lineIndex) => (lineIndex === index ? { ...line, ...patch } : line)));
  };

  const updateCondition = (lineIndex: number, conditionIndex: number, patch: Partial<ConditionLine>) => {
    setMetricLines((lines) =>
      lines.map((line, index) => {
        if (index !== lineIndex) return line;
        return {
          ...line,
          conditions: line.conditions.map((condition, currentIndex) =>
            currentIndex === conditionIndex ? { ...condition, ...patch } : condition
          ),
        };
      })
    );
  };

  const addCondition = (lineIndex: number) => {
    setMetricLines((lines) =>
      lines.map((line, index) =>
        index === lineIndex
          ? {
            ...line,
            conditions: [...line.conditions, { connector: 'AND', dimension: 'endpoint', method: '=~', value: '/api/.*' }],
          }
          : line
      )
    );
  };

  const removeCondition = (lineIndex: number, conditionIndex: number) => {
    setMetricLines((lines) =>
      lines.map((line, index) => {
        if (index !== lineIndex) return line;
        return {
          ...line,
          conditions: line.conditions.filter((_, currentIndex) => currentIndex !== conditionIndex),
        };
      })
    );
  };

  const addLine = () => {
    const ref = String.fromCharCode(97 + metricLines.length);
    setMetricLines((lines) => [
      ...lines,
      {
        ref,
        metric: 'disk_used_bytes',
        conditions: [{ connector: 'AND', dimension: 'instance_id', method: '=~', value: 'host-01' }],
        groupMethod: 'avg',
        groupBy: ['instance_id'],
      },
    ]);
  };

  const removeLine = (index: number) => {
    if (metricLines.length <= 1) return;
    setMetricLines((lines) => lines.filter((_, lineIndex) => lineIndex !== index));
  };

  const baseExpression = useMemo(() => {
    const normalizedFormula = metricLines.length === 1 ? metricLines[0].ref : formula;
    return metricLines.reduce((expression, line) => {
      const grouped = `${line.groupMethod}(${metricQuery(line.metric, line.conditions)}) by (${line.groupBy.join(', ')})`;
      return expression.replaceAll(line.ref, `(${grouped})`);
    }, normalizedFormula);
  }, [formula, metricLines]);

  const finalQuery = useMemo(() => {
    const step = periodStep(period);
    return `${windowMethod}((${baseExpression})[${period}m:${step}])`;
  }, [baseExpression, period, windowMethod]);

  return (
    <>
      <style>
        {`
          html,
          body,
          #storybook-root {
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
        <div style={layoutStyle}>
          <div style={panelStyle}>
            <div style={stepTitleStyle}>
              <span style={stepBadgeStyle}>2</span>
              <span style={titleStyle}>定义指标</span>
            </div>

            <FormRow label="采集模板" required>
              <Space wrap>
                <Button type="primary">主机（Telegraf）</Button>
                <Button type="text">Windows WMI</Button>
                <Button type="text">rex-test</Button>
              </Space>
            </FormRow>

            <FormRow
              label="指标"
              required
            >
              <div style={metricEditorStyle}>
                <div style={editorHeaderStyle}>
                  <Space size={8}>
                    <Text strong>指标编辑器</Text>
                    <Tag color="blue">表达式</Tag>
                  </Space>
                </div>

                <div style={editorBodyStyle}>
                  {metricLines.map((line, index) => (
                    <div style={metricBlockStyle} key={line.ref}>
                      <div style={metricLineStyle}>
                        <span style={refStyle}>{line.ref}</span>
                        <Select
                          value={line.metric}
                          onChange={(value) => updateLine(index, { metric: value })}
                          options={metrics}
                          style={{ minWidth: 190, flex: '1 1 220px' }}
                        />
                        <Select
                          value={line.groupMethod}
                          onChange={(value) => updateLine(index, { groupMethod: value })}
                          options={groupMethods}
                          style={{ width: 118 }}
                        />
                        <Select
                          mode="multiple"
                          value={line.groupBy}
                          onChange={(value) => updateLine(index, { groupBy: value })}
                          options={groupByOptions}
                          maxTagCount="responsive"
                          style={{ minWidth: 190, flex: '1 1 220px' }}
                        />
                        <Button
                          icon={<CloseOutlined />}
                          disabled={metricLines.length <= 1}
                          onClick={() => removeLine(index)}
                        />
                      </div>
                      {line.conditions.map((condition, conditionIndex) => (
                        <div style={conditionLineStyle} key={`${line.ref}-${conditionIndex}`}>
                          {conditionIndex === 0 ? (
                            <Text type="secondary" style={{ width: 68 }}>
                              条件
                            </Text>
                          ) : (
                            <Select
                              value={condition.connector}
                              onChange={(value) => updateCondition(index, conditionIndex, { connector: value })}
                              options={connectorOptions}
                              style={{ width: 68 }}
                            />
                          )}
                          <Select
                            value={condition.dimension}
                            onChange={(value) => updateCondition(index, conditionIndex, { dimension: value })}
                            options={conditionDimensionOptions}
                            style={{ minWidth: 150, flex: '1 1 160px' }}
                          />
                          <Select
                            value={condition.method}
                            onChange={(value) => updateCondition(index, conditionIndex, { method: value })}
                            options={conditionMethodOptions}
                            style={{ width: 86 }}
                          />
                          <Input
                            value={condition.value}
                            onChange={(event) => updateCondition(index, conditionIndex, { value: event.target.value })}
                            style={{ minWidth: 160, flex: '1 1 180px' }}
                          />
                          <Button
                            icon={<CloseOutlined />}
                            onClick={() => removeCondition(index, conditionIndex)}
                          />
                        </div>
                      ))}
                      <div style={{ paddingLeft: 42, marginTop: 8 }}>
                        <Button size="small" icon={<PlusOutlined />} onClick={() => addCondition(index)}>
                          添加条件
                        </Button>
                      </div>
                    </div>
                  ))}
                  <Space>
                    <Button icon={<PlusOutlined />} onClick={addLine}>
                      添加指标
                    </Button>
                  </Space>
                  {metricLines.length > 1 && (
                    <div style={formulaLineStyle}>
                      <span style={{ ...refStyle, background: '#eaf2ff', color: '#1f5eff' }}>
                        <FunctionOutlined />
                      </span>
                      <Input
                        value={resultName}
                        onChange={(event) => setResultName(event.target.value)}
                        placeholder="结果名称"
                      />
                      <Text type="secondary" style={{ textAlign: 'center' }}>
                        =
                      </Text>
                      <Input value={formula} onChange={(event) => setFormula(event.target.value)} />
                    </div>
                  )}
                </div>
              </div>
            </FormRow>

            <FormRow label="聚合周期" required>
              <InputNumber value={period} min={1} addonAfter="分钟" onChange={(value) => setPeriod(value || 5)} style={{ width: '100%' }} />
            </FormRow>

            <FormRow label="聚合方式" required>
              <Select value={windowMethod} onChange={setWindowMethod} options={windowMethods} style={{ width: '100%' }} />
            </FormRow>
          </div>

          <div style={stickyPanelStyle}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Space wrap>
                <Tag color="blue">指标表达式</Tag>
                <Tag color="green">step：{periodStep(period)}</Tag>
                <Tag>{metricLines.length > 1 ? '公式结果' : '单结果序列'}</Tag>
                {metricLines.length > 1 && <Tag color="purple">{resultName || '未命名结果'}</Tag>}
              </Space>
              <Text strong>指标预览</Text>
              <div style={chartStyle}>
                <svg viewBox="0 0 480 160" width="100%" height="100%" preserveAspectRatio="none">
                  <path
                    d="M0,108 C60,92 92,132 148,86 C204,40 246,86 306,72 C362,58 414,118 480,54"
                    fill="none"
                    stroke="#1f5eff"
                    strokeWidth="3"
                  />
                  <path
                    d="M0,108 C60,92 92,132 148,86 C204,40 246,86 306,72 C362,58 414,118 480,54 L480,160 L0,160 Z"
                    fill="rgba(31,94,255,0.12)"
                    stroke="none"
                  />
                  <line x1="0" y1="96" x2="480" y2="96" stroke="#ff4d4f" strokeDasharray="6 6" />
                </svg>
              </div>
              <Text strong>最终评估查询</Text>
              <code style={codeStyle}>{finalQuery}</code>
            </Space>
          </div>
        </div>
      </div>
    </>
  );
};

const meta: Meta<typeof MetricEditorCompanion> = {
  title: 'Monitor/PolicyMetricEditorCompanion',
  component: MetricEditorCompanion,
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;

type Story = StoryObj<typeof MetricEditorCompanion>;

export const FormulaExpression: Story = {
  render: () => <MetricEditorCompanion />,
};

export const SingleMetricExpression: Story = {
  render: () => (
    <MetricEditorCompanion
      initialLines={[
        {
          ref: 'a',
          metric: 'cpu_usage',
          conditions: [{ connector: 'AND', dimension: 'instance_id', method: '=~', value: 'host-01' }],
          groupMethod: 'avg',
          groupBy: ['instance_id'],
        },
      ]}
    />
  ),
};
