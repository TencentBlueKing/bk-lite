import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import {
  Badge,
  Button,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Layout,
  message,
  Popconfirm,
  Radio,
  Select,
  Space,
  Steps,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  AppstoreOutlined,
  BellOutlined,
  CheckOutlined,
  CloseCircleOutlined,
  CloseOutlined,
  ClockCircleOutlined,
  CompassOutlined,
  DeleteOutlined,
  EditOutlined,
  FireOutlined,
  PlusOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  RocketOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';

const { Content } = Layout;
const { Title, Text } = Typography;

/* ============================================================
 * bklite APM · 事件 · 交互式故事书
 *
 * 关键架构(已对齐规格书《事件.md》):
 *  1) 事件 group 下挂"告警(查看) + 策略(配置)"两个子菜单
 *  2) 告警状态机:新告警 → 已恢复 / 已关闭(3 态)
 *  3) 度量告警:度量固定 4 个(错误率 / P99 时延 / P95 时延 / 吞吐)
 *  4) 分组评估:不分组(聚合) / 按版本 / 按端点(3 选 1)
 *  5) 通知复用 system_mgmt 6 类通道(含 NATS 告警中心);APM 不维护独立通道
 *  6) 抑制在告警中心做,APM 侧不维护抑制窗口/抑制规则/抑制粒度
 *  7) 告警→告警中心单向推送,告警中心关闭/抑制不回写,APM 是 source of truth
 *  8) 列表两个独立 Tab:活跃告警 / 历史告警
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
function TopMenuBar({ active = 'events' }: { active?: string }) {
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
 * 二级导航(事件 group):告警 / 策略
 * ============================================================ */
function EventsSubNav({ active }: { active: 'alerts' | 'policies' }) {
  const items = [
    { key: 'alerts', label: '告警', count: 7, href: STORY_URLS.events },
    { key: 'policies', label: '策略', count: 5, href: '?path=/story/apm-events-pages--policies-list' },
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
            <span>{it.label}</span>
            <Badge
              count={it.count}
              style={{
                background: isActive ? TOKENS.primary : TOKENS.textTertiary,
                fontSize: 10,
                boxShadow: 'none',
              }}
            />
          </a>
        );
      })}
    </div>
  );
}

/* ============================================================
 * 告警(查看)
 * ============================================================ */

type AlertState = 'new' | 'recovered' | 'closed';
type AlertLevel = 'critical' | 'error' | 'warning';
type AlertMetric = 'error_rate' | 'p99' | 'p95' | 'throughput';

// 状态机对齐 monitor:new(蓝)/ recovered(灰)/ closed(灰)
const STATE_STYLE: Record<AlertState, { color: string; bg: string; label: string }> = {
  new: { color: TOKENS.primary, bg: TOKENS.primarySoft, label: '新告警' },
  recovered: { color: TOKENS.textSecondary, bg: TOKENS.bg, label: '已恢复' },
  closed: { color: TOKENS.textTertiary, bg: TOKENS.bg, label: '已关闭' },
};

// 3 级别配色(对齐 monitor 实际定义):critical 红 / error 橙 / warning 浅橙
const LEVEL_COLOR: Record<AlertLevel, string> = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42',
};

const LEVEL_LABEL: Record<AlertLevel, string> = {
  critical: '严重',
  error: '错误',
  warning: '警告',
};

type EnrichedAlert = (typeof ALERTS)[number] & {
  level: AlertLevel;
  notified: boolean;
  operator: string | null;
};

const METRIC_LABEL: Record<AlertMetric, string> = {
  error_rate: '错误率',
  p99: 'P99 时延',
  p95: 'P95 时延',
  throughput: '吞吐',
};

const METRIC_UNIT: Record<AlertMetric, string> = {
  error_rate: '%',
  p99: 'ms',
  p95: 'ms',
  throughput: 'req/s',
};

const METRIC_COLOR: Record<AlertMetric, string> = {
  error_rate: TOKENS.danger,
  p99: TOKENS.warning,
  p95: '#a16207',
  throughput: TOKENS.primary,
};

const GROUP_LABEL: Record<'none' | 'version' | 'endpoint', string> = {
  none: '不分组(聚合)',
  version: '按版本',
  endpoint: '按端点',
};

const ALERTS = [
  {
    key: 'a1',
    title: 'payment-svc 错误率 > 80%',
    metric: 'error_rate' as AlertMetric,
    service: 'payment-svc',
    endpoint: '',
    version: 'v2.4.1',
    rule: '错误率 > 80%(按版本)',
    currentValue: '92.3',
    threshold: '80.0',
    triggerAt: '2026-07-08 09:42',
    recoverAt: null,
    state: 'new' as AlertState,
    count: 3,
  },
  {
    key: 'a2',
    title: 'checkout-api 错误率 > 5%(按端点 POST /checkout)',
    metric: 'error_rate' as AlertMetric,
    service: 'checkout-api',
    endpoint: 'POST /checkout',
    version: '',
    rule: '错误率 > 5%(按端点)',
    currentValue: '12.7',
    threshold: '5.0',
    triggerAt: '2026-07-08 09:38',
    recoverAt: null,
    state: 'new' as AlertState,
    count: 1,
  },
  {
    key: 'a3',
    title: 'api-gateway P99 时延 > 800ms',
    metric: 'p99' as AlertMetric,
    service: 'api-gateway',
    endpoint: '',
    version: '',
    rule: 'P99 时延 > 800ms(不分组)',
    currentValue: '1240',
    threshold: '800',
    triggerAt: '2026-07-08 08:15',
    recoverAt: null,
    state: 'new' as AlertState,
    count: 2,
  },
  {
    key: 'a4',
    title: 'checkout-api 502 错误爆发 — 错误率 18.4%',
    metric: 'error_rate' as AlertMetric,
    service: 'checkout-api',
    endpoint: 'GET /products',
    version: 'v3.1.0',
    rule: '错误率 > 10%(按版本 + 端点)',
    currentValue: '18.4',
    threshold: '10.0',
    triggerAt: '2026-07-08 07:50',
    recoverAt: '2026-07-08 08:05',
    state: 'recovered' as AlertState,
    count: 1,
  },
  {
    key: 'a5',
    title: 'auth-svc P95 时延 > 300ms(按版本 v3.0.2)',
    metric: 'p95' as AlertMetric,
    service: 'auth-svc',
    endpoint: '',
    version: 'v3.0.2',
    rule: 'P95 时延 > 300ms(按版本)',
    currentValue: '452',
    threshold: '300',
    triggerAt: '2026-07-08 07:30',
    recoverAt: null,
    state: 'new' as AlertState,
    count: 5,
  },
  {
    key: 'a6',
    title: 'payment-svc 吞吐 < 100 req/s',
    metric: 'throughput' as AlertMetric,
    service: 'payment-svc',
    endpoint: '',
    version: '',
    rule: '吞吐 < 100 req/s(不分组)',
    currentValue: '47',
    threshold: '100',
    triggerAt: '2026-07-08 06:14',
    recoverAt: '2026-07-08 06:48',
    state: 'recovered' as AlertState,
    count: 1,
  },
  {
    key: 'a7',
    title: 'user-svc 错误率 > 50% (按端点 POST /login)',
    metric: 'error_rate' as AlertMetric,
    service: 'user-svc',
    endpoint: 'POST /login',
    version: '',
    rule: '错误率 > 50%(按端点)',
    currentValue: '68.2',
    threshold: '50.0',
    triggerAt: '2026-07-08 05:20',
    recoverAt: null,
    state: 'closed' as AlertState,
    count: 1,
  },
];

function StateTag({ state }: { state: AlertState }) {
  const s = STATE_STYLE[state];
  return (
    <Tag
      style={{
        margin: 0,
        background: s.bg,
        color: s.color,
        border: `1px solid ${s.color === TOKENS.textTertiary ? TOKENS.border : s.color}`,
      }}
    >
      {s.label}
    </Tag>
  );
}

function MetricTag({ metric }: { metric: AlertMetric }) {
  return (
    <Tag
      style={{
        margin: 0,
        background: 'transparent',
        color: METRIC_COLOR[metric],
        border: `1px solid ${METRIC_COLOR[metric]}`,
      }}
    >
      {METRIC_LABEL[metric]}
    </Tag>
  );
}

function LevelTag({ level }: { level: AlertLevel }) {
  const color = LEVEL_COLOR[level];
  return (
    <Tag
      style={{
        margin: 0,
        background: `${color}1a`,
        color: color,
        border: `1px solid ${color}`,
        fontWeight: 600,
      }}
    >
      {LEVEL_LABEL[level]}
    </Tag>
  );
}

