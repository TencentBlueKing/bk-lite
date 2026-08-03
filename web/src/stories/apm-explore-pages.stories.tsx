import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import {
  Button,
  Checkbox,
  Col,
  Input,
  InputNumber,
  Layout,
  List,
  Radio,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ApiOutlined,
  AppstoreOutlined,
  BellOutlined,
  BugOutlined,
  CheckOutlined,
  CloseCircleOutlined,
  CaretDownOutlined,
  CompassOutlined,
  FileSearchOutlined,
  FireFilled,
  MoreOutlined,
  RadarChartOutlined,
  RocketOutlined,
  SearchOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';

const { Content } = Layout;
const { Title, Text } = Typography;

/* ============================================================
 * bklite APM · 探索 · 交互式故事书
 *
 * 关键架构(已对齐规格书《探索.md》):
 *  1) 探索菜单下挂三个二级页:调用链 / 端点 / 错误
 *  2) 调用链:多维结构化检索 + Traces/Spans 切换 + 时延散点图 + Span 详情(瀑布图/火焰图)
 *  3) 端点:端点级 RED + 状态码细分 + 时延构成 + 跨维度切片
 *  4) 错误:Issue 自动聚类 + 列表 + 详情(影响面 / 典型样本 / 异常栈 / 版本分布 / 端点分布)
 *  5) 业务错误判定走 OTel Error + 业务侧 Span 标签,与 SLO good 口径解耦
 *  6) 不带同比 delta;危险信号(错误/激增)优先
 * ============================================================ */

const TOKENS = {
  bg: '#f5f7fa',
  surface: '#ffffff',
  border: '#e6ebf2',
  borderStrong: '#dbe2ec',
  text: '#1f2937',
  textSecondary: '#64748b',
  textTertiary: '#94a3b8',
  primary: '#155aef',
  primarySoft: '#eaf2ff',
  success: '#27c274',
  danger: '#f43b2c',
  warning: '#f59e0b',
  neutral: '#94a3b8',
};

const shellStyle: React.CSSProperties = {
  minHeight: '100vh',
  background: TOKENS.bg,
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
};

const surfaceCardStyle: React.CSSProperties = {
  background: TOKENS.surface,
  border: `1px solid ${TOKENS.border}`,
  borderRadius: 12,
};

const tabularNumStyle: React.CSSProperties = {
  fontVariantNumeric: 'tabular-nums',
};

/* ---------- 跨 Story URL ---------- */
const STORY_URLS = {
  home: '?path=/story/apm-home-pages--home-dashboard-story',
  service: '?path=/story/apm-service-pages--service-directory-app-view',
  topology: '?path=/story/apm-service-pages--service-topology',
  explore: '?path=/story/apm-explore-pages--traces-search',
  events: '?path=/story/apm-events-pages--alerts-list',
  integration: '?path=/story/apm-integration-pages-添加接入--integration-catalog-story',
};

/* ============================================================
 * 顶导(全局)
 * ============================================================ */
function TopMenuBar({ active = 'explore' }: { active?: string }) {
  const items = [
    { key: 'home', label: '首页', icon: <RadarChartOutlined />, href: STORY_URLS.home },
    { key: 'service', label: '服务', icon: <AppstoreOutlined />, href: STORY_URLS.service },
    { key: 'explore', label: '探索', icon: <CompassOutlined />, href: STORY_URLS.explore },
    { key: 'events', label: '事件', icon: <BellOutlined />, href: STORY_URLS.events },
    { key: 'integration', label: '集成', icon: <RocketOutlined />, href: STORY_URLS.integration },
  ];
  return (
    <div
      style={{
        background: TOKENS.surface,
        borderBottom: `1px solid ${TOKENS.border}`,
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        height: 52,
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          color: TOKENS.primary,
          marginRight: 24,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <RadarChartOutlined style={{ fontSize: 18 }} />
        <span>BK-Lite APM</span>
      </div>
      {items.map((it) => {
        const isActive = it.key === active;
        return (
          <a
            key={it.key}
            href={it.href}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '0 12px',
              height: 52,
              color: isActive ? TOKENS.primary : TOKENS.text,
              background: isActive ? TOKENS.primarySoft : 'transparent',
              borderBottom: isActive ? `2px solid ${TOKENS.primary}` : '2px solid transparent',
              fontSize: 14,
              fontWeight: isActive ? 600 : 500,
              textDecoration: 'none',
            }}
          >
            {it.icon}
            <span>{it.label}</span>
          </a>
        );
      })}
    </div>
  );
}

/* ============================================================
 * 探索二级导航:调用链 / 端点 / 错误
 * ============================================================ */
function ExploreSubNav({ active }: { active: 'traces' | 'endpoints' | 'errors' }) {
  const items = [
    { key: 'traces', label: '调用链', href: STORY_URLS.explore },
    { key: 'endpoints', label: '端点', href: '?path=/story/apm-explore-pages--endpoints-list' },
    { key: 'errors', label: '错误', href: '?path=/story/apm-explore-pages--issue-list' },
  ];
  return (
    <div
      style={{
        background: TOKENS.surface,
        borderBottom: `1px solid ${TOKENS.border}`,
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        height: 44,
      }}
    >
      {items.map((it) => {
        const isActive = it.key === active;
        return (
          <a
            key={it.key}
            href={it.href}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '0 12px',
              height: 44,
              color: isActive ? TOKENS.primary : TOKENS.text,
              borderBottom: isActive ? `2px solid ${TOKENS.primary}` : '2px solid transparent',
              fontSize: 14,
              fontWeight: isActive ? 600 : 500,
              textDecoration: 'none',
            }}
          >
            {it.key === 'traces' && <FileSearchOutlined />}
            {it.key === 'endpoints' && <ApiOutlined />}
            {it.key === 'errors' && <BugOutlined />}
            <span>{it.label}</span>
          </a>
        );
      })}
    </div>
  );
}

/* ============================================================
 * 1) TracesSearch · 调用链检索(分面 + 查询框 + 列表 + 时延散点图)
 * ============================================================ */

// 模拟 Trace 数据
const TRACES = [
  {
    key: 't1',
    traceId: '7f8a3b2e1c4d5e6f',
    service: 'payment-svc',
    operation: 'POST /api/v1/charge',
    method: 'POST',
    statusCode: 500,
    kind: '服务端',
    duration: 1240,
    spanCount: 18,
    status: 'error' as 'ok' | 'error',
    errorCount: 3,
    start: '2026-07-08 10:42:18.234',
    errorSpan: 'PaymentService.charge',
  },
  {
    key: 't2',
    traceId: 'a3b2c1d4e5f60718',
    service: 'checkout-api',
    operation: 'POST /api/v1/checkout',
    method: 'POST',
    statusCode: 200,
    kind: '客户端',
    duration: 856,
    spanCount: 12,
    status: 'ok' as const,
    start: '2026-07-08 10:42:16.892',
  },
  {
    key: 't3',
    traceId: 'b4c5d6e7f8091a2b',
    service: 'api-gateway',
    operation: 'GET /api/v1/catalog',
    method: 'GET',
    statusCode: 200,
    kind: '客户端',
    duration: 245,
    spanCount: 6,
    status: 'ok' as const,
    start: '2026-07-08 10:42:14.180',
  },
  {
    key: 't4',
    traceId: 'c5d6e7f8091a2b3c',
    service: 'auth-svc',
    operation: 'POST /api/v1/token/verify',
    method: 'POST',
    statusCode: 200,
    kind: '服务端',
    duration: 38,
    spanCount: 4,
    status: 'ok' as const,
    start: '2026-07-08 10:42:10.512',
  },
  {
    key: 't5',
    traceId: 'd6e7f8091a2b3c4d',
    service: 'payment-svc',
    operation: 'POST /api/v1/charge',
    method: 'POST',
    statusCode: 500,
    kind: '客户端',
    duration: 1890,
    spanCount: 24,
    status: 'error' as const,
    errorCount: 5,
    start: '2026-07-08 10:42:08.044',
    errorSpan: 'Redis connection timeout',
  },
  {
    key: 't6',
    traceId: 'e7f8091a2b3c4d5e',
    service: 'catalog-api',
    operation: 'GET /api/v1/products',
    method: 'GET',
    statusCode: 200,
    kind: '服务端',
    duration: 64,
    spanCount: 5,
    status: 'ok' as const,
    start: '2026-07-08 10:42:05.728',
  },
  {
    key: 't7',
    traceId: 'f8091a2b3c4d5e6f',
    service: 'payment-svc',
    operation: 'POST /api/v1/charge',
    method: 'POST',
    statusCode: 500,
    kind: '服务端',
    duration: 2105,
    spanCount: 28,
    status: 'error' as const,
    errorCount: 7,
    start: '2026-07-08 10:42:02.018',
    errorSpan: 'NullPointerException',
  },
  {
    key: 't8',
    traceId: '091a2b3c4d5e6f70',
    service: 'notification-worker',
    operation: 'send email',
    method: '',
    statusCode: 0,
    kind: '生产者',
    duration: 142,
    spanCount: 7,
    status: 'ok' as const,
    start: '2026-07-08 10:41:58.296',
  },
];

