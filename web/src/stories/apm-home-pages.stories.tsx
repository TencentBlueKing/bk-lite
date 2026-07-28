import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Collapse,
  Col,
  Layout,
  List,
  Progress,
  Row,
  Segmented,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  AppstoreOutlined,
  BellOutlined,
  BugOutlined,
  CaretRightOutlined,
  ClockCircleOutlined,
  CompassOutlined,
  FireOutlined,
  HistoryOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  RocketOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

const { Content } = Layout;
const { Title, Paragraph, Text } = Typography;

/* ============================================================
 * bklite APM · 首页 · 交互式故事书
 *
 * 关键架构(已对齐规格书《首页.md》):
 *  1) 5 张汇总卡(全局健康度 / 活跃服务 / SLO 违约 / 最近错误 / 最近部署)
 *  2) 首页是只读汇总,所有卡片内容来源于其他菜单的近窗数据
 *  3) 时间窗不可自定义(15min 活跃 / 1h SLO与错误 / 7d 部署)
 *  4) 不带同比 delta(避免猜测;趋势分析由"服务"菜单提供)
 *  5) 危险信号(严重/警告)优先,常态信息降级
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

const HEALTH_COLORS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: TOKENS.danger,
  2: TOKENS.warning,
  3: '#facc15',
  4: '#10b981',
  5: TOKENS.success,
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
  home: '?path=/story/apm-home-pages--home-dashboard',
  service: '?path=/story/apm-service-pages--service-directory-app-view',
  topology: '?path=/story/apm-service-pages--service-topology',
  slo: '?path=/story/apm-service-pages--service-slo-list',
  explore: '?path=/story/apm-explore-pages--traces-search',
  events: '?path=/story/apm-events-pages--alerts-list',
  integration: '?path=/story/apm-integration-pages-添加接入--integration-catalog-story',
};

/* ============================================================
 * 顶导(全局一级菜单):首页 / 服务 / 探索 / 事件 / 集成
 * 备注:"服务拓扑" 与 "SLO" 是"服务"一级菜单下的二级 tab,
 *      不在顶导中重复(规格书《服务.md》§3.1.1)。
 * ============================================================ */