/**
 * 堆叠柱状图(SVG 自绘,无外部依赖)
 * data: [{ time, critical, error, warning }]
 * colors: { critical, error, warning }
 */
function StackedBarChart({
  data,
  colors,
}: {
  data: { time: string; critical: number; error: number; warning: number }[];
  colors: { critical: string; error: string; warning: string };
}) {
  const height = 8;
  const max = Math.max(1, ...data.map((d) => d.critical + d.error + d.warning));
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 2,
        height: height * 10,
        padding: '4px 0',
      }}
    >
      {data.map((d) => {
        const total = d.critical + d.error + d.warning;
        const totalH = (total / max) * (height * 8);
        const cH = (d.critical / max) * (height * 8);
        const eH = (d.error / max) * (height * 8);
        const wH = (d.warning / max) * (height * 8);
        return (
          <div
            key={d.time}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'flex-end',
              alignItems: 'stretch',
              height: '100%',
              position: 'relative',
            }}
            title={`${d.time} · 严重 ${d.critical} / 错误 ${d.error} / 警告 ${d.warning}`}
          >
            <div
              style={{
                background: colors.critical,
                height: cH,
                borderRadius: '2px 2px 0 0',
              }}
            />
            <div style={{ background: colors.error, height: eH }} />
            <div
              style={{
                background: colors.warning,
                height: wH,
                borderRadius: total === totalH ? '2px 2px 0 0' : 0,
              }}
            />
            {/* 用 padding 把柱体填充到 totalH 高度,避免浮点计算误差 */}
            {totalH - cH - eH - wH > 0 && (
              <div style={{ height: totalH - cH - eH - wH }} />
            )}
            {total === 0 && (
              <div
                style={{
                  height: 2,
                  background: TOKENS.border,
                  borderRadius: 1,
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}


function AlertsList() {
  const [keyword, setKeyword] = useState('');
  const [tab, setTab] = useState<'active' | 'history'>('active');
  const [refreshInterval, setRefreshInterval] = useState<number>(0); // 0 = 不自动刷新
  // 告警详情抽屉状态
  const [drawer, setDrawer] = useState<{
    open: boolean;
    alert: EnrichedAlert | null;
    initialTab: 'alert' | 'event';
  }>({ open: false, alert: null, initialTab: 'alert' });

  // 关闭告警(monitor 一致:Popconfirm 后调 PATCH,成功后提示)
  const handleCloseAlert = (record: EnrichedAlert) => {
    message.success(`已关闭告警: ${record.title}`);
  };

  // mock: 派生告警级别 / 通知 / 处置人(按度量类型给默认级别,保证演示效果)
  const enrichedAlerts: EnrichedAlert[] = ALERTS.map((a, i) => ({
    ...a,
    level:
      a.metric === 'error_rate'
        ? 'critical'
        : a.metric === 'p99' || a.metric === 'p95'
          ? 'error'
          : 'warning',
    notified: a.state === 'new' ? i % 4 !== 0 : true,
    operator:
      a.state === 'closed'
        ? 'sre.zhang'
        : a.state === 'recovered'
          ? 'sre.li'
          : i % 3 === 0
            ? null
            : 'sre.wang',
  }));

  const activeAlerts = enrichedAlerts.filter((a) => a.state === 'new');
  const historyAlerts = enrichedAlerts.filter(
    (a) => a.state === 'recovered' || a.state === 'closed',
  );
  const list = tab === 'active' ? activeAlerts : historyAlerts;
  const filtered = keyword
    ? list.filter(
      (a) =>
        a.title.includes(keyword) ||
          a.service.includes(keyword) ||
          a.rule.includes(keyword),
    )
    : list;

  // 顶部 StackedBarChart 数据:按小时聚合 3 级别告警数(mock 24h 分布)
  const chartData = React.useMemo(() => {
    const buckets: { time: string; critical: number; error: number; warning: number }[] = [];
    const now = new Date('2026-07-08 10:00');
    for (let h = 23; h >= 0; h -= 1) {
      const t = new Date(now.getTime() - h * 60 * 60 * 1000);
      const hour = String(t.getHours()).padStart(2, '0');
      // mock 分布:每个小时随机级别数
      const seed = h * 7 + 3;
      buckets.push({
        time: `${hour}:00`,
        critical: (seed % 3) + (h % 2),
        error: (seed % 2) + 1,
        warning: (seed % 4) + (h % 3),
      });
    }
    return buckets;
  }, []);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const columns: any = [
    {
      title: '级别',
      dataIndex: 'level',
      width: 90,
      render: (v: AlertLevel) => <LevelTag level={v} />,
    },
    {
      title: '触发时间',
      dataIndex: 'triggerAt',
      width: 150,
      render: (v: string) => (
        <Space size={4}>
          <ClockCircleOutlined style={{ color: TOKENS.textTertiary, fontSize: 11 }} />
          <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{v}</span>
        </Space>
      ),
    },
    {
      title: '告警标题',
      dataIndex: 'title',
      render: (v: string) => (
        <a style={{ color: TOKENS.primary, fontWeight: 500 }}>{v}</a>
      ),
    },
    {
      title: '指标',
      dataIndex: 'metric',
      width: 110,
      render: (v: AlertMetric) => <MetricTag metric={v} />,
    },
    {
      title: '服务 / 端点',
      dataIndex: 'service',
      width: 180,
      render: (_: unknown, r: EnrichedAlert) => (
        <Space size={4} direction="vertical" style={{ lineHeight: 1.3 }}>
          <a style={{ color: TOKENS.text, fontSize: 13 }}>{r.service}</a>
          {r.endpoint && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              {r.endpoint}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '通知',
      dataIndex: 'notified',
      width: 80,
      render: (v: boolean) =>
        v ? (
          <Tag color="success" style={{ margin: 0 }}>
            <CheckOutlined /> 已通知
          </Tag>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            未通知
          </Text>
        ),
    },
    {
      title: '处置人',
      dataIndex: 'operator',
      width: 120,
      render: (v: string | null) =>
        v ? (
          <Space size={6}>
            <span
              style={{
                width: 20,
                height: 20,
                borderRadius: '50%',
                background: TOKENS.primary,
                color: '#fff',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 10,
                fontWeight: 600,
              }}
            >
              {v.slice(0, 1).toUpperCase()}
            </span>
            <span style={{ fontSize: 12 }}>{v}</span>
          </Space>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            --
          </Text>
        ),
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_: unknown, record: EnrichedAlert) => (
        <>
          <Button
            type="link"
            style={{ padding: 0, marginRight: 8 }}
            onClick={() =>
              setDrawer({ open: true, alert: record, initialTab: 'alert' })
            }
          >
            详情
          </Button>
          <Popconfirm
            title="确定关闭此告警?"
            description="关闭后不可恢复,如需继续监控请重新启用策略"
            okText="确定"
            cancelText="取消"
            onConfirm={() => handleCloseAlert(record)}
          >
            <Button
              type="link"
              danger
              style={{ padding: 0 }}
              disabled={record.state !== 'new'}
            >
              关闭
            </Button>
          </Popconfirm>
        </>
      ),
    },
  ];

  return (
    <div style={shellStyle}>
      <TopMenuBar active="events" />
      <EventsSubNav active="alerts" />
      <Content style={{ padding: 24 }}>
        <div style={{ ...surfaceCardStyle, padding: '12px 16px', marginBottom: 16 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 12,
            }}
          >
            <Space size={8} align="center">
              <BellOutlined style={{ color: TOKENS.primary }} />
              <Title level={4} style={{ margin: 0 }}>
                告警
              </Title>
            </Space>
            <Space>
              <Input
                size="small"
                placeholder="搜索告警标题 / 服务 / 规则"
                prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                style={{ width: 240 }}
                allowClear
              />
              <Button size="small" icon={<ReloadOutlined />}>
                刷新
              </Button>
            </Space>
          </div>
        </div>
        <div style={{ ...surfaceCardStyle, padding: '12px 16px', marginBottom: 16 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 8,
            }}
          >
            <Text style={{ fontSize: 13, fontWeight: 500 }}>告警分布(近 24h)</Text>
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                级别:
              </Text>
              <Tag style={{ margin: 0, background: `${LEVEL_COLOR.critical}1a`, color: LEVEL_COLOR.critical, border: `1px solid ${LEVEL_COLOR.critical}` }}>
                严重 {chartData.reduce((s, b) => s + b.critical, 0)}
              </Tag>
              <Tag style={{ margin: 0, background: `${LEVEL_COLOR.error}1a`, color: LEVEL_COLOR.error, border: `1px solid ${LEVEL_COLOR.error}` }}>
                错误 {chartData.reduce((s, b) => s + b.error, 0)}
              </Tag>
              <Tag style={{ margin: 0, background: `${LEVEL_COLOR.warning}1a`, color: LEVEL_COLOR.warning, border: `1px solid ${LEVEL_COLOR.warning}` }}>
                警告 {chartData.reduce((s, b) => s + b.warning, 0)}
              </Tag>
            </Space>
          </div>
          <StackedBarChart data={chartData} colors={LEVEL_COLOR} />
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginTop: 10,
              paddingTop: 10,
              borderTop: `1px solid ${TOKENS.border}`,
            }}
          >
            <Space size={4} size-inline={4} align="center">
              <Text type="secondary" style={{ fontSize: 11 }}>
                自动刷新
              </Text>
              <Radio.Group
                size="small"
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(e.target.value)}
              >
                <Radio.Button value={0}>关</Radio.Button>
                <Radio.Button value={30}>30s</Radio.Button>
                <Radio.Button value={60}>1m</Radio.Button>
                <Radio.Button value={300}>5m</Radio.Button>
              </Radio.Group>
              <Text type="secondary" style={{ fontSize: 11, marginLeft: 12 }}>
                时间范围
              </Text>
              <Radio.Group size="small" defaultValue="24h">
                <Radio.Button value="1h">1h</Radio.Button>
                <Radio.Button value="24h">24h</Radio.Button>
                <Radio.Button value="7d">7d</Radio.Button>
                <Radio.Button value="custom">自定义</Radio.Button>
              </Radio.Group>
            </Space>
            <Text type="secondary" style={{ fontSize: 11 }}>
              最后更新:2026-07-08 10:00:00
            </Text>
          </div>
        </div>
        <div style={{ ...surfaceCardStyle, padding: 0 }}>
          <Tabs
            activeKey={tab}
            onChange={(k) => setTab(k as 'active' | 'history')}
            style={{ paddingLeft: 16, paddingTop: 8 }}
            items={[
              {
                key: 'active',
                label: (
                  <Space size={6}>
                    <span>活跃告警</span>
                    <Tag color="red" style={{ margin: 0 }}>
                      {activeAlerts.length}
                    </Tag>
                  </Space>
                ),
              },
              {
                key: 'history',
                label: (
                  <Space size={6}>
                    <span>历史告警</span>
                    <Tag style={{ margin: 0 }}>{historyAlerts.length}</Tag>
                  </Space>
                ),
              },
            ]}
          />
          <Table
            size="middle"
            rowKey="key"
            pagination={false}
            dataSource={filtered}
            columns={columns}
          />
        </div>
      </Content>
      <AlertDetailDrawer
        open={drawer.open}
        alert={drawer.alert}
        initialTab={drawer.initialTab}
        onClose={() => setDrawer({ open: false, alert: null, initialTab: 'alert' })}
      />
    </div>
  );
}

/* ============================================================
 * 告警详情抽屉(从告警列表点告警标题打开)
 *  - 头部:LevelTag + 状态 + 度量 + 标题
 *  - 元信息行:服务/端点/版本/规则/触发时间
 *  - Tabs:告警 | 事件
 *  - 告警 tab:对齐 monitor Information(Descriptions + 触发时快照图 + 关闭按钮)
 *  - 事件 tab:对齐 monitor(热力图 + 简单时间轴列表,只展示该告警关联的事件)
 * ============================================================ */

/**
 * 告警 tab 内容(对齐 monitor Information)
 *  - Descriptions 2 列带边框(时间/级别/首次告警时间/告警信息/资产类型/资产/资产组/策略名/通知/操作人/通知人)
 *  - 触发时快照图(告警前后窗口折线图,带阈值线)
 *  - 关闭告警按钮(status==='new' 可用)
 */
function AlertTabContent({ alert: a }: { alert: EnrichedAlert }) {
  return (
    <div>
      {/* 告警信息表(对齐 monitor Descriptions 2 列) */}
      <Descriptions
        title="告警信息"
        column={2}
        bordered
        size="small"
        labelStyle={{ width: 110, color: TOKENS.textSecondary }}
      >
        <Descriptions.Item label="时间">
          {a.triggerAt}
        </Descriptions.Item>
        <Descriptions.Item label="级别">
          <div
            style={{
              borderLeft: `4px solid ${LEVEL_COLOR[a.level]}`,
              paddingLeft: 8,
              color: LEVEL_COLOR[a.level],
              fontWeight: 600,
            }}
          >
            {LEVEL_LABEL[a.level]}
          </div>
        </Descriptions.Item>
        <Descriptions.Item label="首次告警时间">
          2026-07-08 09:42:00
        </Descriptions.Item>
        <Descriptions.Item label="所属对象" span={2}>
          <Space size={4} direction="vertical" style={{ lineHeight: 1.3 }}>
            <a style={{ color: TOKENS.primary, fontSize: 13 }}>{a.service}</a>
            {a.endpoint && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {a.endpoint}
              </Text>
            )}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="所属版本">
          {a.version || '--'}
        </Descriptions.Item>
        <Descriptions.Item label="关联规则" span={2}>
          <code style={{ background: TOKENS.bg, padding: '2px 6px', borderRadius: 3, fontSize: 12 }}>
            {a.rule}
          </code>
        </Descriptions.Item>
        <Descriptions.Item label="度量">
          <Space size={4}>
            <MetricTag metric={a.metric} />
            <Text type="secondary" style={{ fontSize: 11 }}>
              {GROUP_LABEL[a.endpoint ? 'endpoint' : a.version ? 'version' : 'none']}
            </Text>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="阈值">
          <span style={tabularNumStyle}>
            &gt; {a.threshold} {METRIC_UNIT[a.metric]}
          </span>
        </Descriptions.Item>
        {a.state === 'closed' && (
          <Descriptions.Item label="告警结束时间">
            {a.recoverAt || '--'}
          </Descriptions.Item>
        )}
        <Descriptions.Item label="通知">
          {a.notified ? (
            <Tag color="success" style={{ margin: 0 }}>
              <CheckOutlined /> 已通知
            </Tag>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>未通知</Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="操作人">
          {a.operator || '--'}
        </Descriptions.Item>
        <Descriptions.Item label="通知人">
          sre.wang, sre.li
        </Descriptions.Item>
      </Descriptions>

      {/* 关闭告警按钮(对齐 monitor) */}
      <div style={{ marginTop: 12 }}>
        <Button
          type="primary"
          danger
          disabled={a.state !== 'new'}
        >
          关闭告警
        </Button>
      </div>

      {/* 触发时快照图(对齐 monitor LineChart) */}
      <div
        style={{
          ...surfaceCardStyle,
          padding: '14px 16px',
          marginTop: 16,
        }}
      >
        <Title level={5} style={{ margin: 0, marginBottom: 4 }}>
          触发时快照
          <Text type="secondary" style={{ fontSize: 11, fontWeight: 400, marginLeft: 8 }}>
            告警前后 1 小时 · {METRIC_LABEL[a.metric]}({METRIC_UNIT[a.metric]})
          </Text>
        </Title>
        <div style={{ height: 220, position: 'relative' }}>
          <SnapshotLineChart metric={a.metric} threshold={a.threshold} />
        </div>
      </div>
    </div>
  );
}

/**
 * 触发时快照图(SVG 自绘,告警前后 1 小时)
 * 折线 + 阈值线 + 触发点标红
 */
function SnapshotLineChart({
  metric,
  threshold,
}: {
  metric: AlertMetric;
  threshold: string;
}) {
  // mock 60 个数据点(告警前 30 + 告警后 30,每点 1 分钟)
  const points = React.useMemo(() => {
    const arr: { x: number; y: number }[] = [];
    const th = Number(threshold);
    const baseline =
      metric === 'error_rate' ? 20 :
      metric === 'throughput' ? 280 :
      metric === 'p99' ? 320 :
      180;
    for (let i = 0; i < 60; i += 1) {
      // 告警前稳定,告警时(i=30)飙升,告警后慢慢回落
      let v: number;
      if (i < 25) {
        v = baseline + Math.sin(i * 0.3) * 8 + (i % 4) * 2;
      } else if (i < 32) {
        v = baseline + (i - 25) * 18 + Math.random() * 10;
      } else if (i < 45) {
        v = th * 1.4 + (Math.random() - 0.5) * 30;
      } else {
        v = baseline * 1.2 + (i - 45) * 4 + (Math.random() - 0.5) * 8;
      }
      arr.push({ x: i, y: v });
    }
    return arr;
  }, [metric, threshold]);

  const th = Number(threshold);
  const W = 800;
  const H = 220;
  const PAD_L = 36;
  const PAD_R = 12;
  const PAD_T = 12;
  const PAD_B = 24;
  const chartW = W - PAD_L - PAD_R;
  const chartH = H - PAD_T - PAD_B;
  const yMax = Math.max(...points.map((p) => p.y), th * 1.5) * 1.1;
  const yMin = 0;
  const toX = (i: number) => PAD_L + (i / 59) * chartW;
  const toY = (v: number) => PAD_T + chartH - ((v - yMin) / (yMax - yMin)) * chartH;
  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.x).toFixed(1)},${toY(p.y).toFixed(1)}`)
    .join(' ');
  const areaD = `${pathD} L${toX(59).toFixed(1)},${(PAD_T + chartH).toFixed(1)} L${toX(0).toFixed(1)},${(PAD_T + chartH).toFixed(1)} Z`;
  const thY = toY(th);

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {/* 网格 */}
      {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
        const y = PAD_T + chartH * p;
        const v = yMax - (yMax - yMin) * p;
        return (
          <g key={i}>
            <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="#eef2f6" strokeWidth={1} />
            <text x={PAD_L - 4} y={y + 3} textAnchor="end" fontSize={10} fill={TOKENS.textTertiary}>
              {Math.round(v)}
            </text>
          </g>
        );
      })}
      {/* 告警时段背景(30-45) */}
      <rect
        x={toX(30)}
        y={PAD_T}
        width={toX(45) - toX(30)}
        height={chartH}
        fill={`${TOKENS.danger}10`}
      />
      <text x={toX(37.5)} y={PAD_T + 12} textAnchor="middle" fontSize={10} fill={TOKENS.danger}>
        告警时段
      </text>
      {/* 阈值线 */}
      <line
        x1={PAD_L}
        y1={thY}
        x2={W - PAD_R}
        y2={thY}
        stroke={TOKENS.danger}
        strokeWidth={1.5}
        strokeDasharray="4 4"
      />
      <text x={W - PAD_R - 4} y={thY - 4} textAnchor="end" fontSize={10} fill={TOKENS.danger}>
        阈值 {th} {METRIC_UNIT[metric]}
      </text>
      {/* 面积 + 折线 */}
      <path d={areaD} fill={`${TOKENS.primary}15`} />
      <path d={pathD} fill="none" stroke={TOKENS.primary} strokeWidth={1.5} />
      {/* 触发点 */}
      <circle cx={toX(30)} cy={toY(points[30].y)} r={4} fill={TOKENS.danger} stroke="#fff" strokeWidth={2} />
      {/* X 轴标签 */}
      {[-30, -20, -10, 0, 10, 20, 30].map((offset, i) => {
        const x = toX(30 + offset);
        return (
          <text key={i} x={x} y={H - 6} textAnchor="middle" fontSize={10} fill={TOKENS.textTertiary}>
            {offset === 0 ? '触发' : `${offset > 0 ? '+' : ''}${offset}m`}
          </text>
        );
      })}
    </svg>
  );
}

/* ============================================================
 * 事件 tab 内容(对齐 monitor event tab)
 *  - 顶部 EventHeatMap(7d × 24h 事件分布)
 *  - 列表:时间 + 内容(endpoint path)+ 值(对齐 monitor timeline row)
 *  - 事件范围:只展示该告警 service(+ endpoint 限定)的事件
 * ============================================================ */

interface ApmEvent {
  time: string;       // '09:42:18'
  content: string;    // 'POST /pay'(对齐 monitor 事件 content)
  value: string;      // 'HTTP 502' / '1240ms'(对齐 monitor 事件 value)
}

// 7×24 热力图 cell 颜色(0 / 1-3 / 4-7 / 8-15 / 16+)
function getHeatColor(count: number): string {
  if (count === 0) return '#f0f0f0';
  if (count <= 3) return '#dbeafe';
  if (count <= 7) return '#93c5fd';
  if (count <= 15) return '#3b82f6';
  return '#dc2626';
}

function getHeatLabel(count: number): string {
  if (count === 0) return '无';
  if (count <= 3) return '少量';
  if (count <= 7) return '中等';
  if (count <= 15) return '密集';
  return '爆发';
}

/**
 * mock 7×24 事件分布矩阵
 * 围绕 a1 告警(payment-svc v2.4.1 错误率,7/8 09:42 触发)构造:
 *  - 7/8 当天 09-10 时段密集爆发,其他时段偶发
 *  - 其他天散布少量
 */
const HEATMAP_DAYS = ['7/2', '7/3', '7/4', '7/5', '7/6', '7/7', '7/8 (今)'];
const HEATMAP_MATRIX: number[][] = [
  [0, 0, 0, 0, 0, 0, 1, 2, 3, 2, 1, 1, 0, 0, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 2, 1, 1, 3, 2, 1, 0, 0, 0, 2, 1, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 1, 2, 1, 0, 1, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 3, 2, 2, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 4, 2, 1, 1, 2, 3, 1, 0, 0, 0, 0, 0, 0, 0],
  // 7/8(今):09-10 爆发
  [0, 0, 0, 0, 0, 0, 1, 2, 4, 16, 18, 8, 5, 4, 6, 3, 2, 1, 1, 0, 0, 0, 0, 0],
];

/**
 * mock 事件流(50 条,围绕 a1 告警 service=payment-svc,endpoint=空(聚合整个服务))
 * 全部事件都来自 payment-svc 各端点(POST /pay / POST /refund / GET /order)
 * 时段分布:9:30-9:38 偶发 → 9:38-9:42 升温 → 9:42-9:50 爆发 → 9:50-10:15 恢复
 */
const APM_EVENTS: ApmEvent[] = [
  { time: '09:30:12', content: 'POST /pay',     value: '32ms' },
  { time: '09:31:48', content: 'POST /refund',  value: '45ms' },
  { time: '09:33:05', content: 'GET /order',    value: '28ms' },
  { time: '09:34:22', content: 'POST /pay',     value: '512ms' },
  { time: '09:35:11', content: 'GET /order',    value: '52ms' },
  { time: '09:36:30', content: 'POST /pay',     value: '38ms' },
  { time: '09:37:18', content: 'POST /refund',  value: '28ms' },
  { time: '09:37:55', content: 'POST /pay',     value: '88ms' },
  { time: '09:38:20', content: 'POST /pay',     value: '780ms' },
  { time: '09:38:42', content: 'POST /pay',     value: 'HTTP 504' },
  { time: '09:39:08', content: 'POST /pay',     value: '1024ms' },
  { time: '09:39:33', content: 'POST /refund',  value: '2.1s 排队' },
  { time: '09:40:15', content: 'POST /pay',     value: '920ms' },
  { time: '09:40:48', content: 'POST /pay',     value: 'HTTP 500' },
  { time: '09:41:09', content: 'POST /pay',     value: '680ms' },
  { time: '09:41:32', content: 'POST /refund',  value: '1.5s 排队' },
  { time: '09:41:55', content: 'POST /pay',     value: '1240ms' },
  { time: '09:42:00', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:42:08', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:42:14', content: 'POST /refund',  value: 'HTTP 500' },
  { time: '09:42:18', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:42:30', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:42:48', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:43:12', content: 'POST /pay',     value: 'HTTP 500' },
  { time: '09:43:35', content: 'POST /pay',     value: '1480ms' },
  { time: '09:43:58', content: 'GET /order',    value: '920ms' },
  { time: '09:44:20', content: 'POST /refund',  value: 'HTTP 502' },
  { time: '09:44:55', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:45:30', content: 'POST /pay',     value: 'HTTP 500' },
  { time: '09:45:48', content: 'POST /pay',     value: '1120ms' },
  { time: '09:46:20', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:47:05', content: 'GET /order',    value: '2.4s 排队' },
  { time: '09:47:38', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:48:15', content: 'POST /refund',  value: '1320ms' },
  { time: '09:48:50', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:49:25', content: 'POST /pay',     value: '850ms' },
  { time: '09:50:30', content: 'POST /pay',     value: 'HTTP 502' },
  { time: '09:51:48', content: 'POST /pay',     value: '780ms' },
  { time: '09:52:55', content: 'POST /pay',     value: '1.8s 排队' },
  { time: '09:53:30', content: 'POST /pay',     value: '320ms' },
  { time: '09:55:10', content: 'POST /refund',  value: '680ms' },
  { time: '09:57:42', content: 'POST /pay',     value: '128ms' },
  { time: '10:00:18', content: 'POST /pay',     value: '152ms' },
  { time: '10:02:55', content: 'POST /pay',     value: '88ms' },
  { time: '10:05:30', content: 'POST /pay',     value: '520ms' },
  { time: '10:08:12', content: 'GET /order',    value: '45ms' },
  { time: '10:10:48', content: 'POST /refund',  value: '62ms' },
  { time: '10:12:25', content: 'GET /order',    value: '92ms' },
  { time: '10:14:18', content: 'POST /pay',     value: '48ms' },
  { time: '10:15:00', content: 'POST /pay',     value: '1.1s 排队' },
];

/**
 * 事件 tab 内容
 * - 顶部 EventHeatMap(SVG 自绘 7d × 24h)
 * - 列表:对齐 monitor timeline row — 时间(粗体) + 内容(endpoint) + 值(右对齐)
 * - 事件范围:严格限定到该告警 service(+ endpoint 限定)
 */
function EventTabContent({ alert: a }: { alert: EnrichedAlert }) {
  // 真实接口:按 alert.id / service / endpoint / 时间窗 查询事件流
  // mock 全部 50 条围绕 a1(service=payment-svc)构造,展示效果用
  const events = APM_EVENTS;
  const isAlertWindow = (t: string) => t >= '09:42:00' && t <= '09:50:00';

  return (
    <div>
      {/* 热力图 */}
      <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 12 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 10,
          }}
        >
          <Text style={{ fontSize: 13, fontWeight: 500 }}>
            事件分布 · 近 7 天 × 24h
          </Text>
          <Space size={8} align="center">
            <Text type="secondary" style={{ fontSize: 11 }}>
              密度:
            </Text>
            {[0, 3, 7, 15, 16].map((threshold, i) => (
              <Space size={3} key={i} align="center">
                <span
                  style={{
                    width: 12,
                    height: 12,
                    background: getHeatColor(threshold),
                    borderRadius: 2,
                    display: 'inline-block',
                    border: '1px solid #e5e7eb',
                  }}
                />
                <Text type="secondary" style={{ fontSize: 10 }}>
                  {getHeatLabel(threshold)}
                </Text>
              </Space>
            ))}
          </Space>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 520 }}>
            {/* 顶部小时刻度 */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '60px repeat(24, 1fr)',
                gap: 2,
                fontSize: 10,
                color: TOKENS.textTertiary,
                marginBottom: 4,
              }}
            >
              <div></div>
              {Array.from({ length: 24 }).map((_, h) => (
                <div
                  key={h}
                  style={{ textAlign: 'center', opacity: h % 3 === 0 ? 1 : 0.4 }}
                >
                  {h}
                </div>
              ))}
            </div>
            {/* 矩阵 */}
            {HEATMAP_DAYS.map((dayLabel, di) => (
              <div
                key={dayLabel}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '60px repeat(24, 1fr)',
                  gap: 2,
                  marginBottom: 2,
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    color: di === 6 ? TOKENS.primary : TOKENS.textSecondary,
                    display: 'flex',
                    alignItems: 'center',
                    fontWeight: di === 6 ? 600 : 400,
                  }}
                >
                  {dayLabel}
                </div>
                {HEATMAP_MATRIX[di].map((count, hi) => {
                  const isPeak = count >= 16;
                  return (
                    <Tooltip
                      key={hi}
                      title={`${dayLabel} ${hi}:00 - ${hi + 1}:00 · ${count} 条`}
                    >
                      <div
                        style={{
                          height: 18,
                          background: getHeatColor(count),
                          borderRadius: 2,
                          cursor: 'pointer',
                          border: isPeak ? '1px solid #991b1b' : '1px solid transparent',
                        }}
                      />
                    </Tooltip>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        <div
          style={{
            marginTop: 8,
            fontSize: 11,
            color: TOKENS.textTertiary,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <FireOutlined style={{ color: TOKENS.danger }} />
          红框为爆发时段(≥16 条)· 7/8 09-10 时为本次告警前后高密度事件段
        </div>
      </div>

      {/* 事件流列表(对齐 monitor timeline) */}
      <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 8,
          }}
        >
          <Text style={{ fontSize: 13, fontWeight: 500 }}>
            事件流(按时间倒序 · 共 {events.length} 条)
          </Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {a.service}
            {a.endpoint && ` · ${a.endpoint}`}
          </Text>
        </div>
        <div
          style={{
            maxHeight: 400,
            overflowY: 'auto',
            border: `1px solid ${TOKENS.border}`,
            borderRadius: 6,
          }}
        >
          {events.slice().reverse().map((e, idx) => {
            const isAlert = isAlertWindow(e.time);
            const isError = e.value.startsWith('HTTP');
            return (
              <div
                key={`${e.time}-${e.content}`}
                style={{
                  padding: '8px 12px',
                  borderBottom:
                    idx < events.length - 1 ? `1px solid ${TOKENS.border}` : 'none',
                  background: isAlert ? `${TOKENS.danger}06` : 'transparent',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                {/* 时间(对齐 monitor 加粗样式) */}
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: TOKENS.text,
                    width: 72,
                    ...tabularNumStyle,
                  }}
                >
                  {e.time}
                </span>
                {/* 内容(endpoint path, 对齐 monitor 内容) */}
                <span style={{ flex: 1, fontSize: 13, color: TOKENS.text }}>
                  {e.content}
                </span>
                {/* 值(对齐 monitor 值) */}
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: isError
                      ? TOKENS.danger
                      : isAlert
                        ? TOKENS.warning
                        : TOKENS.textSecondary,
                    width: 100,
                    textAlign: 'right',
                    ...tabularNumStyle,
                  }}
                >
                  {e.value}
                </span>
              </div>
            );
          })}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: TOKENS.textTertiary }}>
          红底高亮 = 告警触发时段(09:42:00 ~ 09:50:00)
        </div>
      </div>
    </div>
  );
}

/* ============================================================
 * 告警详情抽屉(对齐 monitor)
 *  - 头部:LevelTag + 状态 + 度量 + 标题 + 元信息
 *  - Tabs:告警 | 事件
 *  - 告警 tab = AlertTabContent
 *  - 事件 tab = EventTabContent
 * ============================================================ */
function AlertDetailDrawer({
  open,
  alert,
  initialTab = 'alert',
  onClose,
}: {
  open: boolean;
  alert: EnrichedAlert | null;
  initialTab?: 'alert' | 'event';
  onClose: () => void;
}) {
  const [tab, setTab] = React.useState<'alert' | 'event'>(initialTab);

  // 切换告警时重置 tab
  React.useEffect(() => {
    setTab(initialTab);
  }, [alert?.key, initialTab]);

  if (!alert) return null;
  const a = alert;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={880}
      title={
        <Space size={8} align="center" wrap>
          <StateTag state={a.state} />
          <LevelTag
            level={a.metric === 'error_rate' ? 'critical' : a.metric === 'throughput' ? 'warning' : 'error'}
          />
          <MetricTag metric={a.metric} />
          <span style={{ fontSize: 16, fontWeight: 600 }}>{a.title}</span>
        </Space>
      }
      closeIcon={<CloseOutlined />}
      styles={{
        body: { padding: '0 16px 16px', overflow: 'hidden', display: 'flex', flexDirection: 'column' },
      }}
      footer={
        <div>
          <Button onClick={onClose}>取消</Button>
        </div>
      }
    >
      {/* 元信息行 */}
      <div
        style={{
          padding: '10px 0',
          color: TOKENS.textSecondary,
          fontSize: 12,
          borderBottom: `1px solid ${TOKENS.border}`,
          display: 'flex',
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <span>
          所属服务{' '}
          <a style={{ color: TOKENS.primary }}>{a.service}</a>
        </span>
        {a.endpoint && (
          <span>
            所属端点{' '}
            <a style={{ color: TOKENS.primary }}>{a.endpoint}</a>
          </span>
        )}
        {a.version && (
          <span>
            所属版本 <Text style={{ fontSize: 12 }}>{a.version}</Text>
          </span>
        )}
        <span>
          关联规则{' '}
          <code style={{ background: TOKENS.bg, padding: '0 4px', borderRadius: 3 }}>{a.rule}</code>
        </span>
        <span>
          触发时间 <Text style={{ fontSize: 12 }}>{a.triggerAt}</Text>
        </span>
      </div>

      {/* Tabs */}
      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as 'alert' | 'event')}
        style={{ marginTop: 4 }}
        items={[
          { key: 'alert', label: '告警' },
          { key: 'event', label: '事件' },
        ]}
      />

      {/* 内容区:可滚动 */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          paddingBottom: 8,
        }}
      >
        {tab === 'alert' ? <AlertTabContent alert={a} /> : <EventTabContent alert={a} />}
      </div>
    </Drawer>
  );
}

/* ============================================================
 * 策略(列表)
 * ============================================================ */
const POLICIES = [
  {
    key: 'p1',
    name: '支付服务错误率 > 80%',
    metric: 'error_rate' as AlertMetric,
    group: 'none' as 'none' | 'version' | 'endpoint',
    service: 'payment-svc',
    endpoint: '',
    version: '',
    threshold: '80',
    compare: '>',
    channels: ['邮件', 'NATS 告警中心', '企微'],
    enabled: true,
    triggerCount: 14,
  },
  {
    key: 'p2',
    name: '所有服务 P99 时延 > 800ms',
    metric: 'p99' as AlertMetric,
    group: 'none' as 'none' | 'version' | 'endpoint',
    service: '全部服务',
    endpoint: '',
    version: '',
    threshold: '800',
    compare: '>',
    channels: ['邮件', '飞书'],
    enabled: true,
    triggerCount: 38,
  },
  {
    key: 'p3',
    name: 'checkout-api 按端点错误率 > 5%',
    metric: 'error_rate' as AlertMetric,
    group: 'endpoint' as 'none' | 'version' | 'endpoint',
    service: 'checkout-api',
    endpoint: '全部端点',
    version: '',
    threshold: '5',
    compare: '>',
    channels: ['邮件'],
    enabled: true,
    triggerCount: 6,
  },
  {
    key: 'p4',
    name: '支付 / 下单按版本 P95 > 300ms',
    metric: 'p95' as AlertMetric,
    group: 'version' as 'none' | 'version' | 'endpoint',
    service: 'payment-svc, checkout-api',
    endpoint: '',
    version: '全部版本',
    threshold: '300',
    compare: '>',
    channels: ['NATS 告警中心', '邮件'],
    enabled: true,
    triggerCount: 11,
  },
  {
    key: 'p5',
    name: 'user-svc 吞吐 < 100 req/s',
    metric: 'throughput' as AlertMetric,
    group: 'none' as 'none' | 'version' | 'endpoint',
    service: 'user-svc',
    endpoint: '',
    version: '',
    threshold: '100',
    compare: '<',
    channels: ['邮件'],
    enabled: false,
    triggerCount: 2,
  },
];

type EnrichedPolicy = (typeof POLICIES)[number] & {
  createdBy: string;
  createdAt: string;
  lastRunAt: string;
};

function PoliciesList() {
  // mock: 派生创建人 / 创建时间 / 最后执行时间
  const enrichedPolicies: EnrichedPolicy[] = POLICIES.map((p, i) => ({
    ...p,
    createdBy: i % 2 === 0 ? 'sre.zhang' : 'sre.li',
    createdAt: `2026-06-${10 + i} 14:0${i}`,
    lastRunAt: `2026-07-08 09:${(40 + i).toString().padStart(2, '0')}`,
  }));
  return (
    <div style={shellStyle}>
      <TopMenuBar active="events" />
      <EventsSubNav active="policies" />
      <Content style={{ padding: 24 }}>
        <div style={{ ...surfaceCardStyle, padding: '12px 16px', marginBottom: 16 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Space size={8} align="center">
              <SettingOutlined style={{ color: TOKENS.primary }} />
              <Title level={4} style={{ margin: 0 }}>
                告警策略
              </Title>
            </Space>
            <Space>
              <Input
                size="small"
                placeholder="搜索策略名称"
                prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
                style={{ width: 240 }}
                allowClear
              />
              <Button type="primary" icon={<PlusOutlined />} href="?path=/story/apm-events-pages--policy-edit">
                新建策略
              </Button>
            </Space>
          </div>
        </div>
        <div style={{ ...surfaceCardStyle, padding: 0 }}>
          <Table
            size="middle"
            rowKey="key"
            pagination={false}
            dataSource={enrichedPolicies}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            columns={[
              // 名称(纯文本,monitor 列表 name 列无 link)
              {
                title: '策略名称',
                dataIndex: 'name',
                width: 260,
                render: (v: string) => <span style={{ fontWeight: 500 }}>{v}</span>,
              },
              // 监控对象(monitor monitoringTarget) — 作用服务 + 端点
              {
                title: '监控对象',
                key: 'target',
                width: 220,
                render: (_: unknown, r: EnrichedPolicy) => (
                  <Space size={4} direction="vertical" style={{ lineHeight: 1.3 }}>
                    <span style={{ fontSize: 13 }}>{r.service}</span>
                    {r.endpoint && (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {r.endpoint}
                      </Text>
                    )}
                  </Space>
                ),
              },
              // 创建人(monitor created_by)
              {
                title: '创建人',
                dataIndex: 'createdBy',
                width: 110,
                render: (v: string) => (
                  <Space size={6}>
                    <span
                      style={{
                        width: 22,
                        height: 22,
                        borderRadius: '50%',
                        background: TOKENS.primary,
                        color: '#fff',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 11,
                        fontWeight: 600,
                      }}
                    >
                      {v.slice(0, 1).toUpperCase()}
                    </span>
                    <span style={{ fontSize: 12 }}>{v}</span>
                  </Space>
                ),
              },
              // 创建时间(monitor created_at)
              {
                title: '创建时间',
                dataIndex: 'createdAt',
                width: 150,
                render: (v: string) => (
                  <Space size={4}>
                    <ClockCircleOutlined style={{ color: TOKENS.textTertiary, fontSize: 11 }} />
                    <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{v}</span>
                  </Space>
                ),
              },
              // 执行时间(monitor last_run_time)
              {
                title: '执行时间',
                dataIndex: 'lastRunAt',
                width: 150,
                render: (v: string) => (
                  <Space size={4}>
                    <ClockCircleOutlined style={{ color: TOKENS.textTertiary, fontSize: 11 }} />
                    <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{v}</span>
                  </Space>
                ),
              },
              // 启停(monitor effective / enable) — Switch
              {
                title: '启停',
                dataIndex: 'enabled',
                width: 80,
                render: (v: boolean) => (
                  <Switch
                    size="small"
                    checked={v}
                    checkedChildren={<CheckOutlined />}
                    unCheckedChildren={<CloseCircleOutlined />}
                  />
                ),
              },
              // 操作(monitor action) — 编辑 + 删除
              {
                title: '操作',
                key: 'action',
                dataIndex: 'action',
                width: 140,
                fixed: 'right',
                render: () => (
                  <Space size={4}>
                    <Button type="link" style={{ padding: 0 }} icon={<EditOutlined />}>
                      编辑
                    </Button>
                    <Popconfirm
                      title="确定删除该策略?"
                      description="删除后不可恢复"
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button type="link" danger style={{ padding: 0 }} icon={<DeleteOutlined />}>
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ] as any}
          />
        </div>
      </Content>
    </div>
  );
}

/* ============================================================
  );
}

/* ============================================================
 * 策略编辑(对齐 monitor strategy/detail 的样式和交互)
 *  - 没有外层 card 包裹整个 form(直接 PageFrame 风格的步骤)
 *  - 步骤 description 直接放 Form,无 padding+bg 嵌套
 *  - Form.Item label 宽度 100px(monitor clusterLabel.label)
 *  - 阈值表格布局(monitor ThresholdList)
 *  - 右侧:变量表(用 antd Table)+ 指标预览
 * ============================================================ */

/** 模板变量表(对齐 monitor VariablesTable — 表格布局,变量/描述/操作) */
const POLICY_VARIABLES: { v: string; d: string }[] = [
  { v: '${service}', d: '服务名' },
  { v: '${endpoint}', d: '端点' },
  { v: '${version}', d: '版本' },
  { v: '${metric}', d: '指标' },
  { v: '${current_value}', d: '当前值' },
  { v: '${threshold}', d: '阈值' },
  { v: '${level}', d: '告警级别' },
  { v: '${alert_name}', d: '告警名' },
  { v: '${trigger_at}', d: '触发时间' },
  { v: '${group_by}', d: '分组维度' },
];

/** 通知通道(对齐 monitor NotificationForm) */
const NOTIFY_CHANNELS = [
  { value: 'email', label: '邮件' },
  { value: 'wecom', label: '企微' },
  { value: 'feishu', label: '飞书' },
  { value: 'dingtalk', label: '钉钉' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'nats', label: 'NATS 告警中心' },
];

/** 阈值表单项(对齐 monitor ThresholdList — 表格布局) */
const APM_THRESHOLD_LIST: {
  level: 'critical' | 'error' | 'warning';
  compare: string;
  value: number | null;
}[] = [
  { level: 'critical', compare: '>', value: 80 },
  { level: 'error', compare: '>', value: 50 },
  { level: 'warning', compare: '>', value: null },
];

// 统一 Form.Item 字段宽度(monitor 字段不全宽,input 限宽 360)
const inputStyle: React.CSSProperties = { width: 360 };

/** mock 指标预览(对齐 monitor MetricPreview) */
function MetricPreviewMock() {
  const W = 460;
  const H = 200;
  const points: { x: number; y: number }[] = [];
  for (let i = 0; i < 40; i += 1) {
    const base = 40 + Math.sin(i * 0.4) * 12;
    const v = i > 30 ? base + (i - 30) * 6 : base + (Math.random() - 0.5) * 8;
    points.push({ x: i, y: v });
  }
  const max = Math.max(...points.map((p) => p.y));
  const toX = (i: number) => 28 + (i / 39) * (W - 40);
  const toY = (v: number) => 12 + (1 - v / (max * 1.1)) * (H - 36);
  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${toX(p.x).toFixed(1)},${toY(p.y).toFixed(1)}`)
    .join(' ');
  return (
    <svg width="100%" height="200" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
        <line
          key={i}
          x1={28}
          y1={12 + p * (H - 36)}
          x2={W - 12}
          y2={12 + p * (H - 36)}
          stroke="#eef2f6"
          strokeWidth={1}
        />
      ))}
      <line
        x1={28}
        y1={toY(80)}
        x2={W - 12}
        y2={toY(80)}
        stroke={TOKENS.danger}
        strokeWidth={1.2}
        strokeDasharray="4 3"
      />
      <text x={W - 14} y={toY(80) - 4} textAnchor="end" fontSize={10} fill={TOKENS.danger}>
        阈值 80
      </text>
      <path d={pathD} fill="none" stroke={TOKENS.primary} strokeWidth={1.5} />
    </svg>
  );
}