function FacetBox({ title, items }: { title: string; items: Array<{ key: string; label: string; count: number; color?: string }> }) {
  const [selected, setSelected] = useState<string[]>([]);
  return (
    <div style={{ marginBottom: 14 }}>
      <Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>
        {title}
        {selected.length > 0 && (
          <span style={{ marginLeft: 6, color: TOKENS.primary, fontWeight: 600 }}>
            ({selected.length})
          </span>
        )}
      </Text>
      <div style={{ marginTop: 4 }}>
        {items.map((it) => {
          const isSelected = selected.includes(it.key);
          return (
            <label
              key={it.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '4px 6px',
                margin: '0 -6px',
                fontSize: 13,
                cursor: 'pointer',
                borderRadius: 4,
                background: isSelected ? TOKENS.primarySoft : 'transparent',
                color: isSelected ? TOKENS.primary : TOKENS.text,
              }}
            >
              <Space size={6} align="center">
                <Checkbox
                  checked={isSelected}
                  onChange={(e) => {
                    setSelected((prev) =>
                      e.target.checked
                        ? [...prev, it.key]
                        : prev.filter((k) => k !== it.key),
                    );
                  }}
                />
                {it.color && (
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: it.color,
                      display: 'inline-block',
                    }}
                  />
                )}
                <span>{it.label}</span>
              </Space>
              <span style={tabularNumStyle}>{it.count}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

/** 数字范围筛选(对齐 datadog "耗时" 分面) */
function FacetRange({
  title,
  min,
  max,
  unit,
}: {
  title: string;
  min: number;
  max: number;
  unit: string;
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {title}
      </Text>
      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
        <InputNumber
          size="small"
          min={0}
          defaultValue={min}
          style={{ width: '50%' }}
          addonAfter={unit}
        />
        <span style={{ color: TOKENS.textTertiary, fontSize: 12 }}>—</span>
        <InputNumber
          size="small"
          min={0}
          defaultValue={max}
          style={{ width: '50%' }}
          addonAfter={unit}
        />
      </div>
    </div>
  );
}

function TracesSearch() {
  const [entity, setEntity] = useState<'spans' | 'traces'>('spans');
  const [view, setView] = useState<'detail' | 'aggregate'>('detail');
  const [aggForm, setAggForm] = useState<'top' | 'table'>('top');
  const [aggSort, setAggSort] = useState<'count' | 'error' | 'p95'>('count');
  const [aggDim, setAggDim] = useState<
    'service' | 'endpoint' | 'version' | 'env'
  >('service');
  const [liveMode, setLiveMode] = useState<string>('off');
  return (
    <div style={shellStyle}>
      <TopMenuBar active="explore" />
      <ExploreSubNav active="traces" />
      <Content style={{ padding: 24 }}>
        {/* 顶部查询区 — 对齐 datadog(Spans/Traces tab + 搜索框 + 右侧 7d + 实时尾部) */}
        <div
          style={{
            ...surfaceCardStyle,
            padding: '10px 16px',
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          {/* 左侧:Spans | Traces tab */}
          <Segmented
            size="small"
            value={entity}
            onChange={(v) => setEntity(v as 'spans' | 'traces')}
            options={[
              { value: 'spans', label: 'Spans' },
              { value: 'traces', label: 'Traces' },
            ]}
          />
          {/* 搜索框 */}
          <Input
            placeholder='按 key-value 过滤,如 service:auth status:error duration:>30ms'
            prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
            style={{ flex: 1, minWidth: 360 }}
            defaultValue='service:auth status:error duration:>30ms'
            allowClear
          />
          {/* 右侧:7d + 实时尾部 */}
          <Space size={4}>
            <Select
              size="small"
              defaultValue="7d"
              style={{ width: 90 }}
              options={[
                { value: '15m', label: '15m' },
                { value: '1h', label: '1h' },
                { value: '4h', label: '4h' },
                { value: '1d', label: '1d' },
                { value: '7d', label: '7d' },
              ]}
            />
            <Select
              size="small"
              value={liveMode}
              onChange={setLiveMode}
              style={{ width: 88 }}
              prefix={
                <span
                  style={{
                    display: 'inline-block',
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    border: `1.5px solid ${liveMode === 'off' ? TOKENS.textTertiary : TOKENS.primary}`,
                    background: liveMode === 'off' ? 'transparent' : TOKENS.primary,
                    marginRight: 2,
                  }}
                />
              }
              suffixIcon={
                <span style={{ fontSize: 10, color: TOKENS.textTertiary, lineHeight: 1 }}>↑↓</span>
              }
              popupMatchSelectWidth={100}
              options={[
                { value: 'off', label: 'off' },
                { value: '1s', label: '1s' },
                { value: '2s', label: '2s' },
                { value: '5s', label: '5s' },
                { value: '30s', label: '30s' },
                { value: '1m', label: '1m' },
              ]}
            />
          </Space>
        </div>

        <Row gutter={[12, 12]}>
          {/* 左侧分面 */}
          <Col xs={24} lg={5}>
            <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
              <Title level={5} style={{ margin: 0, marginBottom: 10 }}>
                分面筛选
              </Title>
              {/* 状态(对齐 datadog — 状态在最前) */}
              <FacetBox
                title="状态"
                items={[
                  { key: 'error', label: '错误', count: 60, color: TOKENS.danger },
                  { key: 'ok', label: '正常', count: 5763, color: TOKENS.success },
                ]}
              />
              <FacetBox
                title="服务"
                items={[
                  { key: 'api-gateway', label: 'api-gateway', count: 1145 },
                  { key: 'checkout-api', label: 'checkout-api', count: 984 },
                  { key: 'user-api', label: 'user-api', count: 744 },
                  { key: 'catalog-api', label: 'catalog-api', count: 727 },
                  { key: 'inventory-svc', label: 'inventory-svc', count: 644 },
                  { key: 'payment-svc', label: 'payment-svc', count: 629 },
                  { key: 'auth-svc', label: 'auth-svc', count: 438 },
                  { key: 'web-storefront', label: 'web-storefront', count: 429 },
                  { key: 'notification-worker', label: 'notification-worker', count: 83 },
                ]}
              />
              <FacetBox
                title="环境"
                items={[
                  { key: 'production', label: 'production', count: 4427 },
                  { key: 'staging', label: 'staging', count: 1396 },
                ]}
              />
              <FacetBox
                title="SPAN 类型"
                items={[
                  { key: 'client', label: 'CLIENT', count: 3491 },
                  { key: 'server', label: 'SERVER', count: 2082 },
                  { key: 'producer', label: 'PRODUCER', count: 205 },
                  { key: 'consumer', label: 'CONSUMER', count: 45 },
                ]}
              />
              {/* 耗时范围筛选(对齐 datadog "耗时" 分面) */}
              <FacetRange title="耗时" min={0} max={2000} unit="ms" />
            </div>
          </Col>

          {/* 右侧主区 */}
          <Col xs={24} lg={19}>
            {/* 顶部统计行(对齐 datadog:大字 X.XX traces/s · 命中 N + 明细/聚合切换在右) */}
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-end',
                justifyContent: 'space-between',
                padding: '0 4px 12px',
              }}
            >
              <div>
                <span style={{ fontSize: 28, fontWeight: 700, color: TOKENS.text }}>
                  {entity === 'traces' ? '0.00' : '0.01'}
                </span>
                <Text type="secondary" style={{ marginLeft: 8, fontSize: 13 }}>
                  {entity}/s · 命中 {entity === 'traces' ? 400 : 5823}
                </Text>
              </div>
              <Segmented
                value={view}
                onChange={(v) => setView(v as 'detail' | 'aggregate')}
                options={[
                  { value: 'detail', label: '明细' },
                  { value: 'aggregate', label: '聚合' },
                ]}
              />
            </div>

            {/* 时延散点图 — 仅明细模式显示(时序分布是筛选器,点击后更新检索条件,聚合不需要) */}
            {view === 'detail' && (
            <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 12 }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 8,
                }}
              >
                <Space size={8}>
                  <Title level={5} style={{ margin: 0 }}>
                    时序分布
                  </Title>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    在图上拖选一段时间锁定结果
                  </Text>
                </Space>
                <Space size={4}>
                  <span style={{ fontSize: 11, color: TOKENS.textTertiary, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: TOKENS.primary, display: 'inline-block' }} />
                    正常
                  </span>
                  <span style={{ fontSize: 11, color: TOKENS.danger, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: TOKENS.danger, display: 'inline-block' }} />
                    错误
                  </span>
                </Space>
              </div>
              <ScatterChartMock />
            </div>
            )}

            {/* 明细 / 聚合 内容区 */}
            <div style={{ ...surfaceCardStyle, padding: '0' }}>
              {view === 'detail' ? (
                <DetailTable
                  entity={entity}
                  TRACES={TRACES}
                  view={view}
                />
              ) : (
                <AggregateView
                  aggForm={aggForm}
                  setAggForm={setAggForm}
                  aggSort={aggSort}
                  setAggSort={setAggSort}
                  aggDim={aggDim}
                  setAggDim={setAggDim}
                />
              )}
            </div>
          </Col>
        </Row>
      </Content>
    </div>
  );
}

/* ============================================================
 * 明细列表(Traces / Spans)— 对齐 datadog 明细 tab
 * ============================================================ */
/* ============================================================
 * 明细列表(Traces / Spans)— 对齐 datadog 明细 tab
 * Traces 列表:Trace ID / 入口服务·操作 / 状态 / 总耗时 / Span 数 / 开始时间
 * Spans 列表:服务·操作 / SpanKind / HTTP / 自身耗时 / 状态 / Trace
 * ============================================================ */