function TopMenuBar({ active = 'home' }: { active?: string }) {
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
 * 首页工具栏(精简:仅"刷新全部"按钮,因为首页时间窗不可自定义)
 * ============================================================ */
function HomeToolbar({ onRefresh }: { onRefresh?: () => void }) {
  return (
    <div
      style={{
        ...surfaceCardStyle,
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 16,
      }}
    >
      <Space size={8} align="center">
        <Title level={4} style={{ margin: 0 }}>
          APM 看板
        </Title>
        <Text type="secondary" style={{ fontSize: 12 }}>
          全局汇总 · 各域近窗数据 · Group 隔离
        </Text>
      </Space>
      <Space size={8}>
        <Tooltip title="所有卡片使用统一近窗数据,首页时间窗不可自定义(15m 活跃 / 1h SLO与错误 / 7d 部署)">
          <Text type="secondary" style={{ fontSize: 12 }}>
            <ClockCircleOutlined style={{ marginRight: 4 }} />
            汇总于 {new Date().toLocaleString('zh-CN', { hour12: false })}
          </Text>
        </Tooltip>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          重新自检
        </Button>
      </Space>
    </div>
  );
}

/* ============================================================
 * 全局健康度大卡(顶部 1 张,横跨 5 个等级 + 总数)
 * 字段:严重/警告/待定/陈旧/健康/总数
 * ============================================================ */
function GlobalHealthCard() {
  // 模拟数据:基于"服务"菜单中各服务的健康分级统计
  const buckets = [
    { level: 1 as const, label: '严重', count: 2 },
    { level: 2 as const, label: '警告', count: 3 },
    { level: 3 as const, label: '关注', count: 4 },
    { level: 4 as const, label: '陈旧/失联', count: 1 },
    { level: 5 as const, label: '健康', count: 22 },
  ];
  const total = buckets.reduce((a, b) => a + b.count, 0);
  const danger = buckets[0].count + buckets[1].count;

  return (
    <div style={{ ...surfaceCardStyle, padding: '20px 24px', marginBottom: 16 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Space size={8} align="center">
          <ThunderboltOutlined style={{ color: TOKENS.primary, fontSize: 16 }} />
          <Title level={5} style={{ margin: 0 }}>
            全局健康度
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            汇总本 Group 内 {total} 个服务的健康分级
          </Text>
        </Space>
        <a
          href={STORY_URLS.service}
          style={{ color: TOKENS.primary, fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 2 }}
        >
          按健康严重度排序 <CaretRightOutlined />
        </a>
      </div>
      <Row gutter={[12, 12]}>
        {buckets.map((b) => {
          const c = HEALTH_COLORS[b.level];
          const isDanger = b.level <= 2;
          return (
            <Col span={4} key={b.level}>
              <div
                style={{
                  background: isDanger ? '#fef2f0' : TOKENS.surface,
                  border: `1px solid ${isDanger ? c : TOKENS.border}`,
                  borderRadius: 10,
                  padding: '14px 16px',
                  textAlign: 'center',
                  position: 'relative',
                }}
              >
                {isDanger && b.count > 0 && (
                  <Badge
                    count={b.count}
                    style={{
                      position: 'absolute',
                      top: -6,
                      right: -6,
                      background: c,
                    }}
                  />
                )}
                <div
                  style={{
                    fontSize: 26,
                    fontWeight: 700,
                    color: c,
                    lineHeight: 1.1,
                    ...tabularNumStyle,
                  }}
                >
                  {b.count}
                </div>
                <div style={{ fontSize: 12, color: TOKENS.textSecondary, marginTop: 4 }}>
                  {b.label}
                </div>
              </div>
            </Col>
          );
        })}
        <Col span={4}>
          <div
            style={{
              background: TOKENS.primarySoft,
              border: `1px solid ${TOKENS.primary}`,
              borderRadius: 10,
              padding: '14px 16px',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                fontSize: 26,
                fontWeight: 700,
                color: TOKENS.primary,
                lineHeight: 1.1,
                ...tabularNumStyle,
              }}
            >
              {total}
            </div>
            <div style={{ fontSize: 12, color: TOKENS.textSecondary, marginTop: 4 }}>
              总服务数
            </div>
          </div>
        </Col>
      </Row>
      {danger > 0 && (
        <Alert
          showIcon
          type="error"
          style={{ marginTop: 12, borderRadius: 6 }}
          message={
            <span>
              当前有 <b style={{ color: TOKENS.danger }}>{danger}</b> 个服务处于严重/警告状态,建议立即排查。
            </span>
          }
        />
      )}
    </div>
  );
}

/* ============================================================
 * 活跃服务(按环境分组:prod / staging / dev)
 * 服务清单字段:服务名、版本、吞吐、错误率、P99 时延
 * ============================================================ */
const ACTIVE_SERVICES = {
  prod: [
    { name: 'payment-svc', version: 'v5.3.0', throughput: '342/s', errorRate: '20%', p99: '265ms', health: 1 as 1 | 2 | 3 | 4 | 5 },
    { name: 'checkout-api', version: 'v3.1.3', throughput: '124/s', errorRate: '2.9%', p99: '358ms', health: 2 as 1 | 2 | 3 | 4 | 5 },
    { name: 'api-gateway', version: 'v2.8.0', throughput: '2.1k/s', errorRate: '0%', p99: '473ms', health: 4 as 1 | 2 | 3 | 4 | 5 },
    { name: 'catalog-api', version: 'v1.9.2', throughput: '1.4k/s', errorRate: '0.08%', p99: '64ms', health: 5 as 1 | 2 | 3 | 4 | 5 },
    { name: 'auth-svc', version: 'v3.0.2', throughput: '1.2k/s', errorRate: '0.05%', p99: '38ms', health: 5 as 1 | 2 | 3 | 4 | 5 },
  ],
  staging: [
    { name: 'payment-svc', version: 'v5.4.0-rc1', throughput: '46/s', errorRate: '0.3%', p99: '124ms', health: 5 as 1 | 2 | 3 | 4 | 5 },
    { name: 'notification-worker', version: 'v1.3.0-beta', throughput: '12/s', errorRate: '0%', p99: '88ms', health: 5 as 1 | 2 | 3 | 4 | 5 },
  ],
  dev: [
    { name: 'payment-svc', version: 'v5.5.0-dev', throughput: '4/s', errorRate: '0%', p99: '92ms', health: 5 as 1 | 2 | 3 | 4 | 5 },
  ],
};

function HealthDot({ level }: { level: 1 | 2 | 3 | 4 | 5 }) {
  return (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: HEALTH_COLORS[level],
        display: 'inline-block',
        flexShrink: 0,
      }}
    />
  );
}

function ActiveServicesCard() {
  const [env, setEnv] = useState<'prod' | 'staging' | 'dev'>('prod');
  const rows = ACTIVE_SERVICES[env];

  return (
    <div style={{ ...surfaceCardStyle, padding: '16px 18px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <AppstoreOutlined style={{ color: TOKENS.primary }} />
          <Title level={5} style={{ margin: 0 }}>
            活跃服务
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            近窗 15 分钟
          </Text>
        </Space>
        <a href={STORY_URLS.service} style={{ color: TOKENS.primary, fontSize: 12 }}>
          进入服务 →
        </a>
      </div>
      <Segmented
        size="small"
        value={env}
        onChange={(v) => setEnv(v as 'prod' | 'staging' | 'dev')}
        options={[
          { label: `生产 (${ACTIVE_SERVICES.prod.length})`, value: 'prod' },
          { label: `预发 (${ACTIVE_SERVICES.staging.length})`, value: 'staging' },
          { label: `开发 (${ACTIVE_SERVICES.dev.length})`, value: 'dev' },
        ]}
        style={{ marginBottom: 12 }}
      />
      <Table
        size="small"
        rowKey="name"
        pagination={false}
        dataSource={rows}
        columns={[
          {
            title: '服务',
            dataIndex: 'name',
            render: (v, r) => (
              <Space size={6} align="center">
                <HealthDot level={r.health} />
                <a style={{ color: TOKENS.primary }}>{v}</a>
              </Space>
            ),
          },
          { title: '版本', dataIndex: 'version', width: 100, render: (v) => <Tag style={{ margin: 0, fontFamily: 'monospace', fontSize: 11 }}>{v}</Tag> },
          {
            title: '吞吐',
            dataIndex: 'throughput',
            width: 70,
            align: 'right' as const,
            render: (v) => <span style={tabularNumStyle}>{v}</span>,
          },
          {
            title: '错误率',
            dataIndex: 'errorRate',
            width: 70,
            align: 'right' as const,
            render: (v) => {
              const n = parseFloat(v);
              const danger = !isNaN(n) && n >= 1;
              return (
                <span
                  style={{
                    ...tabularNumStyle,
                    color: danger ? TOKENS.danger : TOKENS.text,
                    fontWeight: danger ? 600 : 400,
                  }}
                >
                  {v}
                </span>
              );
            },
          },
          {
            title: 'P99',
            dataIndex: 'p99',
            width: 70,
            align: 'right' as const,
            render: (v, r) => {
              const num = parseInt(v, 10);
              const danger = r.health <= 2 && num > 200;
              return (
                <span
                  style={{
                    ...tabularNumStyle,
                    color: danger ? TOKENS.danger : TOKENS.text,
                    fontWeight: danger ? 600 : 400,
                  }}
                >
                  {v}
                </span>
              );
            },
          },
        ]}
      />
    </div>
  );
}

/* ============================================================
 * SLO 违约摘要
 * 字段:服务名、SLO 名称、剩余预算、燃尽率、违约状态、最近一次评估时间
 * ============================================================ */
const SLO_BREACH = [
  {
    key: '1',
    service: 'payment-svc',
    slo: '可用性 ≥ 99.9%',
    budget: 28,
    burn: 8.4,
    state: 'breach' as const,
    evaluated: '5 分钟前',
  },
  {
    key: '2',
    service: 'checkout-api',
    slo: 'P99 < 400ms',
    budget: 56,
    burn: 4.1,
    state: 'risk' as const,
    evaluated: '5 分钟前',
  },
  {
    key: '3',
    service: 'api-gateway',
    slo: '可用性 ≥ 99.5%',
    budget: 82,
    burn: 1.3,
    state: 'ok' as const,
    evaluated: '5 分钟前',
  },
];

function SloBreachCard() {
  return (
    <div style={{ ...surfaceCardStyle, padding: '16px 18px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <FireOutlined style={{ color: TOKENS.warning }} />
          <Title level={5} style={{ margin: 0 }}>
            SLO 违约摘要
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            近窗 1 小时
          </Text>
        </Space>
        <a href={STORY_URLS.slo} style={{ color: TOKENS.primary, fontSize: 12 }}>
          进入 SLO →
        </a>
      </div>
      <Table
        size="small"
        rowKey="key"
        pagination={false}
        dataSource={SLO_BREACH}
        columns={[
          {
            title: '服务',
            dataIndex: 'service',
            render: (v) => <a style={{ color: TOKENS.primary }}>{v}</a>,
          },
          { title: 'SLO', dataIndex: 'slo', width: 140 },
          {
            title: '剩余预算',
            dataIndex: 'budget',
            width: 110,
            render: (v) => {
              const danger = v <= 30;
              return (
                <Progress
                  percent={v}
                  size="small"
                  showInfo
                  strokeColor={danger ? TOKENS.danger : v <= 60 ? TOKENS.warning : TOKENS.success}
                  format={(p) => <span style={tabularNumStyle}>{p}%</span>}
                />
              );
            },
          },
          {
            title: '燃尽率',
            dataIndex: 'burn',
            width: 80,
            align: 'right' as const,
            render: (v) => {
              const danger = v >= 5;
              const warn = v >= 2;
              return (
                <span
                  style={{
                    ...tabularNumStyle,
                    color: danger ? TOKENS.danger : warn ? TOKENS.warning : TOKENS.text,
                    fontWeight: danger || warn ? 600 : 400,
                  }}
                >
                  {v.toFixed(1)}x
                </span>
              );
            },
          },
          {
            title: '状态',
            dataIndex: 'state',
            width: 80,
            render: (v) => {
              if (v === 'breach') return <Tag color="error" style={{ margin: 0 }}>违约</Tag>;
              if (v === 'risk') return <Tag color="warning" style={{ margin: 0 }}>高风险</Tag>;
              return <Tag color="success" style={{ margin: 0 }}>健康</Tag>;
            },
          },
        ]}
      />
    </div>
  );
}

/* ============================================================
 * 最近错误(Issue 列表:标题 / 影响服务 / 首现 / 累计 / 激增 / 状态)
 * ============================================================ */
const RECENT_ISSUES = [
  {
    key: '1',
    title: 'NullPointerException at PaymentService.charge',
    service: 'payment-svc',
    firstSeen: '12 分钟前',
    count: 142,
    spiking: true,
    state: '待分诊' as const,
  },
  {
    key: '2',
    title: 'HTTP 502 from upstream checkout-api',
    service: 'checkout-api',
    firstSeen: '38 分钟前',
    count: 24,
    spiking: false,
    state: '已分诊' as const,
  },
  {
    key: '3',
    title: '连接 Redis 超时 (read timeout 5s)',
    service: 'api-gateway',
    firstSeen: '1 小时前',
    count: 8,
    spiking: false,
    state: '已解决' as const,
    regression: true,
  },
];

function RecentIssuesCard() {
  return (
    <div style={{ ...surfaceCardStyle, padding: '16px 18px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <BugOutlined style={{ color: TOKENS.danger }} />
          <Title level={5} style={{ margin: 0 }}>
            最近错误
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            近窗 1 小时
          </Text>
        </Space>
        <Space size={4}>
          <Tag color="error" style={{ margin: 0 }}>
            激增 1
          </Tag>
          <Tag color="warning" style={{ margin: 0 }}>
            回归 1
          </Tag>
          <a href={STORY_URLS.explore} style={{ color: TOKENS.primary, fontSize: 12 }}>
            进入错误 →
          </a>
        </Space>
      </div>
      <List
        size="small"
        dataSource={RECENT_ISSUES}
        renderItem={(it) => (
          <List.Item style={{ padding: '10px 0' }}>
            <Space direction="vertical" size={4} style={{ flex: 1 }}>
              <Space size={6} align="center">
                {it.spiking && (
                  <Tag color="error" style={{ margin: 0 }}>
                    <FireOutlined /> 激增
                  </Tag>
                )}
                {it.regression && (
                  <Tag color="warning" style={{ margin: 0 }}>
                    <HistoryOutlined /> 回归
                  </Tag>
                )}
                <a style={{ color: TOKENS.text, fontSize: 13, fontWeight: 500 }}>{it.title}</a>
              </Space>
              <Space size={12} style={{ fontSize: 12, color: TOKENS.textTertiary }}>
                <span>服务 {it.service}</span>
                <span>·</span>
                <span>首现 {it.firstSeen}</span>
                <span>·</span>
                <span style={tabularNumStyle}>累计 {it.count} 次</span>
              </Space>
            </Space>
            <Tag
              style={{
                margin: 0,
                background:
                  it.state === '已分诊'
                    ? TOKENS.primarySoft
                    : it.state === '已解决'
                      ? '#dcfce7'
                      : '#fef2f0',
                color:
                  it.state === '已分诊'
                    ? TOKENS.primary
                    : it.state === '已解决'
                      ? TOKENS.success
                      : TOKENS.danger,
                border: 'none',
              }}
            >
              {it.state}
            </Tag>
          </List.Item>
        )}
      />
    </div>
  );
}

/* ============================================================
 * 最近部署(按服务分组,可折叠)
 * 字段:服务名 / 版本 / 部署时刻 / 来源 / 部署人
 * ============================================================ */
const RECENT_DEPLOYS = [
  {
    service: 'payment-svc',
    items: [
      { version: 'v5.4.0-rc1', time: '2 小时前', source: 'CI' as const, by: 'alice' },
      { version: 'v5.3.0', time: '6 天前', source: 'CI' as const, by: 'bob' },
    ],
  },
  {
    service: 'api-gateway',
    items: [
      { version: 'v2.8.0', time: '1 天前', source: 'CI' as const, by: 'carol' },
    ],
  },
  {
    service: 'auth-svc',
    items: [
      { version: 'v3.0.2', time: '5 天前', source: 'inferred' as const, by: '—' },
    ],
  },
];

function RecentDeploysCard() {
  return (
    <div style={{ ...surfaceCardStyle, padding: '16px 18px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <RocketOutlined style={{ color: TOKENS.success }} />
          <Title level={5} style={{ margin: 0 }}>
            最近部署
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            近窗 7 天 · 按服务分组
          </Text>
        </Space>
        <a href={STORY_URLS.service} style={{ color: TOKENS.primary, fontSize: 12 }}>
          进入服务 →
        </a>
      </div>
      <Collapse
        defaultActiveKey={RECENT_DEPLOYS.map((g) => g.service)}
        ghost
        size="small"
        items={RECENT_DEPLOYS.map((grp) => ({
          key: grp.service,
          label: (
            <Space size={6} align="center">
              <Text strong style={{ fontSize: 13 }}>{grp.service}</Text>
              <Tag style={{ margin: 0, fontSize: 11 }}>{grp.items.length} 次</Tag>
            </Space>
          ),
          children: (
            <div style={{ padding: '0 0 4px 4px' }}>
              {grp.items.map((d, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 0',
                    borderBottom: idx < grp.items.length - 1 ? `1px dashed ${TOKENS.border}` : 'none',
                  }}
                >
                  <Space size={8} align="center">
                    <Tag
                      style={{
                        margin: 0,
                        fontFamily: 'monospace',
                        fontSize: 11,
                        background: d.source === 'CI' ? TOKENS.primarySoft : TOKENS.bg,
                        color: d.source === 'CI' ? TOKENS.primary : TOKENS.textSecondary,
                        border: 'none',
                      }}
                    >
                      {d.version}
                    </Tag>
                    <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>{d.time}</Text>
                    <Text style={{ fontSize: 12, color: TOKENS.textTertiary }}>
                      {d.source === 'CI' ? 'CI 上报' : '推断'}
                    </Text>
                  </Space>
                  <Text style={{ fontSize: 12, color: TOKENS.textTertiary }}>{d.by}</Text>
                </div>
              ))}
            </div>
          ),
        }))}
      />
    </div>
  );
}

/* ============================================================
 * 空状态(未接入任何应用)
 * ============================================================ */
function HomeEmptyState() {
  return (
    <div
      style={{
        ...surfaceCardStyle,
        padding: '60px 24px',
        textAlign: 'center',
        marginTop: 24,
      }}
    >
      <RocketOutlined style={{ fontSize: 48, color: TOKENS.textTertiary, marginBottom: 16 }} />
      <Title level={4} style={{ marginBottom: 8 }}>
        还没有接入任何应用
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 20 }}>
        前往集成菜单完成首次接入,数分钟内即可在首页看到全局健康度与活跃服务。
      </Paragraph>
      <Space>
        <Button type="primary" icon={<RocketOutlined />} href={STORY_URLS.integration}>
          前往集成菜单
        </Button>
        <Button href={STORY_URLS.explore}>查看调用链示例</Button>
      </Space>
    </div>
  );
}

/* ============================================================
 * HomeDashboard · 完整首页
 * ============================================================ */
function HomeDashboard() {
  const [empty, setEmpty] = useState(false);
  return (
    <div style={shellStyle}>
      <TopMenuBar active="home" />
      <Content style={{ padding: 24 }}>
        <HomeToolbar onRefresh={() => undefined} />
        {empty ? (
          <HomeEmptyState />
        ) : (
          <>
            <GlobalHealthCard />
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={12}>
                <ActiveServicesCard />
              </Col>
              <Col xs={24} lg={12}>
                <SloBreachCard />
              </Col>
              <Col xs={24} lg={12}>
                <RecentIssuesCard />
              </Col>
              <Col xs={24} lg={12}>
                <RecentDeploysCard />
              </Col>
            </Row>
            <div style={{ marginTop: 16, textAlign: 'center' }}>
              <Button
                type="link"
                size="small"
                onClick={() => setEmpty(true)}
                style={{ color: TOKENS.textTertiary }}
              >
                预览空状态
              </Button>
            </div>
          </>
        )}
      </Content>
    </div>
  );
}

/* ============================================================
 * Story 注册
 * ============================================================ */
const meta = {
  title: 'APM/Home Pages',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const HomeDashboardStory: Story = {
  name: 'APM 首页 · 看板',
  render: () => <HomeDashboard />,
};