function PolicyEdit() {
  const [noticeOn, setNoticeOn] = useState(true);
  const [selectedChannels, setSelectedChannels] = useState<string[]>(['email', 'nats']);

  return (
    <div style={shellStyle}>
      <TopMenuBar active="events" />
      <EventsSubNav active="policies" />
      <Content style={{ padding: 24 }}>
        <Space style={{ marginBottom: 12 }}>
          <a
            style={{ color: TOKENS.textSecondary, fontSize: 13 }}
            href="?path=/story/apm-events-pages--policies-list"
          >
            ← 返回策略列表
          </a>
        </Space>
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
          {/* 左侧 4 步 Steps(对齐 monitor,无外层 card 包裹) */}
          <div style={{ flex: 1, minWidth: 0, maxWidth: 820 }}>
            <Form
              layout="horizontal"
              labelCol={{ style: { width: 100, color: TOKENS.text } }}
            >
              <Steps
                direction="vertical"
                current={0}
                items={[
                  // 步骤 1:基本信息(对齐 monitor BasicInfoForm — Form 字段直列,无 padding 嵌套)
                  {
                    title: '基本信息',
                    description: (
                      <div>
                        <Form.Item label="策略名称" required>
                          <Input
                            placeholder="如:结账错误率"
                            defaultValue="结账错误率"
                            style={inputStyle}
                          />
                        </Form.Item>
                        <Form.Item
                          label="告警名称"
                          required
                          tooltip="变量可从右侧变量表复制粘贴"
                        >
                          <Input
                            placeholder="${service} 错误率 > ${threshold}"
                            defaultValue="${service} 错误率 > ${threshold}"
                            style={inputStyle}
                          />
                        </Form.Item>
                        <Form.Item label="检测频率" required>
                          <InputNumber
                            min={1}
                            max={60}
                            defaultValue={1}
                            addonAfter="分钟"
                            style={inputStyle}
                          />
                        </Form.Item>
                      </div>
                    ),
                    status: 'process',
                  },
                  // 步骤 2:指标定义(对齐 monitor MetricDefinitionForm)
                  {
                    title: '指标定义',
                    description: (
                      <div>
                        <Form.Item label="服务" required>
                          <Input
                            placeholder="选择或输入服务"
                            defaultValue="checkout-api"
                            style={inputStyle}
                          />
                        </Form.Item>
                        <Form.Item
                          label="端点"
                          help={
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              不选则按服务级别监控(整体聚合)
                            </Text>
                          }
                        >
                          <Select
                            mode="multiple"
                            allowClear
                            placeholder="选择需要监控的端点"
                            style={inputStyle}
                            defaultValue={['POST /checkout', 'GET /cart']}
                            options={[
                              { value: 'POST /checkout', label: 'POST /checkout' },
                              { value: 'GET /cart', label: 'GET /cart' },
                              { value: 'POST /pay', label: 'POST /pay' },
                              { value: 'GET /order', label: 'GET /order' },
                              { value: 'POST /refund', label: 'POST /refund' },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item label="指标" required>
                          <Select
                            defaultValue="error_rate"
                            style={inputStyle}
                            options={[
                              { value: 'error_rate', label: '错误率' },
                              { value: 'p99', label: 'P99 时延' },
                              { value: 'p95', label: 'P95 时延' },
                              { value: 'throughput', label: '吞吐' },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item label="汇聚周期" required>
                          <InputNumber
                            min={1}
                            max={60}
                            defaultValue={5}
                            style={inputStyle}
                            addonAfter="分钟"
                          />
                        </Form.Item>
                        <Form.Item label="汇聚方法" required>
                          <Select
                            defaultValue="avg_over_time"
                            style={inputStyle}
                            options={[
                              { value: 'avg_over_time', label: 'avg_over_time' },
                              { value: 'last_over_time', label: 'last_over_time' },
                              { value: 'max_over_time', label: 'max_over_time' },
                              { value: 'min_over_time', label: 'min_over_time' },
                            ]}
                          />
                        </Form.Item>
                      </div>
                    ),
                    status: 'process',
                  },
                  // 步骤 3:告警条件(对齐 monitor AlertConditionsForm)
                  {
                    title: '告警条件',
                    description: (
                      <div>
                        {/* 阈值表(monitor ThresholdList — 表格布局) */}
                        <div style={{ marginBottom: 24 }}>
                          <div
                            style={{
                              fontSize: 13,
                              fontWeight: 600,
                              marginBottom: 8,
                              color: TOKENS.text,
                            }}
                          >
                            3 级别阈值
                          </div>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey="level"
                            dataSource={APM_THRESHOLD_LIST}
                            columns={[
                              {
                                title: '级别',
                                dataIndex: 'level',
                                width: 100,
                                render: (lvl: 'critical' | 'error' | 'warning') => (
                                  <Tag
                                    style={{
                                      margin: 0,
                                      background: `${LEVEL_COLOR[lvl]}1a`,
                                      color: LEVEL_COLOR[lvl],
                                      border: `1px solid ${LEVEL_COLOR[lvl]}`,
                                      fontWeight: 600,
                                    }}
                                  >
                                    {LEVEL_LABEL[lvl]}
                                  </Tag>
                                ),
                              },
                              {
                                title: '比较符',
                                dataIndex: 'compare',
                                width: 120,
                                render: (v: string) => (
                                  <Select
                                    size="small"
                                    defaultValue={v}
                                    style={{ width: '100%' }}
                                    options={[
                                      { value: 'gt', label: '>' },
                                      { value: 'gte', label: '≥' },
                                      { value: 'lt', label: '<' },
                                      { value: 'lte', label: '≤' },
                                    ]}
                                  />
                                ),
                              },
                              {
                                title: '阈值',
                                dataIndex: 'value',
                                width: 150,
                                render: (v: number | null) => (
                                  <InputNumber
                                    size="small"
                                    placeholder="不启用"
                                    defaultValue={v ?? undefined}
                                    style={{ width: '100%' }}
                                    addonAfter="%"
                                  />
                                ),
                              },
                            ]}
                          />
                        </div>
                        {/* 触发 / 恢复条件(对齐 monitor — label 100px + 冒号 + 12px 间距,inline help 同行) */}
                        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
                          <div
                            style={{
                              width: 100,
                              textAlign: 'right',
                              color: TOKENS.text,
                              paddingRight: 12,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            <span style={{ color: TOKENS.danger, marginRight: 2 }}>*</span>
                            触发条件:
                          </div>
                          <div style={{ flex: 1, color: TOKENS.textSecondary }}>
                            连续{' '}
                            <InputNumber
                              size="small"
                              min={1}
                              max={10}
                              defaultValue={1}
                              style={{ width: 60 }}
                            />{' '}
                            个汇聚周期结果满足告警阈值,触发告警。
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
                          <div
                            style={{
                              width: 100,
                              textAlign: 'right',
                              color: TOKENS.text,
                              paddingRight: 12,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            自动恢复:
                          </div>
                          <div style={{ flex: 1, color: TOKENS.textSecondary }}>
                            当连续{' '}
                            <InputNumber
                              size="small"
                              min={1}
                              max={10}
                              defaultValue={5}
                              style={{ width: 60 }}
                            />{' '}
                            个周期不满足阈值时,则告警自动恢复。
                          </div>
                        </div>
                        {/* 无数据告警(对齐 monitor — label + inline help 单行) */}
                        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
                          <div
                            style={{
                              width: 100,
                              textAlign: 'right',
                              color: TOKENS.text,
                              paddingRight: 12,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            无数据告警:
                          </div>
                          <div style={{ flex: 1, color: TOKENS.textSecondary }}>
                            当检测指标最近{' '}
                            <InputNumber
                              size="small"
                              min={1}
                              max={60}
                              defaultValue={5}
                              style={{ width: 60 }}
                            />{' '}
                            分钟查询结果为空时,触发{' '}
                            <Select
                              size="small"
                              defaultValue="critical"
                              style={{ width: 160 }}
                              options={[
                                { value: 'none', label: '不触发无数据告警' },
                                { value: 'critical', label: '触发严重告警' },
                                { value: 'error', label: '触发错误告警' },
                              ]}
                            />
                          </div>
                        </div>
                        {/* 无数据告警名称(label + input 同行,input 占满,help 下一行缩进) */}
                        <div style={{ marginBottom: 16 }}>
                          <div style={{ display: 'flex', alignItems: 'center' }}>
                            <div
                              style={{
                                width: 100,
                                textAlign: 'right',
                                color: TOKENS.text,
                                paddingRight: 12,
                                whiteSpace: 'nowrap',
                              }}
                            >
                              <span style={{ color: TOKENS.danger, marginRight: 2 }}>*</span>
                              无数据告警名称:
                            </div>
                            <Input
                              size="small"
                              placeholder="${monitor_object}${resource_name}产生${metric_name}无数据告警"
                              defaultValue="${monitor_object}${resource_name}产生${metric_name}无数据告警"
                              style={{ width: '100%' }}
                            />
                          </div>
                          <div
                            style={{
                              marginLeft: 112,
                              marginTop: 4,
                              color: TOKENS.text,
                              fontSize: 12,
                            }}
                          >
                            告警名称模板,变量从右侧变量表复制
                          </div>
                        </div>
                      </div>
                    ),
                    status: 'process',
                  },
                  // 步骤 4:通知配置(对齐 monitor NotificationForm)
                  {
                    title: '通知配置',
                    description: (
                      <div>
                        <Form.Item label="通知" required>
                          <Space size={8} align="center">
                            <Switch
                              size="small"
                              checked={noticeOn}
                              onChange={setNoticeOn}
                              checkedChildren={<CheckOutlined />}
                              unCheckedChildren={<CloseCircleOutlined />}
                            />
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {noticeOn ? '已开启' : '未开启'}
                            </Text>
                          </Space>
                        </Form.Item>
                        {noticeOn && (
                          <>
                            <Form.Item label="通知通道" required>
                              <Space size={[8, 8]} wrap>
                                {NOTIFY_CHANNELS.map((c) => {
                                  const checked = selectedChannels.includes(c.value);
                                  return (
                                    <Tag.CheckableTag
                                      key={c.value}
                                      checked={checked}
                                      onChange={() => {
                                        setSelectedChannels((prev) =>
                                          prev.includes(c.value)
                                            ? prev.filter((x) => x !== c.value)
                                            : [...prev, c.value]
                                        );
                                      }}
                                      style={{
                                        padding: '4px 12px',
                                        border: `1px solid ${
                                          checked ? TOKENS.primary : TOKENS.border
                                        }`,
                                        background: checked
                                          ? TOKENS.primarySoft
                                          : TOKENS.surface,
                                        color: checked
                                          ? TOKENS.primary
                                          : TOKENS.text,
                                      }}
                                    >
                                      {c.label}
                                    </Tag.CheckableTag>
                                  );
                                })}
                              </Space>
                            </Form.Item>
                            {!(
                              selectedChannels.length > 0 &&
                              selectedChannels.every((c) => c === 'nats')
                            ) && (
                              <Form.Item label="通知对象" required>
                                <Select
                                  mode="multiple"
                                  placeholder="选择接收人"
                                  defaultValue={['sre.wang', 'sre.li']}
                                  style={inputStyle}
                                  options={[
                                    { value: 'sre.wang', label: 'sre.wang' },
                                    { value: 'sre.li', label: 'sre.li' },
                                    { value: 'sre.zhang', label: 'sre.zhang' },
                                    { value: 'ops-team', label: '运维组' },
                                  ]}
                                />
                              </Form.Item>
                            )}
                          </>
                        )}
                      </div>
                    ),
                    status: 'process',
                  },
                ]}
              />
            </Form>
            {/* 底部 footer(对齐 monitor) */}
            <div
              style={{
                marginTop: 24,
                paddingTop: 16,
                borderTop: `1px solid ${TOKENS.border}`,
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 8,
              }}
            >
              <Button>取消</Button>
              <Button danger icon={<DeleteOutlined />}>
                删除
              </Button>
              <Button type="primary">保存策略</Button>
            </div>
          </div>

          {/* 右侧 变量表 + 指标预览(对齐 monitor) */}
          <div style={{ width: 400, flexShrink: 0, position: 'sticky', top: 16 }}>
            {/* 变量表(对齐 monitor VariablesTable — antd Table 布局) */}
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: TOKENS.text,
                  marginBottom: 8,
                }}
              >
                模板变量
              </div>
              <Table
                size="small"
                pagination={false}
                rowKey="v"
                dataSource={POLICY_VARIABLES}
                columns={[
                  {
                    title: '变量',
                    dataIndex: 'v',
                    width: 140,
                    render: (v: string) => (
                      <code style={{ color: TOKENS.primary, fontSize: 12 }}>{v}</code>
                    ),
                  },
                  {
                    title: '说明',
                    dataIndex: 'd',
                    render: (v: string) => (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {v}
                      </Text>
                    ),
                  },
                  {
                    title: '操作',
                    key: 'action',
                    width: 60,
                    render: (_: unknown, r: { v: string }) => (
                      <Button
                        type="link"
                        size="small"
                        style={{ padding: 0 }}
                        onClick={() => message.success(`已复制 ${r.v}`)}
                      >
                        复制
                      </Button>
                    ),
                  },
                ]}
              />
            </div>
            {/* 指标预览(对齐 monitor MetricPreview) */}
            <div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: TOKENS.text,
                  marginBottom: 4,
                }}
              >
                指标预览
              </div>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
                错误率(%) · 5 分钟 · 实时模拟
              </Text>
              <MetricPreviewMock />
            </div>
          </div>
        </div>
      </Content>
    </div>
  );
}

/* ============================================================
 * Story 注册
 * ============================================================ */
const meta = {
  title: 'APM/Events Pages',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const AlertsListStory: Story = {
  name: '事件 · 告警列表',
  render: () => <AlertsList />,
};

/**
 * 告警详情抽屉(默认打开,落在告警 tab)
 * 抽屉在告警列表页里点告警标题触发,这里抽出来便于评审同时看两个 tab
 */
function AlertDetailDrawerDemo({
  initialTab = 'alert',
}: {
  initialTab?: 'alert' | 'event';
}) {
  const [open, setOpen] = useState(true);
  // 用 ALERTS[0](a1:payment-svc 错误率 > 80%)作为演示告警
  const a: EnrichedAlert = React.useMemo(
    () => ({
      ...ALERTS[0],
      level: 'critical',
      notified: true,
      operator: 'sre.wang',
    }),
    []
  );
  return (
    <div style={shellStyle}>
      <TopMenuBar active="events" />
      <EventsSubNav active="alerts" />
      <Content style={{ padding: 24 }}>
        <div
          style={{
            ...surfaceCardStyle,
            padding: 16,
            textAlign: 'center',
            color: TOKENS.textSecondary,
          }}
        >
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
            抽屉默认打开 · 切换 tab 查看 &ldquo;告警&rdquo; / &ldquo;事件&rdquo; 两种内容
          </Text>
          <Space>
            <Button onClick={() => setOpen(true)}>重新打开抽屉</Button>
          </Space>
        </div>
      </Content>
      <AlertDetailDrawer
        open={open}
        alert={a}
        initialTab={initialTab}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}

export const AlertDetailDrawerStory: Story = {
  name: '事件 · 告警详情抽屉',
  render: () => <AlertDetailDrawerDemo initialTab="alert" />,
};

export const PoliciesListStory: Story = {
  name: '事件 · 策略列表',
  render: () => <PoliciesList />,
};

export const PolicyEditStory: Story = {
  name: '事件 · 策略编辑',
  render: () => <PolicyEdit />,
};