function DetailTable({
  entity,
  TRACES,
}: {
  entity: 'traces' | 'spans';
  view: 'detail' | 'aggregate';
  TRACES: any[];
}) {
  const tracesColumns = [
    {
      title: '入口服务',
      render: (_: unknown, r: any) => (
        <Space direction="vertical" size={2}>
          <a style={{ color: TOKENS.text, fontWeight: 600, fontSize: 13 }}>{r.service}</a>
          <span style={{ fontSize: 11, color: TOKENS.textTertiary, fontFamily: 'monospace' }}>
            {r.traceId?.slice(0, 16)}
          </span>
        </Space>
      ),
    },
    {
      title: '资源',
      render: (_: unknown, r: any) => (
        <span style={{ fontFamily: 'monospace', fontSize: 12, color: TOKENS.text }}>
          {r.operation}
        </span>
      ),
    },
    {
      title: '总耗时',
      dataIndex: 'duration',
      width: 110,
      align: 'right' as const,
      render: (v: number) => {
        const danger = v > 400;
        return (
          <span
            style={{
              fontVariantNumeric: 'tabular-nums',
              color: danger ? TOKENS.danger : TOKENS.text,
              fontWeight: danger ? 600 : 400,
              textDecoration: 'underline',
              textUnderlineOffset: 3,
            }}
          >
            {v} ms
          </span>
        );
      },
    },
    {
      title: '跨度数',
      dataIndex: 'spanCount',
      width: 80,
      align: 'right' as const,
      render: (v: number) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (v: string, r: any) =>
        v === 'error' ? (
          <Tooltip title={r.errorSpan}>
            <span style={{ color: TOKENS.danger, fontSize: 12, fontWeight: 500 }}>
              <CloseCircleOutlined /> 错误数 {r.errorCount ?? 1}
            </span>
          </Tooltip>
        ) : (
          <span style={{ color: TOKENS.success, fontSize: 12, fontWeight: 500 }}>
            <CheckOutlined /> 正常
          </span>
        ),
    },
    {
      title: '时间',
      dataIndex: 'start',
      width: 100,
      render: () => <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>6 天前</span>,
    },
  ];

  const spansColumns = [
    {
      title: '服务',
      render: (_: unknown, r: any) => (
        <Space direction="vertical" size={2}>
          <a style={{ color: TOKENS.text, fontWeight: 600, fontSize: 13 }}>{r.service}</a>
          <span style={{ fontSize: 11, color: TOKENS.textTertiary }}>{r.kind}</span>
        </Space>
      ),
    },
    {
      title: '资源',
      render: (_: unknown, r: any) => (
        <span style={{ fontFamily: 'monospace', fontSize: 12, color: TOKENS.text }}>
          {r.operation}
        </span>
      ),
    },
    {
      title: 'HTTP',
      width: 130,
      render: (_: unknown, r: any) => (
        <Space size={4}>
          {r.method && (
            <span style={{ fontFamily: 'monospace', fontSize: 12, color: TOKENS.textSecondary }}>
              {r.method}
            </span>
          )}
          {r.statusCode && (
            <span
              style={{
                fontFamily: 'monospace',
                fontSize: 12,
                color: r.status === 'error' ? TOKENS.danger : TOKENS.textSecondary,
                fontWeight: 500,
              }}
            >
              {r.statusCode}
            </span>
          )}
        </Space>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration',
      width: 110,
      align: 'right' as const,
      render: (v: number) => {
        const danger = v > 1000;
        return (
          <span
            style={{
              fontVariantNumeric: 'tabular-nums',
              color: danger ? TOKENS.danger : TOKENS.text,
              fontWeight: danger ? 600 : 400,
              textDecoration: 'underline',
              textUnderlineOffset: 3,
            }}
          >
            {v} ms
          </span>
        );
      },
    },
    {
      title: '时间',
      width: 100,
      render: () => <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>6 天前</span>,
    },
  ];

  return (
    <Table
      size="middle"
      rowKey="key"
      pagination={{ pageSize: 10, showSizeChanger: false }}
      dataSource={TRACES}
      columns={entity === 'traces' ? tracesColumns : spansColumns}
    />
  );
}

/* ============================================================
 * 聚合视图(对齐 datadog 5 个子 Tab)
 *  - Top 榜(蓝条请求数排行)
 *  - 错误率(红条错误率排行)
 *  - 按服务(6 列表格,请求数/错误数/错误率/平均/P95)
 *  - 按端点(同上,按 endpoint 维度)
 *  - 按版本(同上,按 version 维度)
 * ============================================================ */
const AGG_BY_SERVICE = [
  { key: 'api-gateway', requestCount: 1145, errorCount: 4, errorRate: 0.3, avg: 163, p95: 410 },
  { key: 'checkout-api', requestCount: 984, errorCount: 4, errorRate: 0.4, avg: 119, p95: 298 },
  { key: 'user-api', requestCount: 744, errorCount: 2, errorRate: 0.3, avg: 26.5, p95: 56.8 },
  { key: 'catalog-api', requestCount: 727, errorCount: 4, errorRate: 0.6, avg: 21.5, p95: 61.1 },
  { key: 'inventory-svc', requestCount: 644, errorCount: 7, errorRate: 1.1, avg: 17.8, p95: 48.7 },
  { key: 'payment-svc', requestCount: 629, errorCount: 34, errorRate: 5.4, avg: 103, p95: 220 },
  { key: 'auth-svc', requestCount: 438, errorCount: 3, errorRate: 0.7, avg: 10.5, p95: 21.8 },
  { key: 'web-storefront', requestCount: 429, errorCount: 2, errorRate: 0.5, avg: 296, p95: 481 },
  { key: 'notification-worker', requestCount: 83, errorCount: 0, errorRate: 0, avg: 56.8, p95: 91.6 },
];

const AGG_BY_ENDPOINT = [
  { key: 'POST /api/checkout', requestCount: 524, errorCount: 8, errorRate: 1.5, avg: 245, p95: 612 },
  { key: 'GET /api/user/profile', requestCount: 421, errorCount: 22, errorRate: 5.2, avg: 88, p95: 196 },
  { key: 'GET /api/catalog', requestCount: 450, errorCount: 20, errorRate: 4.4, avg: 67.2, p95: 28 },
  { key: 'POST /cart/checkout', requestCount: 470, errorCount: 23, errorRate: 4.9, avg: 364, p95: 19 },
  { key: 'GET /product/:id', requestCount: 163, errorCount: 19, errorRate: 11.7, avg: 320, p95: 17 },
  { key: 'POST /api/pay', requestCount: 383, errorCount: 18, errorRate: 4.7, avg: 104, p95: 18 },
  { key: 'POST /cart/checkout', requestCount: 435, errorCount: 21, errorRate: 4.8, avg: 67.2, p95: 28 },
  { key: 'GET /api/order', requestCount: 312, errorCount: 5, errorRate: 1.6, avg: 56, p95: 132 },
];

const AGG_BY_VERSION = [
  { key: '2.8.0', requestCount: 1145, errorCount: 4, errorRate: 0.3, avg: 163, p95: 410 },
  { key: '2.0.7', requestCount: 744, errorCount: 2, errorRate: 0.3, avg: 26.5, p95: 56.8 },
  { key: '1.9.2', requestCount: 727, errorCount: 4, errorRate: 0.6, avg: 21.5, p95: 61.1 },
  { key: '1.4.1', requestCount: 644, errorCount: 7, errorRate: 1.1, avg: 17.8, p95: 48.7 },
  { key: '3.1.3', requestCount: 527, errorCount: 3, errorRate: 0.6, avg: 120, p95: 302 },
  { key: '3.1.4', requestCount: 457, errorCount: 1, errorRate: 0.2, avg: 118, p95: 298 },
  { key: '3.0.2', requestCount: 438, errorCount: 3, errorRate: 0.7, avg: 10.5, p95: 21.8 },
  { key: '4.2.1', requestCount: 339, errorCount: 23, errorRate: 6.8, avg: 104, p95: 221 },
  { key: '5.3.0', requestCount: 290, errorCount: 11, errorRate: 3.8, avg: 102, p95: 215 },
  { key: '1.2.0', requestCount: 83, errorCount: 0, errorRate: 0, avg: 56.8, p95: 91.6 },
];

/** 蓝条 Top 榜(请求数) */
function TopRankingTable({ data }: { data: { key: string; requestCount: number }[] }) {
  const max = Math.max(...data.map((d) => d.requestCount));
  return (
    <div style={{ padding: '8px 0' }}>
      {data.map((d, i) => (
        <div
          key={d.key}
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '8px 16px',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 28,
              textAlign: 'right',
              color: TOKENS.textTertiary,
              fontSize: 12,
            }}
          >
            {i + 1}
          </div>
          <div
            style={{
              minWidth: 140,
              fontSize: 13,
              color: TOKENS.primary,
            }}
          >
            {d.key}
          </div>
          <div
            style={{
              flex: 1,
              height: 8,
              background: '#eef2f6',
              borderRadius: 4,
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                position: 'absolute',
                inset: 0,
                width: `${(d.requestCount / max) * 100}%`,
                background: TOKENS.primary,
                borderRadius: 4,
              }}
            />
          </div>
          <div
            style={{
              width: 80,
              textAlign: 'right',
              fontFamily: 'monospace',
              fontSize: 13,
              color: TOKENS.text,
            }}
          >
            {d.requestCount}
          </div>
        </div>
      ))}
    </div>
  );
}

/** 红条错误率 Top 榜 */
function ErrorRateRankingTable({ data }: { data: { key: string; errorRate: number; requestCount: number }[] }) {
  return (
    <div style={{ padding: '8px 0' }}>
      {data.map((d, i) => (
        <div
          key={d.key}
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '8px 16px',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 28,
              textAlign: 'right',
              color: TOKENS.textTertiary,
              fontSize: 12,
            }}
          >
            {i + 1}
          </div>
          <div
            style={{
              minWidth: 140,
              fontSize: 13,
              color: TOKENS.primary,
            }}
          >
            {d.key}
          </div>
          <div
            style={{
              flex: 1,
              height: 8,
              background: '#fdecec',
              borderRadius: 4,
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                position: 'absolute',
                inset: 0,
                width: `${Math.min(d.errorRate * 10, 100)}%`,
                background: TOKENS.danger,
                borderRadius: 4,
              }}
            />
          </div>
          <div
            style={{
              width: 80,
              textAlign: 'right',
              fontFamily: 'monospace',
              fontSize: 13,
              color: TOKENS.danger,
              fontWeight: 600,
            }}
          >
            {d.errorRate.toFixed(1)}%
          </div>
        </div>
      ))}
    </div>
  );
}

/** 通用 6 列聚合分析表格(按服务 / 按端点 / 按版本) */
function AggregateTable({
  data,
  dimension,
}: {
  data: typeof AGG_BY_SERVICE;
  dimension: 'service' | 'endpoint' | 'version' | 'env';
}) {
  return (
    <Table
      size="middle"
      rowKey="key"
      pagination={false}
      dataSource={data}
      columns={[
        {
          title: dimension === 'service' ? '按服务' : dimension === 'endpoint' ? '按端点' : '按版本',
          dataIndex: 'key',
          render: (v: string) => (
            <a style={{ color: TOKENS.primary, fontSize: 13 }}>{v}</a>
          ),
        },
        {
          title: '请求数',
          dataIndex: 'requestCount',
          sorter: (a: any, b: any) => a.requestCount - b.requestCount,
          defaultSortOrder: 'descend' as const,
          align: 'right' as const,
          render: (v: number) => (
            <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{v}</span>
          ),
        },
        {
          title: '错误数',
          dataIndex: 'errorCount',
          align: 'right' as const,
          render: (v: number) => (
            <span style={{ color: v > 10 ? TOKENS.danger : TOKENS.text, fontVariantNumeric: 'tabular-nums' }}>
              {v}
            </span>
          ),
        },
        {
          title: '错误率',
          dataIndex: 'errorRate',
          align: 'right' as const,
          sorter: (a: any, b: any) => a.errorRate - b.errorRate,
          render: (v: number) => (
            <span
              style={{
                color: v > 1 ? TOKENS.danger : TOKENS.text,
                fontWeight: 600,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {v.toFixed(1)}%
            </span>
          ),
        },
        {
          title: '平均',
          dataIndex: 'avg',
          align: 'right' as const,
          render: (v: number) => (
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v}ms</span>
          ),
        },
        {
          title: 'P95 耗时',
          dataIndex: 'p95',
          align: 'right' as const,
          render: (v: number) => (
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v}ms</span>
          ),
        },
      ]}
    />
  );
}

function AggregateView({
  aggForm,
  setAggForm,
  aggSort,
  setAggSort,
  aggDim,
  setAggDim,
}: {
  aggForm: 'top' | 'table';
  setAggForm: (v: 'top' | 'table') => void;
  aggSort: 'count' | 'error' | 'p95';
  setAggSort: (v: 'count' | 'error' | 'p95') => void;
  aggDim: 'service' | 'endpoint' | 'version' | 'env';
  setAggDim: (v: 'service' | 'endpoint' | 'version' | 'env') => void;
}) {
  const dataByDim: Record<
    'service' | 'endpoint' | 'version' | 'env',
    Array<{
      key: string;
      requestCount: number;
      errorCount: number;
      errorRate: number;
      avg: number;
      p95: number;
    }>
  > = {
    service: AGG_BY_SERVICE as any,
    endpoint: AGG_BY_ENDPOINT as any,
    version: AGG_BY_VERSION as any,
    env: [
      { key: 'production', requestCount: 4427, errorCount: 88, errorRate: 2.0, avg: 142, p95: 358 },
      { key: 'staging', requestCount: 1396, errorCount: 12, errorRate: 0.9, avg: 98, p95: 220 },
    ],
  };

  return (
    <div>
      {/* 顶部:大字"Top 榜" + 4 维度 tab + 右上 5 个排序/视图 chip */}
      <div
        style={{
          padding: '10px 16px',
          borderTop: `1px solid ${TOKENS.border}`,
          background: '#fafbfc',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        {/* 左侧:大字标题 + 4 维度 tab */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 18, fontWeight: 600, color: TOKENS.text }}>
            Top 榜
          </span>
          <Tabs
            size="small"
            activeKey={aggDim}
            onChange={(k) => setAggDim(k as typeof aggDim)}
            items={[
              { key: 'service', label: '按服务' },
              { key: 'endpoint', label: '按端点' },
              { key: 'version', label: '按版本' },
              { key: 'env', label: '按环境' },
            ]}
          />
        </div>
        {/* 右侧:5 个 chip(3 排序 + Top 榜/表格) */}
        <Space size={8} style={{ marginLeft: 'auto' }}>
          <Segmented
            size="small"
            value={aggSort}
            onChange={(v) => setAggSort(v as 'count' | 'error' | 'p95')}
            options={[
              { value: 'count', label: '请求数' },
              { value: 'error', label: '错误率' },
              { value: 'p95', label: 'P95 耗时' },
            ]}
          />
          <Segmented
            size="small"
            value={aggForm}
            onChange={(v) => setAggForm(v as 'top' | 'table')}
            options={[
              { value: 'top', label: 'Top 榜' },
              { value: 'table', label: '表格' },
            ]}
          />
        </Space>
      </div>
      <div style={{ padding: '0 16px 16px' }}>
        {aggForm === 'top' && aggSort === 'count' && (
          <TopRankingTable data={dataByDim[aggDim]} />
        )}
        {aggForm === 'top' && aggSort === 'error' && (
          <ErrorRateRankingTable data={dataByDim[aggDim]} />
        )}
        {aggForm === 'table' && (
          <AggregateTable data={dataByDim[aggDim]} dimension={aggDim} />
        )}
      </div>
    </div>
  );
}

function ScatterChartMock() {
  // 简单的散点图 SVG(82 个点)
  const w = 760;
  const h = 180;
  const points = Array.from({ length: 82 }, (_, i) => {
    const x = (i / 82) * w + Math.random() * 8;
    // 大部分点 < 500ms,少量长尾
    const bucket = Math.random();
    let y;
    if (bucket < 0.7) y = h - 20 - Math.random() * 60;
    else if (bucket < 0.95) y = h - 60 - Math.random() * 50;
    else y = h - 100 - Math.random() * 60;
    const isError = i % 7 === 0; // 12/82 ≈ 15% 错误
    return { x, y, isError };
  });
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {/* 背景网格 */}
      {[0, 1, 2, 3].map((i) => (
        <line
          key={i}
          x1={0}
          y1={(h / 4) * i + 10}
          x2={w}
          y2={(h / 4) * i + 10}
          stroke={TOKENS.border}
          strokeDasharray="2,4"
        />
      ))}
      {/* 数据点 */}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={4}
          fill={p.isError ? TOKENS.danger : TOKENS.primary}
          opacity={0.7}
        />
      ))}
      {/* Y 轴标签 */}
      <text x={4} y={14} fontSize={10} fill={TOKENS.textTertiary}>
        2s
      </text>
      <text x={4} y={h / 2} fontSize={10} fill={TOKENS.textTertiary}>
        1s
      </text>
      <text x={4} y={h - 4} fontSize={10} fill={TOKENS.textTertiary}>
        0
      </text>
    </svg>
  );
}

/* ============================================================
 * 2) TraceDetail · Trace 详情(瀑布图/火焰图/跨度列表 三视图)
 *    严格对齐 datadog Trace 详情页:breadcrumb + 概览 stat strip + 三视图 tabs + 服务执行占比 + Span 详情
 * ============================================================ */

/** 服务色板 — datadog 风格按服务稳定分配颜色 */
const SERVICE_COLORS: Record<string, string> = {
  'api-gateway': '#1f77ff',
  'catalog-api': '#7c3aed',
  'checkout-api': '#ec4899',
  'payment-svc': '#f59e0b',
  'inventory-svc': '#10b981',
  'user-api': '#a3e635',
  'auth-svc': '#f5b97c',
};

/** Span 树(对齐 datadog 截图 7 服务 / 22 跨度数) */
interface SpanRow {
  id: string;
  parent: string | null;
  depth: number;
  name: string;
  service: string;
  kind: 'SERVER' | 'CLIENT' | 'INTERNAL' | 'PRODUCER' | 'CONSUMER';
  start: number;
  dur: number;
  selfDur: number;
  status: 'ok' | 'error';
  isKeyPath: boolean;
}
const SPANS: SpanRow[] = [
  // 根:api-gateway GET /api/user/profile
  { id: 's0', parent: null, depth: 0, name: 'GET /api/user/profile', service: 'api-gateway', kind: 'SERVER', start: 0, dur: 421, selfDur: 0, status: 'error', isKeyPath: true },
  { id: 's1', parent: 's0', depth: 1, name: 'GET /catalog', service: 'api-gateway', kind: 'CLIENT', start: 0, dur: 47, selfDur: 1, status: 'ok', isKeyPath: false },
  { id: 's2', parent: 's1', depth: 2, name: 'GET /catalog/search', service: 'api-gateway', kind: 'CLIENT', start: 0, dur: 46, selfDur: 0, status: 'ok', isKeyPath: false },
  { id: 's3', parent: 's2', depth: 3, name: 'SELECT products', service: 'catalog-api', kind: 'CLIENT', start: 0, dur: 11, selfDur: 11, status: 'ok', isKeyPath: false },
  { id: 's4', parent: 's2', depth: 3, name: 'GET catalog:*', service: 'catalog-api', kind: 'CLIENT', start: 12, dur: 5, selfDur: 5, status: 'ok', isKeyPath: false },
  // POST /checkout
  { id: 's5', parent: 's0', depth: 1, name: 'POST /checkout', service: 'api-gateway', kind: 'CLIENT', start: 60, dur: 298, selfDur: 2, status: 'ok', isKeyPath: true },
  { id: 's6', parent: 's5', depth: 2, name: 'POST /checkout', service: 'checkout-api', kind: 'SERVER', start: 60, dur: 296, selfDur: 1, status: 'ok', isKeyPath: true },
  { id: 's7', parent: 's6', depth: 3, name: 'POST /charge', service: 'checkout-api', kind: 'CLIENT', start: 100, dur: 195, selfDur: 2, status: 'ok', isKeyPath: true },
  { id: 's8', parent: 's7', depth: 4, name: 'POST /charge', service: 'payment-svc', kind: 'SERVER', start: 100, dur: 193, selfDur: 96, status: 'error', isKeyPath: true },
  { id: 's9', parent: 's8', depth: 5, name: 'POST stripe.charge', service: 'payment-svc', kind: 'CLIENT', start: 100, dur: 87, selfDur: 87, status: 'ok', isKeyPath: true },
  { id: 's10', parent: 's9', depth: 6, name: 'INSERT payments', service: 'payment-svc', kind: 'CLIENT', start: 100, dur: 9, selfDur: 9, status: 'ok', isKeyPath: false },
  { id: 's11', parent: 's6', depth: 3, name: 'POST /reserve', service: 'checkout-api', kind: 'CLIENT', start: 200, dur: 50, selfDur: 1, status: 'ok', isKeyPath: false },
  { id: 's12', parent: 's11', depth: 4, name: 'POST /reserve', service: 'inventory-svc', kind: 'SERVER', start: 200, dur: 49, selfDur: 2, status: 'ok', isKeyPath: false },
  { id: 's13', parent: 's12', depth: 5, name: 'DECR stock:*', service: 'inventory-svc', kind: 'CLIENT', start: 200, dur: 2, selfDur: 2, status: 'ok', isKeyPath: false },
  { id: 's14', parent: 's12', depth: 5, name: 'publish inventory.reserved', service: 'inventory-svc', kind: 'CLIENT', start: 220, dur: 4, selfDur: 4, status: 'ok', isKeyPath: false },
  { id: 's15', parent: 's6', depth: 3, name: 'INSERT orders', service: 'checkout-api', kind: 'CLIENT', start: 260, dur: 10, selfDur: 10, status: 'ok', isKeyPath: false },
  // GET /user
  { id: 's16', parent: 's0', depth: 1, name: 'GET /user', service: 'api-gateway', kind: 'CLIENT', start: 305, dur: 56, selfDur: 1, status: 'ok', isKeyPath: false },
  { id: 's17', parent: 's16', depth: 2, name: 'GET /user', service: 'user-api', kind: 'SERVER', start: 305, dur: 55, selfDur: 1, status: 'ok', isKeyPath: false },
  { id: 's18', parent: 's17', depth: 3, name: 'SELECT users', service: 'user-api', kind: 'CLIENT', start: 310, dur: 16, selfDur: 16, status: 'ok', isKeyPath: false },
  // POST /verify
  { id: 's19', parent: 's0', depth: 1, name: 'POST /verify', service: 'api-gateway', kind: 'CLIENT', start: 365, dur: 20, selfDur: 1, status: 'ok', isKeyPath: false },
  { id: 's20', parent: 's19', depth: 2, name: 'POST /verify', service: 'user-api', kind: 'SERVER', start: 365, dur: 19, selfDur: 19, status: 'ok', isKeyPath: false },
  { id: 's21', parent: 's0', depth: 1, name: 'auth-svc.token.refresh', service: 'api-gateway', kind: 'INTERNAL', start: 390, dur: 5, selfDur: 5, status: 'ok', isKeyPath: false },
];
const TRACE_TOTAL_DUR = 421;
const TRACE_SERVICES = Array.from(new Set(SPANS.map((s) => s.service)));

function WaterfallChart({
  selectedId,
  onSelect,
}: {
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const padLeft = 240;
  const chartW = 580;
  const rowH = 22;
  const totalDur = TRACE_TOTAL_DUR;
  const ticks = [0, 84, 168, 252, 337];

  return (
    <div style={{ position: 'relative' }}>
      {/* 时间轴 */}
      <div
        style={{
          position: 'relative',
          height: 24,
          marginLeft: padLeft,
          width: chartW,
          borderBottom: `1px solid ${TOKENS.border}`,
        }}
      >
        {ticks.map((t) => (
          <div
            key={t}
            style={{
              position: 'absolute',
              left: (t / totalDur) * chartW,
              transform: 'translateX(-50%)',
              fontSize: 10,
              color: TOKENS.textTertiary,
              top: 4,
            }}
          >
            {t}ms
          </div>
        ))}
      </div>
      {/* Span 行 */}
      <div>
        {SPANS.map((s) => {
          const isSel = s.id === selectedId;
          const x = (s.start / totalDur) * chartW;
          const w = Math.max(2, (s.dur / totalDur) * chartW);
          const color = s.status === 'error' ? TOKENS.danger : SERVICE_COLORS[s.service];
          return (
            <div
              key={s.id}
              onClick={() => onSelect(s.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                height: rowH,
                cursor: 'pointer',
                background: isSel ? TOKENS.primarySoft : 'transparent',
                borderLeft: isSel ? `2px solid ${TOKENS.primary}` : '2px solid transparent',
              }}
            >
              {/* 左列:缩进 + operation + service */}
              <div
                style={{
                  width: padLeft,
                  paddingLeft: 8 + s.depth * 12,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 12,
                  overflow: 'hidden',
                }}
              >
                <span
                  style={{
                    width: 4,
                    height: 4,
                    borderRadius: '50%',
                    background: SERVICE_COLORS[s.service],
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    color: TOKENS.text,
                    fontFamily: 'ui-monospace, monospace',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontWeight: s.isKeyPath ? 600 : 400,
                  }}
                >
                  {s.name}
                </span>
                <span style={{ color: TOKENS.textTertiary, fontSize: 11, flexShrink: 0 }}>
                  {s.service}
                </span>
              </div>
              {/* 右列:条 + 时长 */}
              <div style={{ position: 'relative', width: chartW, height: rowH }}>
                {s.parent && (
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: rowH / 2 - 1,
                      width: x,
                      height: 1,
                      background: TOKENS.border,
                    }}
                  />
                )}
                <div
                  style={{
                    position: 'absolute',
                    left: x,
                    top: 3,
                    width: w,
                    height: rowH - 8,
                    background: color,
                    opacity: s.isKeyPath ? 1 : 0.7,
                    borderRadius: 2,
                    boxShadow: s.status === 'error' ? `0 0 0 1px ${TOKENS.danger}` : 'none',
                  }}
                >
                  {w > 30 && (
                    <span
                      style={{
                        position: 'absolute',
                        right: -42,
                        top: 0,
                        lineHeight: `${rowH - 8}px`,
                        fontSize: 10,
                        color: TOKENS.textSecondary,
                        fontFamily: 'ui-monospace, monospace',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {s.dur}ms
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** 火焰图(icicle 冰柱图):按调用栈层级递归切分宽度,颜色按服务 */
function FlameChart({ onSelect }: { onSelect: (id: string) => void }) {
  const totalDur = TRACE_TOTAL_DUR;
  const w = 820;
  const rowH = 24;
  const root = SPANS[0];

  // 预计算每层的最深深度
  const depthCache = new Map<string, number>();
  function getDepth(span: SpanRow): number {
    if (depthCache.has(span.id)) return depthCache.get(span.id)!;
    const children = SPANS.filter((s) => s.parent === span.id);
    const d = children.length === 0 ? 0 : 1 + Math.max(...children.map(getDepth));
    depthCache.set(span.id, d);
    return d;
  }
  const maxDepth = getDepth(root);

  // 递归画一个 span:父自己 + 下一层子
  function renderSpan(span: SpanRow, rowIdx: number): React.ReactNode {
    const children = SPANS.filter((s) => s.parent === span.id).sort((a, b) => a.start - b.start);
    const blocks: React.ReactNode[] = [];

    // 父方块
    const color = span.status === 'error' ? TOKENS.danger : SERVICE_COLORS[span.service];
    const opacity = rowIdx === 0 ? 0.95 : 0.85;
    const wPx = Math.max(2, (span.dur / totalDur) * w);
    const xPx = (span.start / totalDur) * w;
    const canShowText = wPx > 60;
    blocks.push(
      <div
        key={span.id}
        onClick={() => onSelect(span.id)}
        title={`${span.service} · ${span.name} · ${span.dur}ms`}
        style={{
          position: 'absolute',
          left: xPx,
          top: rowIdx * rowH,
          width: wPx,
          height: rowH - 2,
          background: color,
          opacity,
          cursor: 'pointer',
          overflow: 'hidden',
          padding: '0 6px',
          color: '#fff',
          fontSize: 11,
          lineHeight: `${rowH - 2}px`,
          fontFamily: 'ui-monospace, monospace',
          whiteSpace: 'nowrap',
          textOverflow: 'ellipsis',
          border: span.status === 'error' ? `1.5px solid #fff` : `1px solid rgba(255,255,255,0.4)`,
          boxShadow: span.isKeyPath ? 'inset 0 -2px 0 rgba(255,255,255,0.7)' : 'none',
        }}
      >
        {canShowText ? span.name : ''}
      </div>,
    );

    // 子方块
    children.forEach((c) => {
      blocks.push(...(renderSpan(c, rowIdx + 1) as React.ReactNode[]));
    });
    return blocks;
  }

  const totalH = (maxDepth + 1) * rowH + 4;
  return (
    <div
      style={{
        position: 'relative',
        width: w,
        height: totalH,
        background: TOKENS.bg,
        borderRadius: 4,
        overflow: 'hidden',
      }}
    >
      {renderSpan(root, 0)}
    </div>
  );
}

/** 跨度列表:搜索 + 列表行 */
function SpanList({
  selectedId,
  onSelect,
  query,
  setQuery,
}: {
  selectedId: string;
  onSelect: (id: string) => void;
  query: string;
  setQuery: (v: string) => void;
}) {
  const filtered = SPANS.filter(
    (s) =>
      !query ||
      s.name.toLowerCase().includes(query.toLowerCase()) ||
      s.service.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div>
      <Input
        placeholder="搜索跨度名 / 服务"
        prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        allowClear
        style={{ marginBottom: 12 }}
      />
      <div style={{ border: `1px solid ${TOKENS.border}`, borderRadius: 6, overflow: 'hidden' }}>
        {filtered.map((s) => {
          const isSel = s.id === selectedId;
          return (
            <div
              key={s.id}
              onClick={() => onSelect(s.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '8px 12px',
                borderBottom: `1px solid ${TOKENS.border}`,
                background: isSel ? TOKENS.primarySoft : 'transparent',
                borderLeft: isSel ? `2px solid ${TOKENS.primary}` : '2px solid transparent',
                cursor: 'pointer',
                fontSize: 13,
                paddingLeft: 14,
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  background: s.status === 'error' ? TOKENS.danger : SERVICE_COLORS[s.service],
                  marginRight: 10,
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  flex: 1,
                  fontFamily: 'ui-monospace, monospace',
                  paddingLeft: s.depth * 12,
                  color: TOKENS.text,
                  fontWeight: s.isKeyPath ? 600 : 400,
                }}
              >
                {s.name}
              </span>
              <span style={{ color: TOKENS.textTertiary, fontSize: 12, width: 120, textAlign: 'right' }}>
                {s.service}
              </span>
              <span
                style={{
                  width: 70,
                  textAlign: 'right',
                  fontVariantNumeric: 'tabular-nums',
                  color: s.dur > 100 ? TOKENS.danger : TOKENS.text,
                }}
              >
                {s.dur}ms
                {s.status === 'error' && (
                  <span style={{ color: TOKENS.danger, marginLeft: 6 }}>⚠</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SpanDetailPanel({ selectedId }: { selectedId: string }) {
  const s = SPANS.find((x) => x.id === selectedId) ?? SPANS[8];
  const stack =
    s.status === 'error'
      ? 'java.lang.NullPointerException: Cannot invoke "String.length()" because "orderId" is null\n  at com.bklite.payment.PaymentService.charge(PaymentService.java:142)\n  at com.bklite.payment.PaymentController.checkout(PaymentController.java:88)\n  ...'
      : null;
  return (
    <div>
      {/* 顶部:操作名 + 服务 + kind + 操作按钮 */}
      <div style={{ marginBottom: 10 }}>
        <Text strong style={{ fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>
          {s.name}
        </Text>
      </div>
      <Space size={6} wrap style={{ marginBottom: 12 }}>
        <a style={{ color: TOKENS.textSecondary, fontSize: 12 }}>{s.service}</a>
        <Tag style={{ margin: 0, fontSize: 11 }}>{s.kind}</Tag>
        <a style={{ color: TOKENS.primary, fontSize: 12 }}>查看端点</a>
        <a
          style={{
            color: TOKENS.danger,
            fontSize: 12,
            border: `1px solid ${TOKENS.danger}`,
            padding: '0 6px',
            borderRadius: 3,
          }}
        >
          错误追踪
        </a>
      </Space>
      {stack && (
        <pre
          style={{
            background: '#fef2f2',
            border: `1px solid #fecaca`,
            padding: '8px 10px',
            borderRadius: 4,
            fontSize: 11,
            color: '#7f1d1d',
            margin: '0 0 12px 0',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            fontFamily: 'ui-monospace, monospace',
          }}
        >
          {stack}
        </pre>
      )}
      <Tabs
        size="small"
        defaultActiveKey="overview"
        items={[
          {
            key: 'overview',
            label: '概览',
            children: (
              <div style={{ fontSize: 12 }}>
                {[
                  ['总耗时', `${s.dur}ms`],
                  ['自身耗时', `${s.selfDur}ms`],
                  ['起始偏移', `+${s.start}.0ms`],
                  ['状态', s.status === 'error' ? 'ERROR' : 'OK'],
                ].map(([k, v], i) => (
                  <div
                    key={k}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      padding: '6px 0',
                      borderBottom: i < 3 ? `1px dashed ${TOKENS.border}` : 'none',
                    }}
                  >
                    <span style={{ color: TOKENS.textTertiary }}>{k}</span>
                    <span
                      style={{
                        color: v === 'ERROR' ? TOKENS.danger : TOKENS.text,
                        fontFamily: 'ui-monospace, monospace',
                        fontWeight: v === 'ERROR' ? 600 : 400,
                      }}
                    >
                      {String(v)}
                    </span>
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: 'attrs',
            label: '属性',
            children: (
              <div style={{ fontSize: 12 }}>
                {[
                  ['service.name', s.service],
                  ['service.version', 'v5.3.0'],
                  ['service.namespace', 'billing'],
                  ['deployment.environment', 'prod'],
                  ['host.name', `${s.service}-7d8b-x7zqv`],
                  ['http.method', s.kind === 'SERVER' ? 'POST' : '—'],
                  ['http.route', s.name.split(' ')[1] ?? '—'],
                  ['http.status_code', s.status === 'error' ? '500' : '200'],
                  ['order.id', 'ord_20260708_a812f'],
                  ['user.id', 'usr_8821'],
                ].map(([k, v]) => (
                  <div
                    key={k}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      padding: '4px 0',
                      borderBottom: `1px dashed ${TOKENS.border}`,
                    }}
                  >
                    <span style={{ color: TOKENS.textTertiary, fontFamily: 'monospace' }}>{k}</span>
                    <span style={{ color: TOKENS.text, fontFamily: 'monospace' }}>{v}</span>
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: 'events',
            label: '事件',
            children: (
              <List
                size="small"
                dataSource={[
                  { name: 'exception', time: '10:42:19.474' },
                  { name: 'log.error', time: '10:42:19.476' },
                ]}
                renderItem={(it) => (
                  <List.Item style={{ padding: '4px 0' }}>
                    <span style={{ fontSize: 12 }}>{it.name}</span>
                    <span style={{ fontSize: 12, color: TOKENS.textTertiary, fontFamily: 'monospace' }}>
                      {it.time}
                    </span>
                  </List.Item>
                )}
              />
            ),
          },
          {
            key: 'logs',
            label: '采样',
            children: (
              <div style={{ fontSize: 12, color: TOKENS.textSecondary, padding: '8px 0' }}>
                暂未启用日志关联
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

/** 服务执行占比 — 横向 bar 列表 */
function ServiceBreakdown() {
  // 按服务聚合 dur 占比
  const byService = new Map<string, number>();
  SPANS.forEach((s) => byService.set(s.service, (byService.get(s.service) ?? 0) + s.dur));
  const total = Array.from(byService.values()).reduce((a, b) => a + b, 0);
  const rows = Array.from(byService.entries())
    .map(([svc, dur]) => ({ svc, dur, pct: (dur / total) * 100 }))
    .sort((a, b) => b.dur - a.dur);
  return (
    <div style={{ ...surfaceCardStyle, padding: '12px 14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <Text style={{ fontSize: 12, color: TOKENS.text, fontWeight: 600 }}>服务执行占比</Text>
        <Text style={{ fontSize: 10, color: TOKENS.textTertiary }}>% 执行时间</Text>
      </div>
      <div>
        {rows.map((r) => (
          <div key={r.svc} style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: SERVICE_COLORS[r.svc],
                marginRight: 8,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                width: 92,
                fontSize: 12,
                color: TOKENS.text,
                fontFamily: 'ui-monospace, monospace',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {r.svc}
            </span>
            <div style={{ flex: 1, height: 6, background: TOKENS.bg, borderRadius: 3, margin: '0 10px' }}>
              <div
                style={{
                  width: `${r.pct}%`,
                  height: '100%',
                  background: SERVICE_COLORS[r.svc],
                  borderRadius: 3,
                }}
              />
            </div>
            <span
              style={{
                width: 44,
                textAlign: 'right',
                fontSize: 12,
                fontVariantNumeric: 'tabular-nums',
                color: TOKENS.text,
                fontWeight: 500,
              }}
            >
              {r.pct.toFixed(1)}%
            </span>
            <span
              style={{
                width: 48,
                textAlign: 'right',
                fontSize: 11,
                color: TOKENS.textTertiary,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {r.dur}ms
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TraceDetail() {
  const [view, setView] = useState<'waterfall' | 'flame' | 'list'>('waterfall');
  const [selectedId, setSelectedId] = useState<string>('s8');
  const [spanQuery, setSpanQuery] = useState('');
  const firstErrorId = SPANS.find((s) => s.status === 'error')?.id ?? 's8';

  return (
    <div style={shellStyle}>
      <TopMenuBar active="explore" />
      <ExploreSubNav active="traces" />
      <Content style={{ padding: 24 }}>
        {/* 面包屑 */}
        <div style={{ marginBottom: 12, fontSize: 13, color: TOKENS.textSecondary }}>
          <a href={STORY_URLS.explore} style={{ color: TOKENS.textSecondary }}>
            服务
          </a>
          <span style={{ margin: '0 6px' }}>›</span>
          <a style={{ color: TOKENS.textSecondary }}>api-gateway</a>
          <span style={{ margin: '0 6px' }}>›</span>
          <Text style={{ color: TOKENS.text }}>GET /api/user/profile</Text>
          <span style={{ marginLeft: 12 }}>
            <span
              style={{
                background: TOKENS.primarySoft,
                color: TOKENS.primary,
                padding: '2px 6px',
                borderRadius: 3,
                fontSize: 11,
                fontFamily: 'ui-monospace, monospace',
                marginRight: 8,
              }}
            >
              GET
            </span>
            <span style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12, color: TOKENS.text }}>
              /api/user/profile
            </span>
            <span
              style={{
                background: '#dcfce7',
                color: '#16a34a',
                padding: '2px 6px',
                borderRadius: 3,
                fontSize: 11,
                marginLeft: 8,
              }}
            >
              ✓ 200
            </span>
          </span>
        </div>

        {/* 概览 stat strip */}
        <div
          style={{
            ...surfaceCardStyle,
            padding: '12px 16px',
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 28,
          }}
        >
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              Trace ID
            </Text>
            <div
              style={{
                fontSize: 13,
                fontFamily: 'ui-monospace, monospace',
                color: TOKENS.text,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                marginTop: 2,
              }}
            >
              59165a3a...451d07d4
              <Button size="small" type="text" icon={<ShareAltOutlined />} style={{ padding: 0 }} />
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              总耗时
            </Text>
            <div style={{ fontSize: 16, fontWeight: 600, color: TOKENS.text, marginTop: 2 }}>
              421ms
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              跨度数
            </Text>
            <div style={{ fontSize: 16, fontWeight: 600, color: TOKENS.text, marginTop: 2 }}>
              {SPANS.length}
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              服务数
            </Text>
            <div style={{ fontSize: 16, fontWeight: 600, color: TOKENS.text, marginTop: 2 }}>
              {TRACE_SERVICES.length}
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              状态
            </Text>
            <div style={{ marginTop: 2 }}>
              <span
                style={{
                  color: TOKENS.danger,
                  fontSize: 13,
                  fontWeight: 500,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                <CloseCircleOutlined /> 含错误
              </span>
            </div>
          </div>
          {/* 跳到首个错误 */}
          <div style={{ flex: 1 }} />
          <Button
            danger
            icon={<FireFilled />}
            onClick={() => setSelectedId(firstErrorId)}
          >
            跳到首个错误
          </Button>
        </div>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={16}>
            {/* 视图切换 tabs */}
            <div style={{ marginBottom: 12 }}>
              <Segmented
                value={view}
                onChange={(v) => setView(v as 'waterfall' | 'flame' | 'list')}
                options={[
                  { value: 'waterfall', label: '瀑布图' },
                  { value: 'flame', label: '火焰图' },
                  { value: 'list', label: '跨度列表' },
                ]}
              />
            </div>
            {/* 三视图 */}
            <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
              {view === 'waterfall' && (
                <WaterfallChart selectedId={selectedId} onSelect={setSelectedId} />
              )}
              {view === 'flame' && <FlameChart onSelect={setSelectedId} />}
              {view === 'list' && (
                <SpanList
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  query={spanQuery}
                  setQuery={setSpanQuery}
                />
              )}
            </div>
          </Col>
          <Col xs={24} lg={8}>
            <div style={{ position: 'sticky', top: 80 }}>
              <ServiceBreakdown />
              <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginTop: 12 }}>
                <SpanDetailPanel selectedId={selectedId} />
              </div>
            </div>
          </Col>
        </Row>
      </Content>
    </div>
  );
}

/* ============================================================
 * 3) EndpointsList · 端点列表(对齐 datadog)
 *    顶部工具栏 + 单表(方法 / 端点 / 所属服务 / 吞吐量 / 错误率 / P95 / 最近活跃)
 * ============================================================ */
const ENDPOINTS = [
  { key: 'e1', service: 'user-api', method: 'GET', route: '/user', rps: 0.00, errorRate: 0.7, p95: 61, lastActive: '7 天前' },
  { key: 'e2', service: 'inventory-svc', method: 'POST', route: '/reserve', rps: 0.00, errorRate: 2.9, p95: 59, lastActive: '7 天前' },
  { key: 'e3', service: 'auth-svc', method: 'POST', route: '/verify', rps: 0.00, errorRate: 1.3, p95: 23, lastActive: '7 天前' },
  { key: 'e4', service: 'payment-svc', method: 'POST', route: '/charge', rps: 0.00, errorRate: 15, p95: 244, lastActive: '7 天前' },
  { key: 'e5', service: 'checkout-api', method: 'POST', route: '/checkout', rps: 0.00, errorRate: 2.9, p95: 349, lastActive: '7 天前' },
  { key: 'e6', service: 'checkout-api', method: 'GET', route: '/checkout/:id', rps: 0.00, errorRate: 0, p95: 321, lastActive: '7 天前' },
  { key: 'e7', service: 'catalog-api', method: 'GET', route: '/catalog/search', rps: 0.00, errorRate: 2.2, p95: 77, lastActive: '7 天前' },
  { key: 'e8', service: 'catalog-api', method: 'GET', route: '/catalog', rps: 0.00, errorRate: 0.7, p95: 46, lastActive: '7 天前' },
  { key: 'e9', service: 'api-gateway', method: 'POST', route: '/api/checkout', rps: 0.00, errorRate: 1.8, p95: 453, lastActive: '7 天前' },
  { key: 'e10', service: 'api-gateway', method: 'GET', route: '/api/user/profile', rps: 0.00, errorRate: 0, p95: 445, lastActive: '7 天前' },
  { key: 'e11', service: 'api-gateway', method: 'GET', route: '/api/catalog', rps: 0.00, errorRate: 1.9, p95: 469, lastActive: '7 天前' },
  { key: 'e12', service: 'web-storefront', method: 'GET', route: '/', rps: 0.00, errorRate: 0, p95: 472, lastActive: '7 天前' },
  { key: 'e13', service: 'web-storefront', method: 'POST', route: '/cart/checkout', rps: 0.00, errorRate: 0, p95: 506, lastActive: '7 天前' },
  { key: 'e14', service: 'web-storefront', method: 'GET', route: '/product/:id', rps: 0.00, errorRate: 2.9, p95: 483, lastActive: '7 天前' },
];

function EndpointsList() {
  const [query, setQuery] = useState('');
  const [env, setEnv] = useState('all');
  const [service, setService] = useState('all');
  const [sortBy, setSortBy] = useState('rps');
  const [timeRange, setTimeRange] = useState('7d');

  const filtered = ENDPOINTS.filter((e) => {
    if (service !== 'all' && e.service !== service) return false;
    if (query && !e.route.toLowerCase().includes(query.toLowerCase()) && !e.service.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  }).sort((a, b) => {
    if (sortBy === 'rps') return b.rps - a.rps;
    if (sortBy === 'errorRate') return b.errorRate - a.errorRate;
    if (sortBy === 'p95') return b.p95 - a.p95;
    return 0;
  });

  const errorRateColor = (v: number) => {
    if (v >= 5) return TOKENS.danger;
    if (v >= 1) return TOKENS.warning;
    return TOKENS.success;
  };

  return (
    <div style={shellStyle}>
      <TopMenuBar active="explore" />
      <ExploreSubNav active="endpoints" />
      <Content style={{ padding: 24 }}>
        {/* 顶部工具栏(对齐 datadog) */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            marginBottom: 16,
            flexWrap: 'wrap',
          }}
        >
          <Input
            placeholder="搜索路径模板 / 服务"
            prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            allowClear
            style={{ width: 280 }}
          />
          <Select
            value={env}
            onChange={setEnv}
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部环境' },
              { value: 'production', label: 'production' },
              { value: 'staging', label: 'staging' },
            ]}
          />
          <div style={{ flex: 1 }} />
          <Select
            value={service}
            onChange={setService}
            style={{ width: 140 }}
            suffixIcon={<ApiOutlined style={{ color: TOKENS.textTertiary }} />}
            options={[
              { value: 'all', label: '全部服务' },
              ...Array.from(new Set(ENDPOINTS.map((e) => e.service))).map((s) => ({ value: s, label: s })),
            ]}
          />
          <Select
            value={sortBy}
            onChange={setSortBy}
            style={{ width: 120 }}
            options={[
              { value: 'rps', label: '吞吐量' },
              { value: 'errorRate', label: '错误率' },
              { value: 'p95', label: 'P95 耗时' },
            ]}
          />
          <Radio.Group
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            size="small"
            buttonStyle="solid"
          >
            <Radio.Button value="15m">15m</Radio.Button>
            <Radio.Button value="1h">1h</Radio.Button>
            <Radio.Button value="4h">4h</Radio.Button>
            <Radio.Button value="1d">1d</Radio.Button>
            <Radio.Button value="7d">7d</Radio.Button>
          </Radio.Group>
        </div>

        {/* 单表(对齐 datadog:方法 / 端点 / 所属服务 / 吞吐量 / 错误率 / P95 / 最近活跃) */}
        <div style={surfaceCardStyle}>
          <Table
            size="middle"
            rowKey="key"
            pagination={false}
            dataSource={filtered}
            columns={[
              {
                title: '方法',
                dataIndex: 'method',
                width: 70,
                render: (v) => (
                  <span
                    style={{
                      background: v === 'POST' ? TOKENS.primarySoft : TOKENS.bg,
                      color: v === 'POST' ? TOKENS.primary : TOKENS.textSecondary,
                      padding: '2px 8px',
                      borderRadius: 3,
                      fontSize: 11,
                      fontFamily: 'ui-monospace, monospace',
                      fontWeight: 500,
                    }}
                  >
                    {v}
                  </span>
                ),
              },
              {
                title: '端点',
                render: (_, r) => (
                  <Space size={6} align="center">
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        background: SERVICE_COLORS[r.service] ?? TOKENS.textTertiary,
                        flexShrink: 0,
                      }}
                    />
                    <a
                      style={{
                        color: TOKENS.text,
                        fontFamily: 'ui-monospace, monospace',
                        fontSize: 13,
                      }}
                    >
                      {r.method} {r.route}
                    </a>
                  </Space>
                ),
              },
              {
                title: '所属服务',
                dataIndex: 'service',
                width: 140,
                render: (v) => (
                  <span style={{ color: TOKENS.textSecondary, fontSize: 13 }}>{v}</span>
                ),
              },
              {
                title: '吞吐量',
                dataIndex: 'rps',
                width: 140,
                align: 'right' as const,
                sorter: true,
                render: (v) => (
                  <span style={{ textAlign: 'right' }}>
                    <span
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        color: TOKENS.text,
                        fontVariantNumeric: 'tabular-nums',
                        marginRight: 4,
                      }}
                    >
                      {v.toFixed(2)}
                    </span>
                    <span style={{ fontSize: 11, color: TOKENS.textTertiary }}>次/秒</span>
                  </span>
                ),
              },
              {
                title: '错误率',
                dataIndex: 'errorRate',
                width: 100,
                align: 'right' as const,
                render: (v) => (
                  <span
                    style={{
                      color: errorRateColor(v),
                      fontSize: 13,
                      fontWeight: 500,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {v}%
                  </span>
                ),
              },
              {
                title: 'P95',
                dataIndex: 'p95',
                width: 100,
                align: 'right' as const,
                render: (v) => (
                  <span
                    style={{
                      color: TOKENS.textSecondary,
                      fontSize: 13,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {v}ms
                  </span>
                ),
              },
              {
                title: '最近活跃',
                dataIndex: 'lastActive',
                width: 110,
                align: 'right' as const,
                render: (v) => (
                  <span style={{ color: TOKENS.textTertiary, fontSize: 12 }}>{v}</span>
                ),
              },
            ]}
          />
        </div>
      </Content>
    </div>
  );
}

/* ============================================================
 * 4) EndpointDetail · 端点详情(RED 三联 + 状态码 + 时延构成)
 * ============================================================ */
function RedChartsMock({ view }: { view: 'throughput' | 'error' | 'latency' }) {
  const w = 800;
  const h = 200;
  // 模拟两条线:throughput 蓝色,error 红色
  const data = Array.from({ length: 30 }, (_, i) => ({
    x: (i / 29) * (w - 40) + 20,
    throughput: 200 + Math.sin(i / 3) * 50 + Math.random() * 30,
    error: 4 + Math.sin(i / 5) * 1.5 + Math.random() * 0.8 + (i > 20 ? 8 : 0),
    p95: 200 + Math.sin(i / 4) * 30 + (i > 18 ? 200 : 0),
  }));
  const maxY = Math.max(...data.map((d) => d.throughput), ...data.map((d) => d.error * 30), ...data.map((d) => d.p95));
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <line
          key={i}
          x1={20}
          y1={(h - 30) * (i / 4) + 10}
          x2={w - 20}
          y2={(h - 30) * (i / 4) + 10}
          stroke={TOKENS.border}
          strokeDasharray="2,4"
        />
      ))}
      {view === 'latency' && (
        <path
          d={`M ${data
            .map((d) => `${d.x},${h - 30 - (d.p95 / maxY) * (h - 50)}`)
            .join(' L ')}`}
          fill="none"
          stroke={TOKENS.danger}
          strokeWidth={2}
        />
      )}
      {view === 'throughput' && (
        <path
          d={`M ${data
            .map((d) => `${d.x},${h - 30 - (d.throughput / maxY) * (h - 50)}`)
            .join(' L ')}`}
          fill="none"
          stroke={TOKENS.primary}
          strokeWidth={2}
        />
      )}
      {view === 'error' && (
        <path
          d={`M ${data
            .map((d) => `${d.x},${h - 30 - (d.error / maxY) * (h - 50) * 30}`)
            .join(' L ')}`}
          fill="none"
          stroke={TOKENS.danger}
          strokeWidth={2}
        />
      )}
      {/* 部署事件标记 */}
      <line
        x1={data[18].x}
        y1={10}
        x2={data[18].x}
        y2={h - 30}
        stroke={TOKENS.success}
        strokeDasharray="3,3"
        strokeWidth={1.5}
      />
      <text x={data[18].x + 4} y={20} fontSize={10} fill={TOKENS.success}>
        部署 v5.3.0
      </text>
    </svg>
  );
}

function EndpointDetail() {
  const [view, setView] = useState<'throughput' | 'error' | 'latency'>('latency');
  return (
    <div style={shellStyle}>
      <TopMenuBar active="explore" />
      <ExploreSubNav active="endpoints" />
      <Content style={{ padding: 24 }}>
        <Space style={{ marginBottom: 12 }}>
          <a href="?path=/story/apm-explore-pages--endpoints-list" style={{ color: TOKENS.textSecondary, fontSize: 13 }}>
            ← 返回端点列表
          </a>
        </Space>
        <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 16 }}>
          <Space size={8} align="center" wrap>
            <Tag color="blue" style={{ margin: 0, fontFamily: 'monospace' }}>
              POST
            </Tag>
            <Text strong style={{ fontSize: 15, fontFamily: 'monospace' }}>
              /api/v1/charge
            </Text>
            <Tag color="processing" style={{ margin: 0 }}>
              警告
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              payment-svc · prod
            </Text>
          </Space>
        </div>
        <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <KpiCard label="吞吐量" value="342/s" sub="Σ" />
          </Col>
          <Col span={6}>
            <KpiCard label="错误率" value="8.4%" sub="近窗 1h" danger />
          </Col>
          <Col span={6}>
            <KpiCard label="P95" value="285ms" sub="" />
          </Col>
          <Col span={6}>
            <KpiCard label="P99" value="1,240ms" sub="长尾" danger />
          </Col>
        </Row>
        <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 16 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 8,
            }}
          >
            <Segmented
              value={view}
              onChange={(v) => setView(v as 'throughput' | 'error' | 'latency')}
              options={[
                { value: 'throughput', label: '吞吐量' },
                { value: 'error', label: '错误率' },
                { value: 'latency', label: 'P99 时延' },
              ]}
            />
            <Space>
              <Radio.Group size="small" defaultValue="1h">
                <Radio.Button value="15m">15m</Radio.Button>
                <Radio.Button value="1h">1h</Radio.Button>
                <Radio.Button value="4h">4h</Radio.Button>
                <Radio.Button value="1d">1d</Radio.Button>
              </Radio.Group>
            </Space>
          </div>
          <RedChartsMock view={view} />
        </div>
        <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginTop: 16 }}>
          <Title level={5} style={{ margin: 0, marginBottom: 10 }}>
            样本调用链
          </Title>
          <Table
            size="middle"
            rowKey="key"
            pagination={false}
            dataSource={TRACES.slice(0, 5)}
            columns={[
              {
                title: '入口服务',
                render: (_: unknown, r: any) => (
                  <Space direction="vertical" size={2}>
                    <a style={{ color: TOKENS.text, fontWeight: 600, fontSize: 13 }}>{r.service}</a>
                    <span style={{ fontSize: 11, color: TOKENS.textTertiary, fontFamily: 'monospace' }}>
                      {r.traceId?.slice(0, 16)}
                    </span>
                  </Space>
                ),
              },
              {
                title: '资源',
                render: (_: unknown, r: any) => (
                  <span style={{ fontFamily: 'monospace', fontSize: 12, color: TOKENS.text }}>
                    {r.operation}
                  </span>
                ),
              },
              {
                title: '总耗时',
                dataIndex: 'duration',
                width: 110,
                align: 'right' as const,
                render: (v: number) => {
                  const danger = v > 400;
                  return (
                    <span
                      style={{
                        fontVariantNumeric: 'tabular-nums',
                        color: danger ? TOKENS.danger : TOKENS.text,
                        fontWeight: danger ? 600 : 400,
                        textDecoration: 'underline',
                        textUnderlineOffset: 3,
                      }}
                    >
                      {v} ms
                    </span>
                  );
                },
              },
              {
                title: '跨度数',
                dataIndex: 'spanCount',
                width: 80,
                align: 'right' as const,
                render: (v: number) => (
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>{v}</span>
                ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 110,
                render: (v: string, r: any) =>
                  v === 'error' ? (
                    <span style={{ color: TOKENS.danger, fontSize: 12, fontWeight: 500 }}>
                      <CloseCircleOutlined /> 错误数 {r.errorCount ?? 1}
                    </span>
                  ) : (
                    <span style={{ color: TOKENS.success, fontSize: 12, fontWeight: 500 }}>
                      <CheckOutlined /> 正常
                    </span>
                  ),
              },
              {
                title: '时间',
                width: 100,
                render: () => <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>6 天前</span>,
              },
            ]}
          />
        </div>
      </Content>
    </div>
  );
}

function KpiCard({ label, value, sub, danger }: { label: string; value: string; sub: string; danger?: boolean }) {
  return (
    <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {label}
      </Text>
      <div
        style={{
          fontSize: 24,
          fontWeight: 700,
          color: danger ? TOKENS.danger : TOKENS.text,
          marginTop: 4,
          ...tabularNumStyle,
        }}
      >
        {value}
      </div>
      {sub && (
        <Text type="secondary" style={{ fontSize: 11 }}>
          {sub}
        </Text>
      )}
    </div>
  );
}

/* ============================================================
 * 5) IssueList · Issue 列表
 * ============================================================ */
const ISSUES = [
  {
    key: 'i1',
    type: 'DownstreamUnavailableError',
    message: 'DownstreamUnavailableError: failed processing id=51634 after 191ms',
    service: 'payment-svc',
    versions: ['v5.2.0', 'v5.3.0'],
    endpoints: ['POST /charge'],
    state: '待分诊' as '待分诊' | '已分诊' | '已解决' | '已排除',
    isNew: true,
    affectedTraces: 8,
    occurrences: 8,
    lastSeen: '7 天前',
    stack: 'DownstreamUnavailableError: DownstreamUnavailableError: failed processing id=51634 after 191ms\n  at com.app.service.handle(Handler.java:142)\n  at com.app.web.dispatch(Dispatcher.java:88)\n  at com.app.runtime.exec(Runtime.java:51)',
    versionDist: [
      { v: '5.3.0', count: 4, pct: 50 },
      { v: '5.2.0', count: 4, pct: 50 },
    ],
    endpointDist: [
      { e: 'POST /charge', count: 8, pct: 100 },
    ],
  },
  {
    key: 'i2',
    type: 'NullPointerException',
    message: 'NullPointerException: failed processing id=24462 after 146ms',
    service: 'payment-svc',
    versions: ['v5.2.0', 'v5.3.0'],
    endpoints: ['POST /charge'],
    state: '待分诊' as const,
    isNew: true,
    affectedTraces: 6,
    occurrences: 6,
    lastSeen: '7 天前',
    stack: 'java.lang.NullPointerException: Cannot invoke "String.length()" because "orderId" is null\n  at com.bklite.payment.PaymentService.charge(PaymentService.java:142)\n  at com.bklite.payment.PaymentController.checkout(PaymentController.java:88)',
    versionDist: [
      { v: '5.3.0', count: 4, count2: 0, pct: 67 },
      { v: '5.2.0', count: 2, count2: 0, pct: 33 },
    ],
    endpointDist: [{ e: 'POST /charge', count: 6, pct: 100 }],
  },
  {
    key: 'i3',
    type: 'PaymentDeclinedError',
    message: 'PaymentDeclinedError: failed processing id=21803 after 107ms',
    service: 'payment-svc',
    versions: ['v5.2.0', 'v5.3.0'],
    endpoints: ['POST /charge'],
    state: '待分诊' as const,
    isNew: true,
    affectedTraces: 6,
    occurrences: 6,
    lastSeen: '7 天前',
    stack: 'PaymentDeclinedError: payment declined\n  at com.bklite.payment.PaymentService.process(PaymentService.java:88)',
    versionDist: [
      { v: '5.3.0', count: 4, pct: 67 },
      { v: '5.2.0', count: 2, pct: 33 },
    ],
    endpointDist: [{ e: 'POST /charge', count: 6, pct: 100 }],
  },
  {
    key: 'i4',
    type: 'ValidationError',
    message: 'ValidationError: failed processing id=47900 after 171ms',
    service: 'payment-svc',
    versions: ['v5.2.0', 'v5.3.0'],
    endpoints: ['POST /charge'],
    state: '待分诊' as const,
    isNew: true,
    affectedTraces: 5,
    occurrences: 5,
    lastSeen: '7 天前',
    stack: 'ValidationError: validation failed\n  at com.bklite.payment.PaymentService.validate(PaymentService.java:42)',
    versionDist: [
      { v: '5.3.0', count: 3, pct: 60 },
      { v: '5.2.0', count: 2, pct: 40 },
    ],
    endpointDist: [{ e: 'POST /charge', count: 5, pct: 100 }],
  },
  {
    key: 'i5',
    type: 'TimeoutError',
    message: 'TimeoutError: failed processing id=38912 after 5012ms',
    service: 'payment-svc',
    versions: ['v5.2.0', 'v5.3.0'],
    endpoints: ['POST /charge'],
    state: '待分诊' as const,
    isNew: false,
    affectedTraces: 5,
    occurrences: 5,
    lastSeen: '7 天前',
    stack: 'TimeoutError: request timeout after 5000ms\n  at com.bklite.payment.PaymentService.call(PaymentService.java:99)',
    versionDist: [
      { v: '5.3.0', count: 3, pct: 60 },
      { v: '5.2.0', count: 2, pct: 40 },
    ],
    endpointDist: [{ e: 'POST /charge', count: 5, pct: 100 }],
  },
];

function IssueList() {
  const [timeRange, setTimeRange] = useState('7d');
  const [service, setService] = useState('all');
  const [env, setEnv] = useState('全部环境');
  const [expandedKeys, setExpandedKeys] = useState<string[]>(['i1']);

  const totalIssues = 27;
  const totalOccurrences = 60;
  const totalAffected = 60;
  const totalServices = 8;

  const toggleExpand = (key: string) =>
    setExpandedKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  return (
    <div style={shellStyle}>
      <TopMenuBar active="explore" />
      <ExploreSubNav active="errors" />
      <Content style={{ padding: 24 }}>
        {/* 顶部筛选栏:时间 + 状态 chips + 服务 Select + 环境 Select */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 12,
            flexWrap: 'wrap',
          }}
        >
          <Radio.Group
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            size="small"
            buttonStyle="solid"
          >
            <Radio.Button value="15m">15m</Radio.Button>
            <Radio.Button value="1h">1h</Radio.Button>
            <Radio.Button value="4h">4h</Radio.Button>
            <Radio.Button value="1d">1d</Radio.Button>
            <Radio.Button value="7d">7d</Radio.Button>
          </Radio.Group>
          <div style={{ flex: 1 }} />
          <Select
            value={service}
            onChange={setService}
            size="small"
            style={{ width: 140 }}
            options={[
              { value: 'all', label: '服务' },
              { value: 'payment-svc', label: 'payment-svc' },
              { value: 'checkout-api', label: 'checkout-api' },
              { value: 'api-gateway', label: 'api-gateway' },
            ]}
          />
          <Select
            value={env}
            onChange={setEnv}
            size="small"
            style={{ width: 140 }}
            options={[
              { value: '全部环境', label: '全部环境' },
              { value: 'production', label: 'production' },
              { value: 'staging', label: 'staging' },
            ]}
          />
        </div>

        {/* 概览 KPI 条 */}
        <div
          style={{
            ...surfaceCardStyle,
            padding: '14px 16px',
            marginBottom: 12,
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 16,
          }}
        >
          {[
            { label: '异常 Issue', value: totalIssues, color: TOKENS.danger },
            { label: '出现次数', value: totalOccurrences, color: TOKENS.text },
            { label: '受影响 trace', value: totalAffected, color: TOKENS.text },
            { label: '受影响服务', value: totalServices, color: TOKENS.text },
          ].map((k) => (
            <div key={k.label} style={{ borderRight: `1px solid ${TOKENS.border}`, paddingLeft: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{k.label}</Text>
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  color: k.color,
                  marginTop: 4,
                  ...tabularNumStyle,
                }}
              >
                {k.value}
              </div>
            </div>
          ))}
        </div>

        {/* Issue 列表(每条 Issue 一张卡片) */}
        <div>
          {ISSUES.map((it) => {
            const expanded = expandedKeys.includes(it.key);
            return (
              <div
                key={it.key}
                style={{
                  ...surfaceCardStyle,
                  marginBottom: 8,
                  overflow: 'hidden',
                }}
              >
                {/* 顶部条:服务 + 版本 + 链接 + ⋮ */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '6px 12px',
                    background: TOKENS.primarySoft,
                    borderBottom: expanded ? `1px solid ${TOKENS.border}` : 'none',
                  }}
                >
                  <span
                    style={{
                      background: TOKENS.surface,
                      border: `1px solid ${TOKENS.border}`,
                      padding: '1px 6px',
                      borderRadius: 3,
                      fontSize: 11,
                      fontFamily: 'ui-monospace, monospace',
                      color: TOKENS.text,
                    }}
                  >
                    {it.service}
                  </span>
                  {it.versions.map((v) => (
                    <span
                      key={v}
                      style={{
                        background: TOKENS.surface,
                        border: `1px solid ${TOKENS.border}`,
                        padding: '1px 6px',
                        borderRadius: 3,
                        fontSize: 11,
                        color: TOKENS.textSecondary,
                      }}
                    >
                      {v}
                    </span>
                  ))}
                  <a style={{ color: TOKENS.primary, fontSize: 12 }}>查看样本 trace →</a>
                  <a style={{ color: TOKENS.primary, fontSize: 12 }}>查看相关调用链 →</a>
                  <a style={{ color: TOKENS.primary, fontSize: 12 }}>查看服务错误 →</a>
                  <div style={{ flex: 1 }} />
                  <Button type="text" size="small" icon={<MoreOutlined />} />
                </div>
                {/* 主体行:异常类型 + 消息 + 右侧 3 列数据 */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    padding: '12px 14px',
                    gap: 16,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Space size={8} align="center" style={{ marginBottom: 4 }}>
                      <span
                        style={{
                          display: 'inline-block',
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: TOKENS.danger,
                        }}
                      />
                      <span style={{ fontSize: 14, fontWeight: 600, color: TOKENS.text }}>
                        {it.type}
                      </span>
                      {it.isNew && (
                        <span
                          style={{
                            background: TOKENS.primary,
                            color: '#fff',
                            padding: '0 6px',
                            borderRadius: 3,
                            fontSize: 11,
                            lineHeight: '18px',
                          }}
                        >
                          新增
                        </span>
                      )}
                    </Space>
                    <div style={{ fontSize: 12, color: TOKENS.textSecondary, marginLeft: 16 }}>
                      {it.message}
                    </div>
                  </div>
                  {/* 右侧 3 列数据 */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 90px)',
                      gap: 0,
                      textAlign: 'right',
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontSize: 18,
                          fontWeight: 700,
                          color: TOKENS.danger,
                          ...tabularNumStyle,
                        }}
                      >
                        {it.affectedTraces}
                      </div>
                      <div style={{ fontSize: 11, color: TOKENS.textTertiary }}>受影响 trace</div>
                    </div>
                    <div>
                      <div
                        style={{
                          fontSize: 18,
                          fontWeight: 700,
                          color: TOKENS.text,
                          ...tabularNumStyle,
                        }}
                      >
                        {it.occurrences}
                      </div>
                      <div style={{ fontSize: 11, color: TOKENS.textTertiary }}>出现次数</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 12, color: TOKENS.text, marginTop: 4 }}>{it.lastSeen}</div>
                      <div style={{ fontSize: 11, color: TOKENS.textTertiary }}>最近出现</div>
                    </div>
                  </div>
                </div>
                {/* 折叠区:堆栈 + 分布 */}
                <div
                  style={{
                    padding: '4px 14px 8px 28px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    fontSize: 12,
                    color: TOKENS.textSecondary,
                  }}
                  onClick={() => toggleExpand(it.key)}
                >
                  <CaretDownOutlined
                    style={{
                      fontSize: 10,
                      transition: 'transform 0.15s',
                      transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)',
                    }}
                  />
                  <span>堆栈</span>
                  <CaretDownOutlined
                    style={{
                      fontSize: 10,
                      transition: 'transform 0.15s',
                      transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)',
                      marginLeft: 16,
                    }}
                  />
                  <span>分布</span>
                </div>
                {expanded && (
                  <div
                    style={{
                      padding: '0 16px 14px 28px',
                      borderTop: `1px solid ${TOKENS.border}`,
                    }}
                  >
                    {/* 堆栈 */}
                    <pre
                      style={{
                        background: TOKENS.bg,
                        border: `1px solid ${TOKENS.border}`,
                        borderRadius: 4,
                        padding: '10px 12px',
                        fontSize: 11,
                        color: TOKENS.text,
                        fontFamily: 'ui-monospace, monospace',
                        lineHeight: 1.6,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                        margin: '10px 0',
                      }}
                    >
                      {it.stack}
                    </pre>
                    {/* 按版本分布 */}
                    <div
                      style={{
                        ...surfaceCardStyle,
                        padding: '8px 12px',
                        marginBottom: 8,
                        border: `1px solid ${TOKENS.border}`,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontSize: 12,
                          color: TOKENS.text,
                          fontWeight: 600,
                          marginBottom: 6,
                        }}
                      >
                        <span>按版本分布</span>
                        <span style={{ color: TOKENS.textTertiary, fontWeight: 400 }}>版本</span>
                      </div>
                      {it.versionDist.map((v) => (
                        <div
                          key={v.v}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            marginBottom: 4,
                            fontSize: 12,
                          }}
                        >
                          <span style={{ width: 60, fontFamily: 'ui-monospace, monospace' }}>
                            {v.v}
                          </span>
                          <div
                            style={{
                              flex: 1,
                              height: 4,
                              background: TOKENS.bg,
                              borderRadius: 2,
                              margin: '0 8px',
                            }}
                          >
                            <div
                              style={{
                                width: `${v.pct}%`,
                                height: '100%',
                                background: TOKENS.danger,
                                borderRadius: 2,
                              }}
                            />
                          </div>
                          <span
                            style={{
                              width: 60,
                              textAlign: 'right',
                              color: TOKENS.textSecondary,
                              fontVariantNumeric: 'tabular-nums',
                            }}
                          >
                            {v.count} {v.pct}%
                          </span>
                        </div>
                      ))}
                    </div>
                    {/* 按端点分布 */}
                    <div
                      style={{
                        ...surfaceCardStyle,
                        padding: '8px 12px',
                        border: `1px solid ${TOKENS.border}`,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontSize: 12,
                          color: TOKENS.text,
                          fontWeight: 600,
                          marginBottom: 6,
                        }}
                      >
                        <span>按端点分布</span>
                        <span style={{ color: TOKENS.textTertiary, fontWeight: 400 }}>端点</span>
                      </div>
                      {it.endpointDist.map((e) => (
                        <div
                          key={e.e}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            marginBottom: 4,
                            fontSize: 12,
                          }}
                        >
                          <span
                            style={{
                              width: 100,
                              fontFamily: 'ui-monospace, monospace',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}
                          >
                            {e.e}
                          </span>
                          <div
                            style={{
                              flex: 1,
                              height: 4,
                              background: TOKENS.bg,
                              borderRadius: 2,
                              margin: '0 8px',
                            }}
                          >
                            <div
                              style={{
                                width: `${e.pct}%`,
                                height: '100%',
                                background: TOKENS.danger,
                                borderRadius: 2,
                              }}
                            />
                          </div>
                          <span
                            style={{
                              width: 60,
                              textAlign: 'right',
                              color: TOKENS.textSecondary,
                              fontVariantNumeric: 'tabular-nums',
                            }}
                          >
                            {e.count} {e.pct}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Content>
    </div>
  );
}

/* ============================================================
 * Story 注册
 * ============================================================ */
const meta = {
  title: 'APM/Explore Pages',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const TracesSearchStory: Story = {
  name: '探索 · 调用链检索',
  render: () => <TracesSearch />,
};

export const TraceDetailStory: Story = {
  name: '探索 · Trace 详情',
  render: () => <TraceDetail />,
};

export const EndpointsListStory: Story = {
  name: '探索 · 端点列表',
  render: () => <EndpointsList />,
};

export const EndpointDetailStory: Story = {
  name: '探索 · 端点详情',
  render: () => <EndpointDetail />,
};

export const IssueListStory: Story = {
  name: '探索 · Issue 列表',
  render: () => <IssueList />,
};
