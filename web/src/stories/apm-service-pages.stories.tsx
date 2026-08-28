import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useLayoutEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Col,
  Drawer,
  Dropdown,
  Input,
  InputNumber,
  Layout,
  List,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  BarsOutlined,
  BellOutlined,
  CloseOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  FilterOutlined,
  InboxOutlined,
  PlusOutlined,
  RadarChartOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';

const { Header, Content } = Layout;
const { Title, Paragraph, Text } = Typography;

/* ============================================================
 * bklite APM · 服务域 · 交互式故事书
 *
 * 关键架构(已对齐规格书《服务.md》§3.1):
 *  1) 服务菜单的"服务"页 = 唯一的应用/服务总览入口;无独立应用详情页
 *  2) 顶部二级导航 = 真跳转(跨 Story URL);视角切换器 = 真受控组件
 *  3) 应用卡片点击 → 当前页激活该应用的服务筛选(不跳路由)
 *  4) 服务名点击 → 当前页进入单服务详情(不跳路由)
 *  5) 已归档入口 = 右上角按钮 + Drawer 抽屉(可开关)
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
const HEALTH_LABELS = ['严重', '警告', '关注', '良好', '健康'];

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

/* ---------- 跨 Story URL(顶部二级导航跳转)---------- */
const STORY_URLS = {
  home: '?path=/story/apm-home-pages--home-dashboard-story',
  service: '?path=/story/apm-service-pages--service-directory-app-view',
  serviceList: '?path=/story/apm-service-pages--service-directory-service-view',
  appDetail: '?path=/story/apm-service-pages--service-app-detail',
  serviceDetail: '?path=/story/apm-service-pages--service-detail',
  topology: '?path=/story/apm-service-pages--service-topology',
  slo: '?path=/story/apm-service-pages--slo-list',
  empty: '?path=/story/apm-service-pages--service-empty',
  explore: '?path=/story/apm-explore-pages--traces-search-story',
  events: '?path=/story/apm-events-pages--alerts-list-story',
  integration: '?path=/story/apm-integration-pages-添加接入--integration-catalog-story',
};

/* ---------- 静态数据 ---------- */
interface AppCard {
  key: string;
  name: string;
  health: 1 | 2 | 3 | 4 | 5;
  throughput: string;
  errorRate: string;
  services: string[];
  isUncategorized?: boolean;
}

interface ServiceRow {
  key: string;
  name: string;
  namespace: string;
  env: string;
  version: string;
  health: 1 | 2 | 3 | 4 | 5;
  throughput: string;
  errorRate: string;
  p99: string;
  apdex: number;
  /** 主语言 — 影响服务列表「语言」列标签 */
  language: 'JV' | 'JS' | '.N' | 'GO' | 'PY';
  /** 最近部署相对时间,如「5 天前」 */
  lastDeploy?: string;
  /** 最近活跃相对时间,如「5 天前」 */
  lastActive?: string;
  /** 同一版本的发布增量,如 +1 / +2;undefined 表示无 */
  versionInc?: number;
  /** SLO 达标情况;undefined 表示未配置 */
  slo?: { met: boolean; currentRate: number; budget: number };
  /** 当前活跃告警(按最高等级染色);undefined 或 count=0 表示无告警 */
  activeAlerts?: { count: number; level: 1 | 2 | 3 | 4 | 5 };
  silent?: boolean;
}

const APPS: AppCard[] = [
  { key: 'iam', name: '用户与权限', health: 5, throughput: '2,140', errorRate: '0.1%', services: ['auth-svc', 'user-api'] },
  { key: 'billing', name: '交易清结算', health: 2, throughput: '884', errorRate: '2.4%', services: ['inventory-svc', 'payment-svc', 'checkout-api'] },
  { key: 'store', name: '电商主站', health: 4, throughput: '5,276', errorRate: '0.6%', services: ['catalog-api', 'api-gateway', 'web-storefront', 'web-cdn'] },
  { key: 'async', name: '异步任务', health: 4, throughput: '124', errorRate: '0.2%', services: ['notification-worker'] },
  { key: 'data', name: '数据平台', health: 5, throughput: '612', errorRate: '0.05%', services: ['etl-pipeline', 'cdc-worker'] },
  { key: 'uncategorized', name: '未归类应用', health: 3, throughput: '38', errorRate: '0.9%', services: ['legacy-portal', 'uninstrumented-job'], isUncategorized: true },
];

const SERVICE_OF: Record<string, ServiceRow> = {
  'auth-svc': { key: 'auth-svc', name: 'auth-svc', namespace: 'iam', env: 'prod', version: 'v3.0.2', health: 5, throughput: '1.2k', errorRate: '0.05%', p99: '38ms', apdex: 0.98, language: 'GO', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'user-api': { key: 'user-api', name: 'user-api', namespace: 'iam', env: 'prod', version: 'v2.0.7', health: 5, throughput: '940', errorRate: '0.12%', p99: '42ms', apdex: 0.96, language: 'GO', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'inventory-svc': { key: 'inventory-svc', name: 'inventory-svc', namespace: 'billing', env: 'prod', version: 'v1.4.1', health: 4, throughput: '418', errorRate: '3.0%', p99: '64ms', apdex: 0.86, language: '.N', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'payment-svc': { key: 'payment-svc', name: 'payment-svc', namespace: 'billing', env: 'prod', version: 'v5.3.0', health: 1, throughput: '342', errorRate: '20%', p99: '265ms', apdex: 0.62, language: 'JV', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 1, activeAlerts: { count: 3, level: 1 } },
  'checkout-api': { key: 'checkout-api', name: 'checkout-api', namespace: 'billing', env: 'prod', version: 'v3.1.3', health: 2, throughput: '124', errorRate: '2.9%', p99: '358ms', apdex: 0.78, language: 'JV', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 1, activeAlerts: { count: 2, level: 2 } },
  'catalog-api': { key: 'catalog-api', name: 'catalog-api', namespace: 'store', env: 'prod', version: 'v1.9.2', health: 5, throughput: '1.4k', errorRate: '0.08%', p99: '64ms', apdex: 0.95, language: 'JV', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'api-gateway': { key: 'api-gateway', name: 'api-gateway', namespace: 'store', env: 'prod', version: 'v2.8.0', health: 4, throughput: '2.1k', errorRate: '0%', p99: '473ms', apdex: 0.91, language: 'GO', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0, slo: { met: true, currentRate: 100, budget: 100 } },
  'web-storefront': { key: 'web-storefront', name: 'web-storefront', namespace: 'store', env: 'prod', version: 'v4.2.1', health: 4, throughput: '896', errorRate: '1.2%', p99: '506ms', apdex: 0.88, language: 'JS', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'notification-worker': { key: 'notification-worker', name: 'notification-worker', namespace: 'async', env: 'prod', version: 'v1.2.0', health: 2, throughput: '124', errorRate: '2.8%', p99: '102ms', apdex: 0.82, language: 'JS', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0, activeAlerts: { count: 1, level: 3 } },
  'etl-pipeline': { key: 'etl-pipeline', name: 'etl-pipeline', namespace: 'data', env: 'prod', version: 'v2.4.0', health: 5, throughput: '460', errorRate: '0.05%', p99: '212ms', apdex: 0.95, language: 'PY', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'cdc-worker': { key: 'cdc-worker', name: 'cdc-worker', namespace: 'data', env: 'prod', version: 'v1.1.4', health: 5, throughput: '152', errorRate: '0.03%', p99: '46ms', apdex: 0.97, language: 'JV', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'web-cdn': { key: 'web-cdn', name: 'web-cdn', namespace: 'store', env: 'prod', version: 'v1.0.7', health: 4, throughput: '2.8k', errorRate: '0.02%', p99: '24ms', apdex: 0.99, language: 'GO', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
  'legacy-portal': { key: 'legacy-portal', name: 'legacy-portal', namespace: '', env: 'prod', version: 'v0.9.0', health: 3, throughput: '24', errorRate: '1.2%', p99: '420ms', apdex: 0.74, language: '.N', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0, silent: true },
  'uninstrumented-job': { key: 'uninstrumented-job', name: 'uninstrumented-job', namespace: '', env: 'prod', version: '—', health: 3, throughput: '14', errorRate: '0.6%', p99: '320ms', apdex: 0.80, language: 'JV', lastDeploy: '5 天前', lastActive: '5 天前', versionInc: 0 },
};

const SERVICES: ServiceRow[] = Object.values(SERVICE_OF);

const ARCHIVED_ROWS = [
  { name: 'legacy-portal', app: '未归类应用(空)', env: 'prod', reason: '服务下线', reasonType: 'auto' as const, lastActive: '2026-04-12 14:20', keptDays: 90, pausedAlerts: 3 },
  { name: 'old-metrics-api', app: 'monitor', env: 'prod', reason: '迁移至 monitor-api', reasonType: 'manual' as const, lastActive: '2026-05-08 09:45', keptDays: 90, pausedAlerts: 1 },
  { name: 'test-payment', app: 'billing', env: 'staging', reason: '测试环境关闭', reasonType: 'manual' as const, lastActive: '2025-12-01 11:00', keptDays: 30, pausedAlerts: 0 },
];

/* ============================================================
 * 通用组件
 * ============================================================ */

function TopMenuBar() {
  const items = [
    { key: 'home', label: '首页', icon: <RadarChartOutlined />, href: STORY_URLS.home },
    { key: 'service', label: '服务', icon: <AppstoreOutlined />, href: STORY_URLS.service },
    { key: 'explore', label: '探索', icon: <SearchOutlined />, href: STORY_URLS.explore },
    { key: 'events', label: '事件', icon: <BellOutlined />, href: STORY_URLS.events },
    { key: 'integration', label: '集成', icon: <CloudUploadOutlined />, href: STORY_URLS.integration },
  ];
  return (
    <Header
      style={{
        background: TOKENS.surface,
        borderBottom: `1px solid ${TOKENS.border}`,
        padding: '0 20px',
        height: 56,
        lineHeight: '56px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <Space size={24} align="center">
        <Space size={10} align="center">
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: TOKENS.primary,
              color: '#fff',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: 14,
            }}
          >
            BK
          </div>
          <Text strong style={{ fontSize: 15 }}>
            BlueKing Lite
          </Text>
          <Tag style={{ marginLeft: 4, fontSize: 11 }}>APM</Tag>
        </Space>
        <Space size={4} align="center">
          {items.map((item) => {
            const active = item.key === 'service';
            return (
              <a
                key={item.key}
                href={item.href}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  height: 32,
                  padding: '0 14px',
                  borderRadius: 8,
                  fontWeight: active ? 600 : 500,
                  color: active ? TOKENS.primary : TOKENS.text,
                  background: active ? TOKENS.primarySoft : 'transparent',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </a>
            );
          })}
        </Space>
      </Space>
      <Space size={14} align="center">
        <Text type="secondary" style={{ fontSize: 13 }}>
          陈润燊
        </Text>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 14,
            background: TOKENS.primary,
            color: '#fff',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 600,
            fontSize: 12,
          }}
        >
          陈
        </div>
      </Space>
    </Header>
  );
}

/* ---------- 顶部二级导航(只做路由,不混其它控件)---------- */
function TopSecondaryNav({ active }: { active: 'service' | 'topology' | 'slo' }) {
  const mainOpts = [
    { value: 'service', label: '服务', href: STORY_URLS.service },
    { value: 'topology', label: '服务拓扑', href: STORY_URLS.topology },
    { value: 'slo', label: 'SLO', href: STORY_URLS.slo },
  ];

  return (
    <div
      style={{
        background: TOKENS.surface,
        borderBottom: `1px solid ${TOKENS.border}`,
        padding: '10px 20px 12px',
      }}
    >
      <Segmented
        value={active}
        options={mainOpts.map((o) => ({ value: o.value, label: o.label }))}
        onChange={(v) => {
          if (v === active) return;
          const target = mainOpts.find((o) => o.value === v);
          if (target?.href) window.location.href = target.href;
        }}
        style={{ background: 'transparent' }}
      />
    </div>
  );
}

function HealthDot({ level }: { level: 1 | 2 | 3 | 4 | 5 }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: HEALTH_COLORS[level],
      }}
    />
  );
}

/* ---------- 语言标签(JV/JS/.N/GO/PY)---------- */
const LANG_STYLE: Record<ServiceRow['language'], { bg: string; color: string }> = {
  JV: { bg: '#155aef', color: '#fff' },
  JS: { bg: '#f59e0b', color: '#fff' },
  '.N': { bg: '#64748b', color: '#fff' },
  GO: { bg: '#0ea5e9', color: '#fff' },
  PY: { bg: '#10b981', color: '#fff' },
};

function LanguageTag({ language }: { language: ServiceRow['language'] }) {
  const s = LANG_STYLE[language];
  return (
    <span
      style={{
        display: 'inline-block',
        minWidth: 28,
        padding: '1px 6px',
        borderRadius: 4,
        background: s.bg,
        color: s.color,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: '16px',
        textAlign: 'center',
        fontFamily: 'monospace',
      }}
    >
      {language}
    </span>
  );
}

/* ---------- 迷你趋势柱状图(8 根,按健康度着色)----------
 * 颜色:严重=红 / 警告=橙 / 关注=黄 / 良好=蓝 / 健康=蓝
 * 高度:用 hash 生成稳定起伏(同一服务名每次一致) */
function MiniTrendBars({ health, name }: { health: 1 | 2 | 3 | 4 | 5; name: string }) {
  const color =
    health <= 2 ? TOKENS.danger : health === 3 ? '#f59e0b' : TOKENS.primary;
  const hash = (s: string) => {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  };
  const seed = hash(name);
  const heights = Array.from({ length: 8 }, (_, i) => {
    const v = (Math.sin((seed + i) * 0.7) + 1) / 2; // 0..1
    return Math.round(8 + v * 14); // 8..22
  });
  return (
    <span style={{ display: 'inline-flex', alignItems: 'flex-end', gap: 2, height: 22 }}>
      {heights.map((h, i) => (
        <span
          key={i}
          style={{
            display: 'inline-block',
            width: 4,
            height: h,
            background: color,
            borderRadius: 1,
          }}
        />
      ))}
    </span>
  );
}

/* ---------- SLO 状态指示(达标 / 未达标 / 未配置)---------- */
function SloIndicator({
  slo,
}: {
  slo?: ServiceRow['slo'];
}) {
  if (!slo) return <span style={{ color: TOKENS.textTertiary }}>—</span>;
  return (
    <Space size={4} align="center">
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: '0 6px',
          height: 18,
          borderRadius: 9,
          background: '#dcfce7',
          color: '#15803d',
          fontSize: 11,
          fontWeight: 500,
        }}
      >
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: '#15803d',
          }}
        />
        达标
      </span>
      <span style={{ ...tabularNumStyle, fontSize: 11, color: TOKENS.textTertiary }}>{slo.budget}%</span>
    </Space>
  );
}

/* ---------- 时间窗 segmented(详情/列表页共享)---------- */
type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';

function TimeWindowControl({
  value = '1h',
  onChange,
}: {
  value?: TimeWindow;
  onChange?: (v: TimeWindow) => void;
}) {
  return (
    <Space size={6} align="center">
      <Text type="secondary" style={{ fontSize: 12 }}>时间窗</Text>
      <Segmented
        value={value}
        onChange={(v) => onChange?.(v as TimeWindow)}
        options={[
          { value: '15m', label: '15m' },
          { value: '1h', label: '1h' },
          { value: '4h', label: '4h' },
          { value: '1d', label: '1d' },
          { value: '7d', label: '7d' },
        ]}
      />
    </Space>
  );
}

/* ---------- 已归档按钮(详情/列表页共享)---------- */
function ArchivedButton({ count, onClick }: { count: number; onClick: () => void }) {
  return (
    <Button icon={<InboxOutlined />} onClick={onClick}>
      已归档
      {count > 0 && (
        <Badge count={count} color={TOKENS.textTertiary} style={{ marginLeft: 6 }} />
      )}
    </Button>
  );
}

/* ---------- 页面工具栏 ----------
 * mode = 'list'   → 完整版(视角切换 + 5 个筛选 + 时间窗 + 已归档),用于 app-list / service-list
 * mode = 'detail' → 精简版(左侧「← 返回服务」+ 右侧「时间窗」),用于 app-detail / service-detail
 * 详情页不放任何"列表用"控件:无视角切换、无搜索、无 select、无已归档(已归档只在列表页可用)。
 * ---------- */
function PageToolbar({
  mode = 'list',
  showPerspective = false,
  perspective = 'application',
  onPerspectiveChange,
  archivedCount,
  onArchivedClick,
  onBack,
  backLabel = '返回服务',
  timeWindow = '1h',
  onTimeWindowChange,
}: {
  mode?: 'list' | 'detail';
  showPerspective?: boolean;
  perspective?: 'application' | 'service';
  onPerspectiveChange?: (v: 'application' | 'service') => void;
  archivedCount?: number;
  onArchivedClick?: () => void;
  onBack?: () => void;
  backLabel?: string;
  timeWindow?: TimeWindow;
  onTimeWindowChange?: (v: TimeWindow) => void;
}) {
  const dividerStyle: React.CSSProperties = {
    width: 1,
    height: 16,
    background: TOKENS.border,
    margin: '0 4px',
  };

  if (mode === 'detail') {
    // 详情页工具栏:左「← 返回服务」+ 右「时间窗」;不挂已归档、视角、筛选
    return (
      <div
        style={{
          ...surfaceCardStyle,
          padding: '10px 16px',
          marginBottom: 16,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        {onBack && (
          <Button icon={<ArrowLeftOutlined />} size="small" onClick={onBack}>
            {backLabel}
          </Button>
        )}
        <div style={{ flex: 1 }} />
        <TimeWindowControl value={timeWindow} onChange={onTimeWindowChange} />
      </div>
    );
  }

  // 列表页:完整工具栏
  return (
    <div
      style={{
        ...surfaceCardStyle,
        padding: '12px 16px',
        marginBottom: 16,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        flexWrap: 'wrap',
      }}
    >
      {showPerspective && onPerspectiveChange && (
        <>
          <Space size={6} align="center">
            <Text type="secondary" style={{ fontSize: 12 }}>视角</Text>
            <Segmented
              value={perspective}
              onChange={(v) => onPerspectiveChange(v as 'application' | 'service')}
              options={[
                { value: 'application', label: <span><AppstoreOutlined style={{ marginRight: 4 }} />应用</span> },
                { value: 'service', label: <span><BarsOutlined style={{ marginRight: 4 }} />服务</span> },
              ]}
            />
          </Space>
          <span style={dividerStyle} />
        </>
      )}

      <Input
        allowClear
        placeholder="按服务名称搜索"
        prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
        style={{ width: 220 }}
      />
      <Select defaultValue="all" style={{ width: 120 }} options={[
        { value: 'all', label: '全部环境' },
        { value: 'prod', label: '生产' },
        { value: 'staging', label: '预发' },
      ]} />
      {/* 应用列表(按 namespace/应用名动态拉) */}
      <Select
        defaultValue="all"
        style={{ width: 150 }}
        options={[
          { value: 'all', label: '全部应用' },
          ...APPS.map((a) => ({ value: a.key, label: a.name })),
        ]}
      />
      {/* 5 个健康等级 */}
      <Select
        defaultValue="all"
        style={{ width: 150 }}
        options={[
          { value: 'all', label: '全部健康度' },
          ...HEALTH_LABELS.map((l, i) => ({ value: String(i + 1), label: l })),
        ]}
      />
      <Select defaultValue="all" style={{ width: 120 }} options={[
        { value: 'all', label: '全部版本' },
      ]} />

      <div style={{ flex: 1 }} />

      <TimeWindowControl value={timeWindow} onChange={onTimeWindowChange} />
      <span style={dividerStyle} />
      <ArchivedButton count={archivedCount ?? 0} onClick={onArchivedClick} />
    </div>
  );
}

function AppliedAppBanner({
  app,
  count,
  onClear,
}: {
  app: AppCard;
  count: number;
  onClear: () => void;
}) {
  return (
    <div
      style={{
        ...surfaceCardStyle,
        padding: '10px 16px',
        marginBottom: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: TOKENS.primarySoft,
        borderColor: TOKENS.primary,
      }}
    >
      <Space size={8} align="center">
        <FilterOutlined style={{ color: TOKENS.primary }} />
        <Text style={{ fontSize: 13 }}>已选应用:</Text>
        <Tag color="blue" style={{ margin: 0 }}>
          {app.isUncategorized ? '未归类应用(空 namespace)' : app.name}
        </Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>{count} 个服务</Text>
      </Space>
      <Button size="small" type="text" icon={<CloseOutlined />} onClick={onClear}>
        清除筛选
      </Button>
    </div>
  );
}

function ApplicationCard({
  app,
  selected,
  onSelect,
}: {
  app: AppCard;
  selected?: boolean;
  onSelect: (app: AppCard) => void;
}) {
  const errNum = parseFloat(app.errorRate);
  const errDanger = !isNaN(errNum) && errNum >= 1;

  // 应用下所有服务的告警聚合
  const appAlerts = app.services.reduce(
    (acc, s) => {
      const svc = SERVICE_OF[s];
      const a = svc?.activeAlerts;
      if (a && a.count > 0) {
        acc.count += a.count;
        if (!acc.level || a.level < acc.level) acc.level = a.level;
      }
      return acc;
    },
    { count: 0, level: 0 as 0 | 1 | 2 | 3 | 4 | 5 },
  );
  const alertColor =
    appAlerts.count === 0
      ? TOKENS.textTertiary
      : appAlerts.level <= 2
        ? TOKENS.danger
        : appAlerts.level === 3
          ? '#facc15'
          : TOKENS.textSecondary;
  const alertBg =
    appAlerts.count === 0
      ? TOKENS.bg
      : appAlerts.level <= 2
        ? '#fef2f0'
        : appAlerts.level === 3
          ? '#fef9c3'
          : TOKENS.bg;

  // 服务 tag 一行展示,按真实宽度测量,超出折叠 +N
  const tagsContainerRef = useRef<HTMLDivElement>(null);
  const tagsMeasureRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState(app.services.length);

  useLayoutEffect(() => {
    const recalc = () => {
      const c = tagsContainerRef.current;
      const m = tagsMeasureRef.current;
      if (!c || !m) return;
      // 同步测量层宽度 = 容器宽度(absolute 100% 不一定精确,显式设一下)
      m.style.width = `${c.clientWidth}px`;
      const tagEls = Array.from(m.children) as HTMLElement[];
      const containerW = c.clientWidth;
      let used = 0;
      let n = 0;
      // 预留 +N 标签宽度(按最大 +99 ≈ 38px + 6px gap)
      const reserveW = app.services.length > 1 ? 38 + 6 : 0;
      for (let i = 0; i < tagEls.length; i++) {
        const w = tagEls[i].getBoundingClientRect().width;
        const gap = i > 0 ? 6 : 0;
        if (used + gap + w + reserveW > containerW) break;
        used += gap + w;
        n++;
      }
      setVisibleCount(n);
    };
    recalc();
    const ro = new ResizeObserver(recalc);
    if (tagsContainerRef.current) ro.observe(tagsContainerRef.current);
    return () => ro.disconnect();
  }, [app.services.length]);

  const visibleServices = app.services.slice(0, visibleCount);
  const overflowCount = app.services.length - visibleCount;
  const tooltipTitle = app.services.map((s) => {
    const svc = SERVICE_OF[s];
    return svc?.silent ? `${s}(静默)` : s;
  }).join('、');

  return (
    <div
      onClick={() => onSelect(app)}
      style={{
        ...surfaceCardStyle,
        padding: '16px 18px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderTop: app.isUncategorized ? `3px dashed ${TOKENS.warning}` : undefined,
        borderColor: selected ? TOKENS.primary : TOKENS.border,
        borderWidth: selected ? 2 : 1,
        borderStyle: 'solid',
        position: 'relative',
        cursor: 'pointer',
        transition: 'box-shadow 120ms, border 120ms',
      }}
    >
      {selected && (
        <span
          style={{
            position: 'absolute',
            top: 10,
            right: 10,
            padding: '1px 6px',
            borderRadius: 4,
            background: TOKENS.primarySoft,
            color: TOKENS.primary,
            fontSize: 11,
            fontWeight: 500,
          }}
        >
          已筛选
        </span>
      )}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}
      >
        <div>
          <Space size={8} align="center">
            <HealthDot level={app.health} />
            <span style={{ fontSize: 15, fontWeight: 600, color: TOKENS.text }}>{app.name}</span>
            {app.isUncategorized && (
              <Tooltip title="这些服务未设置 service.namespace，平台归入内置未归类应用。请补全 namespace 以便正确分组。">
                <Tag color="warning" style={{ margin: 0, fontSize: 11 }}>未归类</Tag>
              </Tooltip>
            )}
          </Space>
          <div
            style={{
              fontSize: 12,
              color: TOKENS.textTertiary,
              marginTop: 4,
              marginLeft: 16,
            }}
          >
            {app.services.length} 个服务
          </div>
        </div>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            padding: '2px 8px',
            borderRadius: 4,
            background: alertBg,
            color: alertColor,
            fontSize: 12,
            fontWeight: appAlerts.count > 0 && appAlerts.level <= 2 ? 600 : 400,
            border: `1px solid ${appAlerts.count > 0 && appAlerts.level <= 2 ? TOKENS.danger : TOKENS.border}`,
            flexShrink: 0,
          }}
          title={`应用内 ${appAlerts.count} 个活跃告警`}
        >
          <BellOutlined style={{ fontSize: 11 }} />
          {appAlerts.count}
        </span>
      </div>

      <Row gutter={16} style={{ marginBottom: 14 }}>
        <Col span={12}>
          <Text type="secondary" style={{ fontSize: 11 }}>吞吐量</Text>
          <div style={{ marginTop: 2 }}>
            <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700, color: TOKENS.text }}>
              {app.throughput}
            </span>
            <span style={{ color: TOKENS.textSecondary, fontSize: 12, marginLeft: 2 }}>/s</span>
          </div>
        </Col>
        <Col span={12}>
          <Text type="secondary" style={{ fontSize: 11 }}>错误率</Text>
          <div style={{ marginTop: 2 }}>
            <span
              style={{
                ...tabularNumStyle,
                fontSize: 22,
                fontWeight: 700,
                color: errDanger ? TOKENS.danger : TOKENS.text,
              }}
            >
              {app.errorRate}
            </span>
          </div>
        </Col>
      </Row>

      <Tooltip title={tooltipTitle} placement="top">
        <div
          ref={tagsContainerRef}
          style={{
            position: 'relative',
            borderTop: `1px dashed ${TOKENS.border}`,
            paddingTop: 12,
            marginTop: 'auto',
          }}
        >
          <div
            style={{
              display: 'flex',
              flexWrap: 'nowrap',
              gap: 6,
              overflow: 'hidden',
            }}
          >
            {visibleServices.map((svcName) => {
              const svc = SERVICE_OF[svcName];
              return (
                <span
                  key={svcName}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '2px 8px',
                    borderRadius: 4,
                    background: svc?.silent ? TOKENS.bg : TOKENS.surface,
                    border: `1px solid ${TOKENS.border}`,
                    fontSize: 12,
                    color: svc?.silent ? TOKENS.textTertiary : TOKENS.text,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  {svc && <LanguageTag language={svc.language} />}
                  <span>{svcName}</span>
                </span>
              );
            })}
            {overflowCount > 0 && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '2px 8px',
                  borderRadius: 4,
                  background: TOKENS.primarySoft,
                  color: TOKENS.primary,
                  fontSize: 12,
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                }}
              >
                +{overflowCount}
              </span>
            )}
          </div>
          {/* 测量层:绝对定位 + 不可见,用于 ResizeObserver 实时计算可见数量 */}
          <div
            ref={tagsMeasureRef}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              visibility: 'hidden',
              pointerEvents: 'none',
              display: 'flex',
              gap: 6,
              height: 0,
              overflow: 'visible',
            }}
          >
            {app.services.map((svcName) => {
              const svc = SERVICE_OF[svcName];
              return (
                <span
                  key={svcName}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '2px 8px',
                    borderRadius: 4,
                    background: svc?.silent ? TOKENS.bg : TOKENS.surface,
                    border: `1px solid ${TOKENS.border}`,
                    fontSize: 12,
                    color: svc?.silent ? TOKENS.textTertiary : TOKENS.text,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  {svc && <LanguageTag language={svc.language} />}
                  <span>{svcName}</span>
                </span>
              );
            })}
          </div>
        </div>
      </Tooltip>
    </div>
  );
}

/* ---------- 服务列表 Table(版本概览布局)---------- */
function ServiceListTable({
  rows,
  selectedApp,
  onServiceClick,
}: {
  rows: ServiceRow[];
  selectedApp?: AppCard | null;
  onServiceClick?: (s: ServiceRow) => void;
}) {
  return (
    <div style={{ ...surfaceCardStyle, padding: '0 0 4px' }}>
      <Table
        size="middle"
        rowKey="key"
        pagination={false}
        dataSource={rows}
        columns={[
          {
            title: (
              <Space size={6} align="center">
                <span>服务</span>
                {selectedApp && (
                  <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>
                    {selectedApp.isUncategorized ? '未归类应用' : selectedApp.name}
                  </Tag>
                )}
              </Space>
            ),
            dataIndex: 'name',
            render: (v, r) => (
              <Space size={8} align="center">
                <HealthDot level={r.health} />
                <LanguageTag language={r.language} />
                <a
                  style={{
                    color: TOKENS.primary,
                    fontWeight: r.health <= 2 ? 600 : 500,
                    cursor: 'pointer',
                    opacity: r.silent ? 0.6 : 1,
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onServiceClick?.(r);
                  }}
                >
                  {v}
                </a>
                {r.silent && (
                  <Tag style={{ margin: 0, fontSize: 11, color: TOKENS.textTertiary, borderColor: TOKENS.border }}>
                    静默
                  </Tag>
                )}
              </Space>
            ),
          },
          {
            title: '活跃告警',
            width: 110,
            render: (_, r) => {
              const a = r.activeAlerts;
              if (!a || a.count === 0) {
                return (
                  <Tag
                    style={{
                      margin: 0,
                      fontSize: 11,
                      lineHeight: '18px',
                      padding: '0 8px',
                      borderRadius: 10,
                      background: TOKENS.bg,
                      color: TOKENS.textTertiary,
                      border: `1px solid ${TOKENS.border}`,
                      opacity: r.silent ? 0.6 : 1,
                    }}
                  >
                    <BellOutlined style={{ fontSize: 10, marginRight: 4 }} />
                    0
                  </Tag>
                );
              }
              const color = a.level <= 2 ? TOKENS.danger : a.level === 3 ? '#a16207' : TOKENS.textSecondary;
              const bg = a.level <= 2 ? '#fef2f0' : a.level === 3 ? '#fef9c3' : TOKENS.bg;
              const border = a.level <= 2 ? TOKENS.danger : TOKENS.border;
              return (
                <Tag
                  style={{
                    margin: 0,
                    fontSize: 11,
                    lineHeight: '18px',
                    padding: '0 8px',
                    borderRadius: 10,
                    background: bg,
                    color,
                    border: `1px solid ${border}`,
                    fontWeight: 600,
                    opacity: r.silent ? 0.6 : 1,
                  }}
                  title={`${a.count} 个活跃告警(最高等级 ${a.level})`}
                >
                  <BellOutlined style={{ fontSize: 10, marginRight: 4 }} />
                  {a.count}
                </Tag>
              );
            },
          },
          {
            title: '吞吐量(/s)',
            dataIndex: 'throughput',
            width: 110,
            align: 'right' as const,
            render: (v, r) => (
              <span
                style={{
                  ...tabularNumStyle,
                  color: r.silent ? TOKENS.textTertiary : TOKENS.text,
                  opacity: r.silent ? 0.6 : 1,
                }}
              >
                {v}
              </span>
            ),
          },
          {
            title: '错误率',
            dataIndex: 'errorRate',
            width: 90,
            align: 'right' as const,
            render: (v) => {
              const num = parseFloat(v);
              const danger = !isNaN(num) && num >= 1;
              return (
                <span style={{ ...tabularNumStyle, color: danger ? TOKENS.danger : TOKENS.text, fontWeight: danger ? 600 : 400 }}>
                  {v}
                </span>
              );
            },
          },
          {
            title: 'P99',
            dataIndex: 'p99',
            width: 90,
            align: 'right' as const,
            render: (v) => <span style={tabularNumStyle}>{v}</span>,
          },
          {
            title: 'APDEX',
            dataIndex: 'apdex',
            width: 90,
            align: 'right' as const,
            render: (v, r) => {
              const n = Number(v) || 0;
              const color =
                n >= 0.9 ? TOKENS.success : n >= 0.75 ? TOKENS.warning : TOKENS.danger;
              return (
                <span
                  style={{
                    ...tabularNumStyle,
                    color: r.silent ? TOKENS.textTertiary : color,
                    fontWeight: n < 0.75 ? 600 : 400,
                    opacity: r.silent ? 0.6 : 1,
                  }}
                  title={`Apdex = ${n.toFixed(2)} (T=500ms)`}
                >
                  {n.toFixed(2)}
                </span>
              );
            },
          },
          {
            title: '趋势',
            width: 90,
            render: (_, r) => <MiniTrendBars health={r.health} name={r.key} />,
          },
          {
            title: '最近部署',
            dataIndex: 'lastDeploy',
            width: 100,
            render: (v) => (
              <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>
                {v ?? '—'}
              </span>
            ),
          },
          {
            title: 'SLO',
            width: 120,
            render: (_, r) => <SloIndicator slo={r.slo} />,
          },
          {
            title: '版本',
            width: 110,
            render: (_, r) => (
              <Tag style={{ margin: 0, fontFamily: 'monospace', fontSize: 11 }}>
                {r.version}
              </Tag>
            ),
          },
          {
            title: '最近活跃',
            dataIndex: 'lastActive',
            width: 100,
            render: (v) => (
              <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>
                {v ?? '—'}
              </span>
            ),
          },
        ]}
      />
    </div>
  );
}

/* ---------- 已归档 Drawer(全局挂载)---------- */
function ArchivedDrawer({
  open,
  onClose,
  rows,
}: {
  open: boolean;
  onClose: () => void;
  rows: typeof ARCHIVED_ROWS;
}) {
  return (
    <Drawer
      title={
        <div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>已归档服务</div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {rows.length} 个归档服务 · 数据保留期最长 90 天
          </Text>
        </div>
      }
      placement="right"
      width={560}
      open={open}
      onClose={onClose}
      closable={true}
      mask={true}
      styles={{ body: { padding: '12px 20px' } }}
      extra={
        <Input
          placeholder="搜索归档服务"
          prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
          style={{ width: 180 }}
          size="small"
          allowClear
        />
      }
    >
      <Alert
        showIcon
        type="info"
        style={{ marginBottom: 12, borderRadius: 6 }}
        message="归档不等于删除。归档后告警自动暂停,数据保留期内可恢复。"
      />
      <List
        size="small"
        dataSource={rows}
        renderItem={(item) => (
          <List.Item style={{ padding: '12px 0' }}>
            <Space direction="vertical" size={6} style={{ flex: 1 }}>
              <Space size={8}>
                <Text style={{ fontSize: 13, fontWeight: 500, color: TOKENS.text }}>{item.name}</Text>
                <Tag color={item.reasonType === 'auto' ? 'warning' : 'default'} style={{ margin: 0, fontSize: 11 }}>
                  {item.reasonType === 'auto' ? '自动归档' : '手动归档'}
                </Tag>
              </Space>
              <Space size={8} wrap>
                <Text type="secondary" style={{ fontSize: 12 }}>应用 = {item.app}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>·</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>{item.env}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>·</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>{item.reason}</Text>
              </Space>
              <Space size={12} style={{ fontSize: 12, color: TOKENS.textTertiary }}>
                <span>最后活跃 {item.lastActive}</span>
                <span>·</span>
                <span style={tabularNumStyle}>保留期还剩 {item.keptDays} 天</span>
                {item.pausedAlerts > 0 && (
                  <>
                    <span>·</span>
                    <span style={tabularNumStyle}>{item.pausedAlerts} 条告警暂停</span>
                  </>
                )}
              </Space>
            </Space>
            <Space size={4} direction="vertical" align="end">
              <a style={{ color: TOKENS.primary, fontSize: 12, cursor: 'pointer' }}>查看历史</a>
            </Space>
          </List.Item>
        )}
      />
    </Drawer>
  );
}

/* ============================================================
 * 应用详情:拓扑(主区) + 关键信息(右侧侧栏) + 该应用服务列表
 * ============================================================ */
function KeyInfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>{label}</Text>
      <div>{children}</div>
    </div>
  );
}

function AppDetailView({
  app,
  services,
  onServiceClick,
}: {
  app: AppCard;
  services: ServiceRow[];
  onServiceClick: (s: ServiceRow) => void;
}) {
  // 应用级 KPI 聚合(Σ throughput / max P99 / Σ error% 估算)
  const parseNum = (s: string) => {
    const m = s.match(/([\d.]+)([km]?)/i);
    if (!m) return 0;
    const n = parseFloat(m[1]);
    const unit = m[2].toLowerCase();
    return unit === 'k' ? n * 1000 : unit === 'm' ? n * 1_000_000 : n;
  };
  const totalRps = services.reduce((acc, s) => acc + parseNum(s.throughput), 0);
  const displayRps = totalRps >= 1000 ? `${(totalRps / 1000).toFixed(1)}k` : `${Math.round(totalRps)}`;
  const maxP99 = services.length === 0
    ? 0
    : Math.max(...services.map((s) => parseNum(s.p99)));
  const worstHealth: 1 | 2 | 3 | 4 | 5 = services.length === 0
    ? 5
    : (Math.min(...services.map((s) => s.health)) as 1 | 2 | 3 | 4 | 5);
  const errorServices = services.filter((s) => s.health <= 2).map((s) => s.name);
  /** 应用下健康度最低的服务(无并列时唯一;并列取 throughput 最大) */
  const worstService: ServiceRow | null = services.length === 0
    ? null
    : services.reduce((acc, s) => {
      if (!acc) return s;
      if (s.health < acc.health) return s;
      if (s.health === acc.health && parseNum(s.throughput) > parseNum(acc.throughput)) return s;
      return acc;
    }, null as ServiceRow | null);
  const sumErrorCount = services.reduce((acc, s) => {
    const pct = parseFloat(s.errorRate) || 0;
    const rps = parseNum(s.throughput);
    return acc + (pct / 100) * rps;
  }, 0);
  const errorRate = totalRps > 0 ? (sumErrorCount / totalRps) * 100 : 0;
  const errDanger = errorRate >= 1;

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}
      >
        <Space size={10} align="center">
          <HealthDot level={worstHealth} />
          <Title level={4} style={{ margin: 0 }}>
            {app.name}
          </Title>
          <Tag color={worstHealth <= 2 ? 'error' : worstHealth === 3 ? 'warning' : 'success'}>
            最差 {worstService?.name ?? '—'}
          </Tag>
          {errorServices.length > 0 && (
            <Tag color="error">异常: {errorServices.join('、')}</Tag>
          )}
        </Space>
      </div>

      {/* 拓扑 + 关键信息 同行布局(左 16 列拓扑,右 8 列关键信息) */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={16}>
          <div style={{ ...surfaceCardStyle, padding: '14px 16px', height: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Text strong>服务拓扑(应用聚合 · {app.name})</Text>
              <Space size={8}>
                <Tag>本应用 {services.length} 节点</Tag>
                <Tag color="warning">{errorServices.length} 异常</Tag>
              </Space>
            </div>
            <AppTopologyGraphView app={app} />
          </div>
        </Col>
        <Col span={8}>
          <div style={{ ...surfaceCardStyle, padding: '20px 22px', height: '100%' }}>
            <Text strong style={{ fontSize: 14 }}>关键信息</Text>
            <div style={{ marginTop: 16 }}>
              {/* 健康度(全宽一行) */}
              <KeyInfoRow label="健康度">
                <Space size={8} align="center">
                  <HealthDot level={worstHealth} />
                  <Tag
                    color={worstHealth <= 2 ? 'error' : worstHealth === 3 ? 'warning' : 'success'}
                    style={{ margin: 0 }}
                  >
                    {HEALTH_LABELS[worstHealth - 1]}
                  </Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    最差 {worstService?.name ?? '—'}
                  </Text>
                </Space>
              </KeyInfoRow>
              {/* 以下 4 行两列 */}
              <Row gutter={[16, 14]}>
                <Col span={12}>
                  <KeyInfoRow label="吞吐量(Σ)">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700, color: TOKENS.text }}>{displayRps}</span>
                    <span style={{ color: TOKENS.textSecondary, fontSize: 12, marginLeft: 4 }}>/s</span>
                  </KeyInfoRow>
                </Col>
                <Col span={12}>
                  <KeyInfoRow label="错误率(Σ)">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700, color: errDanger ? TOKENS.danger : TOKENS.text }}>
                      {errorRate.toFixed(1)}
                    </span>
                    <span style={{ color: errDanger ? TOKENS.danger : TOKENS.textSecondary, fontSize: 12, marginLeft: 2 }}>%</span>
                  </KeyInfoRow>
                </Col>
                <Col span={12}>
                  <KeyInfoRow label="P99(max)">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700, color: TOKENS.text }}>{Math.round(maxP99)}</span>
                    <span style={{ color: TOKENS.textSecondary, fontSize: 12, marginLeft: 4 }}>ms</span>
                  </KeyInfoRow>
                </Col>
                <Col span={12}>
                  <KeyInfoRow label="服务数">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700 }}>{services.length}</span>
                  </KeyInfoRow>
                </Col>
                <Col span={12}>
                  <KeyInfoRow label="告警">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700 }}>
                      {services.reduce((acc, s) => acc + (s.activeAlerts?.count ?? 0), 0)}
                    </span>
                  </KeyInfoRow>
                </Col>
                <Col span={12}>
                  <KeyInfoRow label="SLO">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700 }}>
                      {services.filter((s) => s.slo).length}
                    </span>
                  </KeyInfoRow>
                </Col>
                <Col span={12}>
                  <KeyInfoRow label="最近部署">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700, color: TOKENS.text }}>6 天前</span>
                  </KeyInfoRow>
                </Col>
                <Col span={12}>
                  <KeyInfoRow label="版本">
                    <span style={{ ...tabularNumStyle, fontSize: 22, fontWeight: 700 }}>{services.length}</span>
                  </KeyInfoRow>
                </Col>
              </Row>
            </div>
          </div>
        </Col>
      </Row>

      {/* 该应用下的服务列表 */}
      <div style={{ ...surfaceCardStyle, padding: '0 0 4px' }}>
        <div style={{ padding: '14px 16px 4px' }}>
          <Text strong>该应用下的服务({services.length})</Text>
        </div>
        <ServiceListTable rows={services} selectedApp={app} onServiceClick={onServiceClick} />
      </div>
    </div>
  );
}

/* ============================================================
 * 通用拓扑图(圆节点 + 类型 icon + 贝塞尔边 + 健康颜色)
 * AppDetail 与 ServiceTopologyMock 共用一份实现
 * ============================================================ */
type TNodeType = 'service' | 'database' | 'cache' | 'mq' | 'external';
type THealth = 'good' | 'warning' | 'critical' | 'unknown';

interface TNode {
  id: string;
  name: string;
  sub?: string;
  type: TNodeType;
  health: THealth;
  appKey?: string;
  x: number;
  y: number;
}

interface TEdge {
  from: string;
  to: string;
  health?: THealth;
}

const T_HEALTH_COLOR: Record<THealth, string> = {
  good: '#10b981',
  warning: '#f59e0b',
  critical: '#dc2626',
  unknown: '#94a3b8',
};
const T_EDGE_COLOR: Record<THealth, string> = {
  good: '#cbd5e1',
  warning: '#f59e0b',
  critical: '#dc2626',
  unknown: '#cbd5e1',
};

function TypeIcon({ type }: { type: TNodeType }) {
  switch (type) {
    case 'database':
      return (
        <g>
          <ellipse cx={0} cy={-3} rx={7} ry={2.5} fill="#e2e8f0" />
          <path d="M -7 -3 V 3 a 7 2.5 0 0 0 14 0 V -3" fill="#e2e8f0" stroke="#64748b" strokeWidth="0.8" />
          <ellipse cx={0} cy={-3} rx={7} ry={2.5} fill="none" stroke="#64748b" strokeWidth="0.8" />
          <ellipse cx={0} cy={3} rx={7} ry={2.5} fill="none" stroke="#64748b" strokeWidth="0.6" opacity="0.4" />
        </g>
      );
    case 'cache':
      return (
        <g>
          <rect x={-6} y={-5} width={12} height={3} rx={1} fill="#e2e8f0" stroke="#64748b" strokeWidth="0.6" />
          <rect x={-6} y={-1} width={12} height={3} rx={1} fill="#e2e8f0" stroke="#64748b" strokeWidth="0.6" />
          <rect x={-6} y={3} width={12} height={3} rx={1} fill="#e2e8f0" stroke="#64748b" strokeWidth="0.6" />
        </g>
      );
    case 'mq':
      return (
        <g>
          <rect x={-8} y={-2} width={16} height={4} rx={1} fill="#e2e8f0" stroke="#64748b" strokeWidth="0.6" />
          <circle cx={-11} cy={0} r={1.6} fill="#64748b" />
          <circle cx={11} cy={0} r={1.6} fill="#64748b" />
        </g>
      );
    case 'external':
      return (
        <path
          d="M -8 3 q -4 -3 -1 -5 q 2 -3 5 -1 q 3 -2 5 1 q 4 2 1 5 z"
          fill="#e2e8f0"
          stroke="#64748b"
          strokeWidth="0.6"
        />
      );
    case 'service':
    default:
      return <circle r={5} fill="#e2e8f0" stroke="#64748b" strokeWidth="0.6" />;
  }
}

function TopologyNode({ node }: { node: TNode }) {
  const color = T_HEALTH_COLOR[node.health];
  const r = 22;
  const isCritical = node.health === 'critical';
  return (
    <g transform={`translate(${node.x},${node.y})`}>
      <circle r={r} fill="white" stroke={color} strokeWidth={isCritical ? 3 : 2} />
      <TypeIcon type={node.type} />
      <text
        x={0}
        y={r + 14}
        textAnchor="middle"
        fontSize="11"
        fontWeight={isCritical ? 600 : 500}
        fill={isCritical ? '#dc2626' : '#1f2937'}
      >
        {node.name}
      </text>
      {node.sub && (
        <text x={0} y={r + 28} textAnchor="middle" fontSize="10" fill="#64748b">
          {node.sub}
        </text>
      )}
    </g>
  );
}

function TopologyEdge({
  from,
  to,
  health = 'good',
}: {
  from: TNode;
  to: TNode;
  health?: THealth;
}) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const ratio = 22 / len;
  const endX = to.x - dx * ratio;
  const endY = to.y - dy * ratio;
  const cp1x = from.x + (to.x - from.x) * 0.45;
  const cp1y = from.y;
  const cp2x = cp1x;
  const cp2y = to.y;
  const color = T_EDGE_COLOR[health];
  const width = health === 'critical' ? 2.4 : health === 'warning' ? 1.8 : 1.4;
  const dash = health === 'critical' ? '6 4' : undefined;
  const arrowSuffix =
    health === 'critical' ? 'red' : health === 'warning' ? 'orange' : 'gray';
  return (
    <path
      d={`M ${from.x} ${from.y} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${endX} ${endY}`}
      fill="none"
      stroke={color}
      strokeWidth={width}
      strokeDasharray={dash}
      markerEnd={`url(#arrow-${arrowSuffix})`}
    />
  );
}

function TopologyGraph({
  nodes,
  edges,
  highlightAppKey,
}: {
  nodes: TNode[];
  edges: TEdge[];
  highlightAppKey?: string;
}) {
  const padding = 36;
  const maxX = Math.max(...nodes.map((n) => n.x), 100);
  const maxY = Math.max(...nodes.map((n) => n.y), 100);
  const w = maxX + padding + 20;
  const h = maxY + padding + 50;

  const highlightNodes = highlightAppKey
    ? nodes.filter((n) => n.appKey === highlightAppKey)
    : [];
  const minX = highlightNodes.length > 0
    ? Math.min(...highlightNodes.map((n) => n.x)) - 30
    : 0;
  const maxXB = highlightNodes.length > 0
    ? Math.max(...highlightNodes.map((n) => n.x)) + 30
    : 0;
  const minY = highlightNodes.length > 0
    ? Math.min(...highlightNodes.map((n) => n.y)) - 24
    : 0;
  const maxYB = highlightNodes.length > 0
    ? Math.max(...highlightNodes.map((n) => n.y)) + 50
    : 0;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: Math.max(h, 360) }}>
      <defs>
        <marker id="arrow-gray" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#cbd5e1" />
        </marker>
        <marker id="arrow-orange" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b" />
        </marker>
        <marker id="arrow-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#dc2626" />
        </marker>
      </defs>

      {highlightNodes.length > 0 && (
        <rect
          x={minX}
          y={minY}
          width={maxXB - minX}
          height={maxYB - minY}
          rx={14}
          fill="#eef2ff"
          fillOpacity={0.5}
          stroke="#155aef"
          strokeWidth={1}
          strokeDasharray="4 4"
        />
      )}

      {edges.map((e, i) => {
        const from = nodes.find((n) => n.id === e.from);
        const to = nodes.find((n) => n.id === e.to);
        if (!from || !to) return null;
        return <TopologyEdge key={`e-${i}`} from={from} to={to} health={e.health ?? 'good'} />;
      })}

      {nodes.map((n) => <TopologyNode key={n.id} node={n} />)}
    </svg>
  );
}

/* 应用详情用的样例节点/边(billing 应用)
 * 边界:仅展示「本应用的服务」+「直接上下游」(1 跳);
 * 不展示 2 跳之外的非相关节点(如 email-gateway / notification-worker / web-storefront)。
 */
function AppTopologyNodes(appKey: string): { nodes: TNode[]; edges: TEdge[] } {
  const nodes: TNode[] = [
    // ── 直接上游(1 个,真正调用本应用任一服务的入口)──
    { id: 'api-gateway', name: 'api-gateway', type: 'service', health: 'good', x: 220, y: 240, appKey: 'external' },
    // ── 本应用(交易清结算全部 3 个服务)──
    { id: 'inventory-svc', name: 'inventory-svc', sub: appKey, type: 'service', health: 'good', x: 480, y: 110, appKey },
    { id: 'payment-svc', name: 'payment-svc', sub: appKey, type: 'service', health: 'critical', x: 480, y: 240, appKey },
    { id: 'checkout-api', name: 'checkout-api', sub: appKey, type: 'service', health: 'warning', x: 480, y: 370, appKey },
    // ── 直接下游(4 个:缓存/DB/MQ/外部支付)──
    { id: 'redis', name: 'redis', sub: 'redis-1', type: 'cache', health: 'good', x: 740, y: 80, appKey: 'external' },
    { id: 'postgres', name: 'postgres', sub: 'pg-main', type: 'database', health: 'good', x: 740, y: 200, appKey: 'external' },
    { id: 'kafka', name: 'kafka', sub: 'kafka-1', type: 'mq', health: 'unknown', x: 740, y: 320, appKey: 'external' },
    { id: 'stripe', name: 'stripe-gateway', type: 'external', health: 'unknown', x: 740, y: 430, appKey: 'external' },
  ];
  const edges: TEdge[] = [
    // 上游 → 本应用
    { from: 'api-gateway', to: 'inventory-svc' },
    { from: 'api-gateway', to: 'payment-svc' },
    { from: 'api-gateway', to: 'checkout-api', health: 'warning' },
    // 应用内降级链
    { from: 'payment-svc', to: 'inventory-svc', health: 'critical' },
    { from: 'payment-svc', to: 'checkout-api', health: 'warning' },
    // 本应用 → 下游
    { from: 'checkout-api', to: 'redis' },
    { from: 'inventory-svc', to: 'postgres' },
    { from: 'payment-svc', to: 'postgres' },
    { from: 'payment-svc', to: 'kafka' },
    { from: 'payment-svc', to: 'stripe', health: 'warning' },
  ];
  return { nodes, edges };
}

/* 应用详情包装:取应用名 → 节点/边 → TopologyGraph */
function AppTopologyGraphView({ app }: { app: AppCard }) {
  const { nodes, edges } = AppTopologyNodes(app.key);
  return <TopologyGraph nodes={nodes} edges={edges} highlightAppKey={app.key} />;
}

/* ============================================================
 * 单服务详情(Tabs:概览 / 调用链 / 错误 / 运行时 / 部署 / SLO)
 * 顶部不再展示「智能告警 Alert」;只在事实层面陈列数据
 * 「← 返回服务」按钮挪到 PageToolbar(detail mode)
 * ============================================================ */
function ServiceDetailView({
  service,
  timeWindow = '1h',
  onAppClick,
}: {
  service: ServiceRow;
  timeWindow?: TimeWindow;
  onAppClick?: (app: AppCard) => void;
}) {
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [apdexDrawerOpen, setApdexDrawerOpen] = useState(false);

  const app: AppCard | null = service.namespace
    ? APPS.find((a) => a.key === service.namespace) ?? null
    : null;
  const appName = app?.name ?? (service.namespace ? service.namespace : '未归类应用');
  const canDrillApp = !!app && !app.isUncategorized && !!onAppClick;

  const moreMenuItems = [
    { key: 'archive', label: <span onClick={() => setArchiveOpen(true)}>归档</span> },
  ];

  return (
    <div>
      {/* 顶部行:服务名 + 健康 + 关联 / 创建 / ···;时间窗已挪到 PageToolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}
      >
        <Space size={10} align="center">
          <HealthDot level={service.health} />
          <Title level={4} style={{ margin: 0 }}>
            {service.name}
          </Title>
          <Tag color={service.health <= 2 ? 'error' : service.health === 3 ? 'warning' : 'success'}>
            {HEALTH_LABELS[service.health - 1]}
          </Tag>
          <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
            所属应用{' '}
            {canDrillApp ? (
              <a
                style={{ color: TOKENS.primary, cursor: 'pointer' }}
                onClick={() => onAppClick?.(app!)}
              >
                {appName}
              </a>
            ) : (
              <span>{appName}</span>
            )}
          </Text>
        </Space>
        <Space size={8}>
          <Dropdown menu={{ items: moreMenuItems }} placement="bottomRight">
            <Button icon={<EllipsisOutlined />} />
          </Dropdown>
        </Space>
      </div>

      {/* 删除顶部智能告警 Alert — 仅展示事实,不做自动推断 */}

      {/* KPI 行(共享,Tabs 外) */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {/* 吞吐 */}
        <Col span={6}>
          <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>吞吐</Text>
            <div style={{ marginTop: 4 }}>
              <span style={{ ...tabularNumStyle, fontSize: 24, fontWeight: 700, color: TOKENS.text }}>{service.throughput}</span>
              <span style={{ color: TOKENS.textSecondary, fontSize: 13, marginLeft: 2 }}>/s</span>
            </div>
          </div>
        </Col>
        {/* 错误率 */}
        <Col span={6}>
          <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>错误率</Text>
            <div style={{ marginTop: 4 }}>
              <span
                style={{
                  ...tabularNumStyle,
                  fontSize: 24,
                  fontWeight: 700,
                  color: service.health <= 2 ? TOKENS.danger : TOKENS.text,
                }}
              >
                {service.errorRate}
              </span>
            </div>
          </div>
        </Col>
        {/* P99 */}
        <Col span={6}>
          <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>P99</Text>
            <div style={{ marginTop: 4 }}>
              <span
                style={{
                  ...tabularNumStyle,
                  fontSize: 24,
                  fontWeight: 700,
                  color: service.health <= 2 ? TOKENS.danger : TOKENS.text,
                }}
              >
                {service.p99}
              </span>
            </div>
          </div>
        </Col>
        {/* Apdex(带修改阈值入口) */}
        <Col span={6}>
          <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>Apdex</Text>
              <Button
                size="small"
                type="text"
                icon={<SettingOutlined />}
                onClick={() => setApdexDrawerOpen(true)}
                style={{ padding: '0 4px', height: 22 }}
                title="修改 Apdex 阈值"
              >
                阈值
              </Button>
            </div>
            <div style={{ marginTop: 4 }}>
              <span
                style={{
                  ...tabularNumStyle,
                  fontSize: 24,
                  fontWeight: 700,
                  color: service.apdex >= 0.9 ? TOKENS.success : service.apdex >= 0.75 ? TOKENS.warning : TOKENS.danger,
                }}
              >
                {service.apdex.toFixed(2)}
              </span>
              <span style={{ color: TOKENS.textSecondary, fontSize: 12, marginLeft: 8 }}>阈值 T = 500ms</span>
            </div>
          </div>
        </Col>
      </Row>

      {/* Tab 切换:概览 / 调用链 / 错误 / 运行时 / 部署 / SLO */}
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        {/* —— 概览 —— */}
        <Tabs.TabPane tab="概览" key="overview">
          {/* RED 三视图:吞吐 / 错误率 / 时延,各自独立 card,共享 hover 同步 */}
          <ServiceRedCharts timeWindow={timeWindow} />

          <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
                <Text strong>Top 端点(按总耗时)</Text>
                <List
                  size="small"
                  style={{ marginTop: 8 }}
                  dataSource={[
                    { path: 'POST /api/v1/payments', calls: '8.4k', p95: '624ms', ratio: 42 },
                    { path: 'POST /api/v1/refunds', calls: '2.1k', p95: '412ms', ratio: 22 },
                    { path: 'GET /api/v1/payments/{id}', calls: '5.6k', p95: '88ms', ratio: 12 },
                    { path: 'GET /api/v1/health', calls: '12.4k', p95: '8ms', ratio: 4 },
                  ]}
                  renderItem={(item) => (
                    <List.Item style={{ padding: '8px 0' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ fontSize: 13, color: TOKENS.text }}>{item.path}</span>
                          <span style={{ ...tabularNumStyle, fontSize: 12, color: TOKENS.textSecondary }}>
                            {item.calls} · P95 {item.p95}
                          </span>
                        </div>
                        <div style={{ height: 3, background: TOKENS.border, borderRadius: 2, marginTop: 6, overflow: 'hidden' }}>
                          <div style={{ width: `${item.ratio}%`, height: '100%', background: TOKENS.primary }} />
                        </div>
                      </div>
                    </List.Item>
                  )}
                />
              </div>
            </Col>
            <Col span={12}>
              <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
                <Text strong>依赖关系</Text>
                <Row gutter={[12, 12]} style={{ marginTop: 8 }}>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>上游 · 调用方 1</Text>
                    <div style={{ marginTop: 6 }}>
                      <Tag style={{ marginBottom: 4 }}>checkout-api · 244/s · P95 230ms · 错误率 20%</Tag>
                    </div>
                  </Col>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 12 }}>下游 · 被调方 0</Text>
                    <div style={{ marginTop: 6, color: TOKENS.textTertiary, fontSize: 12 }}>近窗内无向下调用(单服务节点)</div>
                  </Col>
                </Row>
              </div>
            </Col>
          </Row>
        </Tabs.TabPane>

        {/* —— 调用链 —— */}
        <Tabs.TabPane tab="调用链" key="trace">
          <Table
            size="middle"
            rowKey="traceId"
            pagination={false}
            dataSource={[
              { traceId: 'c7573a6b982052e1...', entry: 'api-gateway', endpoint: 'GET /api/user/profile', duration: '234ms', spans: 18, status: 'error', time: '刚刚' },
              { traceId: '4cedd8538a05e6bc...', entry: 'web-storefront', endpoint: 'GET /product/:id', duration: '443ms', spans: 22, status: 'ok', time: '2 分钟前' },
              { traceId: 'de7c2c645cc4114d...', entry: 'web-storefront', endpoint: 'POST /cart/checkout', duration: '504ms', spans: 24, status: 'ok', time: '5 分钟前' },
              { traceId: '5414bd298ecb60f...', entry: 'web-storefront', endpoint: 'GET /product/:id', duration: '327ms', spans: 16, status: 'ok', time: '12 分钟前' },
              { traceId: '359649fda0dbb967...', entry: 'api-gateway', endpoint: 'POST /api/checkout', duration: '246ms', spans: 15, status: 'ok', time: '18 分钟前' },
              { traceId: '0542c8a0e5f45a1e...', entry: 'web-storefront', endpoint: 'GET /', duration: '287ms', spans: 21, status: 'ok', time: '23 分钟前' },
              { traceId: '52e743c78acd0bb0...', entry: 'api-gateway', endpoint: 'GET /api/user/profile', duration: '395ms', spans: 22, status: 'ok', time: '31 分钟前' },
              { traceId: '3a28314db85df060...', entry: 'web-storefront', endpoint: 'GET /product/:id', duration: '366ms', spans: 21, status: 'ok', time: '38 分钟前' },
              { traceId: '7ec37c2cfa41ba3...', entry: 'web-storefront', endpoint: 'GET /', duration: '397ms', spans: 24, status: 'ok', time: '44 分钟前' },
              { traceId: '8d4aa54a9d910b59...', entry: 'web-storefront', endpoint: 'POST /cart/checkout', duration: '397ms', spans: 16, status: 'ok', time: '52 分钟前' },
              { traceId: '136879e325b8feb4...', entry: 'api-gateway', endpoint: 'POST /api/checkout', duration: '419ms', spans: 20, status: 'ok', time: '57 分钟前' },
              { traceId: '64258a6d8cf0c8f8...', entry: 'api-gateway', endpoint: 'GET /api/user/profile', duration: '337ms', spans: 22, status: 'ok', time: '59 分钟前' },
            ]}
            columns={[
              {
                title: '入口服务 / Trace ID',
                dataIndex: 'traceId',
                render: (v, r) => (
                  <Space direction="vertical" size={2}>
                    <Space size={6}>
                      <HealthDot level={r.status === 'error' ? 1 : 5} />
                      <span style={{ fontSize: 13, fontWeight: 500 }}>{r.entry}</span>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>{v}</Text>
                  </Space>
                ),
              },
              { title: '资源', dataIndex: 'endpoint', render: (v) => <span style={{ fontSize: 12, fontFamily: 'monospace' }}>{v}</span> },
              { title: '总耗时', dataIndex: 'duration', width: 100, render: (v) => <span style={tabularNumStyle}>{v}</span> },
              { title: '跨度数', dataIndex: 'spans', width: 90, align: 'right' as const, render: (v) => <span style={tabularNumStyle}>{v}</span> },
              {
                title: '状态',
                dataIndex: 'status',
                width: 90,
                render: (v) => v === 'error'
                  ? <Tag color="error" style={{ margin: 0 }}>⚠ 错误数</Tag>
                  : <Tag color="success" style={{ margin: 0 }}>✓ 正常</Tag>,
              },
              { title: '时间', dataIndex: 'time', width: 80, render: (v) => <span style={{ ...tabularNumStyle, fontSize: 12, color: TOKENS.textSecondary }}>{v}</span> },
            ]}
          />
        </Tabs.TabPane>

        {/* —— 错误 —— */}
        <Tabs.TabPane tab="错误" key="errors">
          <div>
            {[
              { name: 'PaymentDeclinedError', msg: 'PaymentDeclinedError: failed processing id=99972 after 240ms', traceId: 'c7573a6b982052e1...', spans: 12, samples: 12, last: '刚刚', stack: 'at PaymentService.process(PaymentService.java:142)\nat RefundService.rollback(RefundService.java:88)' },
              { name: 'ValidationError', msg: 'ValidationError: failed processing id=38391 after 70ms', traceId: 'de7c2c645cc4114d...', spans: 10, samples: 10, last: '8 分钟前', stack: 'at RequestValidator.validate(RequestValidator.java:34)\nat ControllerAdvice.handle(ControllerAdvice.java:21)' },
              { name: 'DownstreamUnavailableError', msg: 'DownstreamUnavailableError: failed processing id=65205 after 134ms', traceId: '359649fda0dbb967...', spans: 9, samples: 9, last: '23 分钟前', stack: 'at DownstreamClient.invoke(DownstreamClient.java:78)\nat RetryTemplate.execute(RetryTemplate.java:32)' },
              { name: 'NullPointerException', msg: 'NullPointerException: failed processing id=28317 after 260ms', traceId: '3a28314db85df060...', spans: 7, samples: 7, last: '47 分钟前', stack: 'at RefundService.rollback(RefundService.java:88)\nat... ' },
            ].map((err) => (
              <div key={err.name} style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    <Space size={8} align="center">
                      <span style={{ fontWeight: 600, color: TOKENS.text, fontSize: 14 }}>{err.name}</span>
                      <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>新增</Tag>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {service.name} · {service.version}
                      </Text>
                    </Space>
                    <div style={{ marginTop: 6 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>{err.msg}</Text>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Space size={16} wrap>
                        <a style={{ color: TOKENS.primary, fontSize: 12 }}>查看样本 trace →</a>
                        <a style={{ color: TOKENS.primary, fontSize: 12 }}>查看相关调用链 →</a>
                        <a style={{ color: TOKENS.primary, fontSize: 12 }}>查看服务错误 →</a>
                      </Space>
                    </div>
                  </div>
                  <Space size={24} align="end">
                    <div style={{ textAlign: 'center' }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>受影响 trace</Text>
                      <div style={{ ...tabularNumStyle, fontSize: 18, fontWeight: 600, color: TOKENS.danger }}>{err.spans}</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>出现次数</Text>
                      <div style={{ ...tabularNumStyle, fontSize: 18, fontWeight: 600, color: TOKENS.danger }}>{err.samples}</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>最近出现</Text>
                      <div style={{ ...tabularNumStyle, fontSize: 13 }}>{err.last}</div>
                    </div>
                  </Space>
                </div>
                <div style={{ marginTop: 10 }}>
                  <a style={{ color: TOKENS.textSecondary, fontSize: 12, cursor: 'pointer' }}>⌃ 堆栈</a>
                </div>
              </div>
            ))}
          </div>
        </Tabs.TabPane>

        {/* —— 运行时(占位)—— */}
        <Tabs.TabPane tab="运行时" key="runtime">
          <div style={{ ...surfaceCardStyle, padding: '64px 24px', textAlign: 'center' }}>
            <Text type="secondary">该服务尚未接入运行时指标采集(JVM/Go Runtime 等)</Text>
          </div>
        </Tabs.TabPane>

        {/* —— 部署 —— */}
        <Tabs.TabPane tab="部署" key="deploy">
          <div style={{ ...surfaceCardStyle, padding: '14px 16px' }}>
            <Text strong>部署事件</Text>
            <List
              size="small"
              style={{ marginTop: 8 }}
              dataSource={[
                { v: service.version, env: service.env, delta: '今日 14:32' },
                { v: 'v5.2.4', env: service.env, delta: '昨日 16:08' },
                { v: 'v5.2.0', env: service.env, delta: '6 天前' },
              ]}
              renderItem={(item) => (
                <List.Item style={{ padding: '8px 0' }}>
                  <Space size={6}>
                    <span style={{ fontSize: 13, color: TOKENS.text }}>{item.v}</span>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>{item.env} · {item.delta}</Text>
                </List.Item>
              )}
            />
          </div>
        </Tabs.TabPane>

        {/* —— SLO(占位)—— */}
        <Tabs.TabPane tab="SLO" key="slo">
          <div style={{ ...surfaceCardStyle, padding: '64px 24px', textAlign: 'center' }}>
            <Text type="secondary">该服务尚未配置 SLO</Text>
          </div>
        </Tabs.TabPane>
      </Tabs>

      <Popconfirm
        title="确认归档该服务?"
        description="归档后告警自动暂停,数据保留期内可恢复。"
        open={archiveOpen}
        onConfirm={() => {
          setArchiveOpen(false);
        }}
        onCancel={() => setArchiveOpen(false)}
      >
        <span style={{ display: 'none' }} />
      </Popconfirm>

      <ApdexThresholdDrawer
        open={apdexDrawerOpen}
        onClose={() => setApdexDrawerOpen(false)}
        serviceName={service.name}
      />
    </div>
  );
}

/* Apdex 满意阈值编辑抽屉(简化版:MVP 只暴露租户默认 + 单服务覆盖) */
function ApdexThresholdDrawer({
  open,
  onClose,
  serviceName,
}: {
  open: boolean;
  onClose: () => void;
  serviceName: string;
}) {
  const [tenantT, setTenantT] = useState(500);
  const [override, setOverride] = useState(false);
  const [serviceT, setServiceT] = useState(500);

  return (
    <Drawer
      title="Apdex 满意阈值"
      placement="right"
      width={400}
      open={open}
      onClose={onClose}
      footer={
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={onClose}>保存</Button>
        </Space>
      }
    >
      <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 0 }}>
        Apdex 按满意阈值 T 把请求分为满意 (≤T) / 容忍 (≤4T) / 沮丧 (&gt;4T)。仅对 Web/HTTP 类服务有意义。
      </Paragraph>

      <Text strong style={{ display: 'block', marginTop: 16, marginBottom: 8 }}>
        租户默认阈值 T
      </Text>
      <InputNumber
        style={{ width: '100%' }}
        value={tenantT}
        onChange={(v) => setTenantT(typeof v === 'number' ? v : 500)}
        addonAfter="毫秒"
        min={0}
      />

      <div style={{ borderTop: `1px dashed ${TOKENS.border}`, margin: '20px 0' }} />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text strong>覆盖本服务({serviceName})</Text>
        <Switch checked={override} onChange={setOverride} size="small" />
      </div>
      <InputNumber
        style={{ width: '100%' }}
        value={serviceT}
        onChange={(v) => setServiceT(typeof v === 'number' ? v : 500)}
        addonAfter="毫秒"
        min={0}
        disabled={!override}
      />
    </Drawer>
  );
}

/* 图例小圆点(时延模式的 P50/P90/P95/P99 图例) */
function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <Space size={6} align="center">
      <span style={{ display: 'inline-block', width: 16, height: 2, background: color }} />
      <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{label}</span>
    </Space>
  );
}

/* RED 时序示意(SVG)— 三视图:throughput / errorRate / latency
 * 支持 hoverIndex 同步:ServiceRedCharts 容器把同一 hoverIndex 推给所有 3 张图,
 * 每张图都画出对应的纵向对齐标记 + 数据点。 */
function RedChart({
  mode = 'latency',
  timeWindow: _tw = '1h',
  hoverIndex = null,
  onHover,
}: {
  mode?: 'throughput' | 'errorRate' | 'latency';
  timeWindow?: TimeWindow;
  hoverIndex?: number | null;
  onHover?: (idx: number | null) => void;
}) {
  const w = 800;
  const h = 140;
  const xs = Array.from({ length: 60 }, (_, i) => i);

  let series: { color: string; values: number[]; min: number; max: number; unit: string; name: string }[] = [];
  if (mode === 'throughput') {
    series = [
      {
        color: TOKENS.primary,
        name: '吞吐量',
        values: xs.map((x) => 200 + 40 * Math.sin(x / 6) + (x > 38 ? 30 : 0)),
        min: 100,
        max: 280,
        unit: 'req/s',
      },
    ];
  } else if (mode === 'errorRate') {
    series = [
      {
        color: TOKENS.danger,
        name: '错误率',
        values: xs.map((x) => (x < 38 ? 0.6 + 0.4 * Math.sin(x / 4) : 6 + 2 * Math.sin(x / 3))),
        min: 0,
        max: 8,
        unit: '%',
      },
    ];
  } else {
    // latency
    series = [
      { color: '#155aef', name: 'P50', values: xs.map((x) => 165 + 8 * Math.sin(x / 5)),  min: 100, max: 290, unit: 'ms' },
      { color: '#8b5cf6', name: 'P90', values: xs.map((x) => 200 + 10 * Math.sin(x / 4)), min: 100, max: 290, unit: 'ms' },
      { color: '#f43b2c', name: 'P95', values: xs.map((x) => 230 + 12 * Math.sin(x / 3)), min: 100, max: 290, unit: 'ms' },
      { color: '#f59e0b', name: 'P99', values: xs.map((x) => 265 + 18 * Math.sin(x / 4)), min: 100, max: 290, unit: 'ms' },
    ];
  }

  const yMin = series[0].min;
  const yMax = series[0].max;
  const toPath = (arr: number[]) => {
    const range = yMax - yMin;
    return arr
      .map((v, i) => {
        const ratio = (v - yMin) / range;
        const x = (i / (arr.length - 1)) * w;
        const y = h - ratio * (h - 20) - 10;
        return `${i === 0 ? 'M' : 'L'}${x},${y}`;
      })
      .join(' ');
  };

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((p) => Math.round(yMin + (yMax - yMin) * p));
  const timeLabels =
    _tw === '7d' || _tw === '1d'
      ? ['5 天前', '4 天前', '3 天前', '2 天前', '今天']
      : _tw === '4h'
        ? ['19:00', '20:00', '21:00', '22:00', '23:00']
        : _tw === '15m'
          ? ['19:45', '19:50', '19:55', '20:00', '20:15']
          : ['20:00', '20:30', '21:00', '21:30', '22:00'];

  const hoverX = hoverIndex !== null ? (hoverIndex / (xs.length - 1)) * w : 0;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      style={{ width: '100%', height: 140, display: 'block', cursor: 'crosshair' }}
      onMouseMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const px = e.clientX - rect.left;
        const ratio = Math.max(0, Math.min(1, px / rect.width));
        const idx = Math.round(ratio * (xs.length - 1));
        onHover?.(idx);
      }}
      onMouseLeave={() => onHover?.(null)}
    >
      <defs>
        <pattern id={`grid-red-${mode}`} width="160" height="28" patternUnits="userSpaceOnUse">
          <path d="M 160 0 L 0 0 0 28" fill="none" stroke={TOKENS.border} strokeWidth="0.5" />
        </pattern>
      </defs>
      <rect width={w} height={h} fill={`url(#grid-red-${mode})`} />

      {/* Y 轴 labels */}
      {yTicks.map((label, i) => {
        const ratio = (label - yMin) / (yMax - yMin);
        const y = h - ratio * (h - 20) - 10;
        return (
          <text key={`y-${i}`} x={4} y={y - 2} fontSize="10" fill={TOKENS.textTertiary}>
            {label}
            {series[0].unit}
          </text>
        );
      })}

      {/* X 轴 labels */}
      {timeLabels.map((label, i) => {
        const x = (i / (timeLabels.length - 1)) * w;
        return (
          <text key={`x-${i}`} x={x} y={h - 2} fontSize="10" fill={TOKENS.textTertiary} textAnchor="middle">
            {label}
          </text>
        );
      })}

      {/* 系列线 */}
      {series.map((s, i) => (
        <path key={`s-${i}`} d={toPath(s.values)} fill="none" stroke={s.color} strokeWidth="1.5" />
      ))}

      {/* hover 标记:所有 3 张图共享同一 hoverIndex,显示同位置的竖虚线 + 数据点 */}
      {hoverIndex !== null && (
        <g>
          <line
            x1={hoverX}
            y1={0}
            x2={hoverX}
            y2={h}
            stroke={TOKENS.primary}
            strokeWidth="1"
            strokeDasharray="3 3"
            opacity={0.6}
          />
          {series.map((s, i) => {
            const v = s.values[hoverIndex];
            const range = yMax - yMin;
            const y = h - ((v - yMin) / range) * (h - 20) - 10;
            return (
              <circle
                key={`hp-${i}`}
                cx={hoverX}
                cy={y}
                r={3.5}
                fill={s.color}
                stroke="white"
                strokeWidth="1.5"
              />
            );
          })}
        </g>
      )}
    </svg>
  );
}

/* 服务详情概览:三图独立 card · 共享 hover 同步
 * 鼠标移到任一图,其他两张图在该时间点也画出对齐标记 */
/* 服务详情概览:RED 时序图(单图 + 内部 tab 切换)
 * 整合模式:一个 card 内,顶部 tab(吞吐 / 错误率 / 时延),下面一张大图 */
function ServiceRedCharts({ timeWindow }: { timeWindow: TimeWindow }) {
  const [view, setView] = useState<'throughput' | 'errorRate' | 'latency'>('throughput');
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const labels =
    timeWindow === '7d' || timeWindow === '1d'
      ? ['5 天前', '4 天前', '3 天前', '2 天前', '今天']
      : timeWindow === '4h'
        ? ['19:00', '20:00', '21:00', '22:00', '23:00']
        : timeWindow === '15m'
          ? ['19:45', '19:50', '19:55', '20:00', '20:15']
          : ['20:00', '20:30', '21:00', '21:30', '22:00'];

  // 实时数值(hover 时显示)
  let hoverText = '';
  if (hoverIndex !== null) {
    const xsLen = 60;
    const tIdx = Math.min(
      Math.round((hoverIndex / (xsLen - 1)) * (labels.length - 1)),
      labels.length - 1,
    );
    const time = labels[tIdx];
    if (view === 'throughput') {
      const v = 200 + 40 * Math.sin(hoverIndex / 6) + (hoverIndex > 38 ? 30 : 0);
      hoverText = `${time}  ·  ${v.toFixed(0)} req/s`;
    } else if (view === 'errorRate') {
      const v = hoverIndex < 38 ? 0.6 + 0.4 * Math.sin(hoverIndex / 4) : 6 + 2 * Math.sin(hoverIndex / 3);
      hoverText = `${time}  ·  ${v.toFixed(1)}%`;
    } else {
      const p50 = 165 + 8 * Math.sin(hoverIndex / 5);
      const p95 = 230 + 12 * Math.sin(hoverIndex / 3);
      hoverText = `${time}  ·  P50 ${p50.toFixed(0)}ms  ·  P95 ${p95.toFixed(0)}ms`;
    }
  }

  return (
    <div style={{ ...surfaceCardStyle, padding: '14px 16px', marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <Segmented
          value={view}
          onChange={(v) => setView(v as typeof view)}
          options={[
            { value: 'throughput', label: '吞吐量' },
            { value: 'errorRate', label: '错误率' },
            { value: 'latency', label: '时延' },
          ]}
        />
        {view === 'latency' && (
          <Space size={14} align="center">
            <LegendDot color="#155aef" label="P50" />
            <LegendDot color="#8b5cf6" label="P90" />
            <LegendDot color="#f43b2c" label="P95" />
            <LegendDot color="#f59e0b" label="P99" />
          </Space>
        )}
      </div>
      {hoverText && (
        <div
          style={{
            fontSize: 12,
            color: TOKENS.textSecondary,
            fontFamily: 'monospace',
            padding: '0 0 8px',
          }}
        >
          {hoverText}
        </div>
      )}
      <RedChart mode={view} timeWindow={timeWindow} hoverIndex={hoverIndex} onHover={setHoverIndex} />
    </div>
  );
}

/* ============================================================
 * ServiceShell:state 容器,贯穿 3 个 service-related Story
 * ============================================================ */
type PageKind = 'app-list' | 'app-detail' | 'service-list' | 'service-detail';

function ServiceShell({
  initialPage = 'app-list',
  initialPerspective = 'application',
  initialApp = null,
  initialService = null,
}: {
  initialPage?: PageKind;
  initialPerspective?: 'application' | 'service';
  initialApp?: AppCard | null;
  initialService?: ServiceRow | null;
}) {
  const [page, setPage] = useState<PageKind>(initialPage);
  const [perspective, setPerspective] = useState<'application' | 'service'>(initialPerspective);
  const [selectedApp, setSelectedApp] = useState<AppCard | null>(initialApp);
  const [selectedService, setSelectedService] = useState<ServiceRow | null>(initialService);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('1h');

  // 同步 perspective 变化到合适 page(视角切换不跳路由,只切内容)
  const handlePerspectiveChange = (next: 'application' | 'service') => {
    setPerspective(next);
    if (page === 'app-list' && next === 'service') {
      setPage('service-list');
    } else if (page === 'service-list' && next === 'application') {
      setPage('app-list');
      setSelectedApp(null);
    } else if (page === 'app-detail' && next === 'service') {
      // 应用详情 → 切到服务视角 = 进入该应用下的服务列表
      setPage('service-list');
    }
  };

  // 应用卡片点击:未归类 → 服务列表(筛 namespace=空);其它 → 应用详情
  const handleAppSelect = (app: AppCard) => {
    setSelectedApp(app);
    setPage(app.isUncategorized ? 'service-list' : 'app-detail');
    if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // 在服务列表(已选应用)清除筛选 → 回到应用视图
  const handleClearApp = () => {
    setSelectedApp(null);
    setPage(perspective === 'application' ? 'app-list' : 'service-list');
  };

  const handleServiceClick = (s: ServiceRow) => {
    setSelectedService(s);
    setPage('service-detail');
    if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // 应用详情返回
  const handleBackFromAppDetail = () => {
    setPage('app-list');
  };

  // 单服务详情返回:根据"前身页"决定落点
  const handleBackFromServiceDetail = () => {
    if (perspective === 'application') {
      if (selectedApp && !selectedApp.isUncategorized) {
        setPage('app-detail'); // 从应用详情下的服务列表 → 回到应用详情
      } else if (selectedApp && selectedApp.isUncategorized) {
        setPage('service-list'); // 从未归类应用下的服务列表 → 回到 service-list(仍带 selectedApp 提示)
      } else {
        setPage('app-list');
      }
    } else {
      setPage('service-list');
    }
  };

  const filteredServices = selectedApp
    ? SERVICES.filter((s) => (selectedApp.isUncategorized ? !s.namespace : s.namespace === selectedApp.key))
    : [];

  const showAppliedBanner = page === 'service-list' && !!selectedApp;

  const content = (() => {
    if (page === 'app-list') {
      return (
        <Row gutter={[16, 16]} align="stretch">
          {APPS.map((app) => (
            <Col xs={24} sm={12} lg={8} xl={6} key={app.key}>
              <ApplicationCard app={app} onSelect={handleAppSelect} />
            </Col>
          ))}
        </Row>
      );
    }
    if (page === 'app-detail' && selectedApp && !selectedApp.isUncategorized) {
      return (
        <AppDetailView
          app={selectedApp}
          services={filteredServices}
          onServiceClick={handleServiceClick}
        />
      );
    }
    if (page === 'service-list') {
      return (
        <>
          {showAppliedBanner && selectedApp && (
            <AppliedAppBanner app={selectedApp} count={filteredServices.length} onClear={handleClearApp} />
          )}
          <ServiceListTable
            rows={showAppliedBanner ? filteredServices : SERVICES}
            selectedApp={showAppliedBanner ? selectedApp : null}
            onServiceClick={handleServiceClick}
          />
        </>
      );
    }
    if (page === 'service-detail' && selectedService) {
      return (
        <ServiceDetailView
          service={selectedService}
          timeWindow={timeWindow}
          onAppClick={handleAppSelect}
        />
      );
    }
    return null;
  })();

  return (
    <Layout style={shellStyle}>
      <TopMenuBar />
      <TopSecondaryNav active="service" />
      <Content style={{ padding: '20px 24px 32px' }}>
        {page === 'app-list' || page === 'service-list' ? (
          <PageToolbar
            mode="list"
            showPerspective
            perspective={perspective}
            onPerspectiveChange={handlePerspectiveChange}
            archivedCount={ARCHIVED_ROWS.length}
            onArchivedClick={() => setDrawerOpen(true)}
            timeWindow={timeWindow}
            onTimeWindowChange={setTimeWindow}
          />
        ) : (
          <PageToolbar
            mode="detail"
            onBack={page === 'app-detail' ? handleBackFromAppDetail : handleBackFromServiceDetail}
            backLabel={page === 'app-detail' ? '返回服务目录' : '返回服务'}
            timeWindow={timeWindow}
            onTimeWindowChange={setTimeWindow}
          />
        )}
        {content}
      </Content>
      <ArchivedDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        rows={ARCHIVED_ROWS}
      />
    </Layout>
  );
}

/* ============================================================
 * 独立故事:服务 → 服务拓扑
 * ============================================================ */
function ServiceTopologyMock() {
  const [layout, setLayout] = useState<'layered' | 'force'>('layered');
  const [anomalyOnly, setAnomalyOnly] = useState(false);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('7d');

  const { nodes, edges } = (() => {
    const nodes: TNode[] = [
      // 用户与权限 (iam)
      { id: 'auth-svc', name: 'auth-svc', sub: 'iam', type: 'service', health: 'good', x: 220, y: 90, appKey: 'iam' },
      { id: 'user-api', name: 'user-api', sub: 'iam', type: 'service', health: 'good', x: 360, y: 90, appKey: 'iam' },
      // 电商主站 (store)
      { id: 'catalog-api', name: 'catalog-api', sub: 'store', type: 'service', health: 'good', x: 80, y: 220, appKey: 'store' },
      { id: 'web-storefront', name: 'web-storefront', sub: 'store', type: 'service', health: 'warning', x: 220, y: 220, appKey: 'store' },
      { id: 'api-gateway', name: 'api-gateway', sub: 'store', type: 'service', health: 'good', x: 360, y: 220, appKey: 'store' },
      // 交易清结算 (billing)
      { id: 'inventory-svc', name: 'inventory-svc', sub: 'billing', type: 'service', health: 'good', x: 500, y: 90, appKey: 'billing' },
      { id: 'payment-svc', name: 'payment-svc', sub: 'billing', type: 'service', health: 'critical', x: 500, y: 220, appKey: 'billing' },
      { id: 'checkout-api', name: 'checkout-api', sub: 'billing', type: 'service', health: 'warning', x: 500, y: 350, appKey: 'billing' },
      // 数据平台 (data)
      { id: 'etl-pipeline', name: 'etl-pipeline', sub: 'data', type: 'service', health: 'good', x: 760, y: 90, appKey: 'data' },
      { id: 'cdc-worker', name: 'cdc-worker', sub: 'data', type: 'service', health: 'warning', x: 900, y: 90, appKey: 'data' },
      // 异步任务 (async) → MQ
      { id: 'notification-worker', name: 'notification-worker', sub: 'async', type: 'mq', health: 'warning', x: 80, y: 380, appKey: 'async' },
      // 共享下游资源
      { id: 'postgres', name: 'postgres', sub: 'pg-main', type: 'database', health: 'good', x: 760, y: 250, appKey: 'shared' },
      { id: 'redis', name: 'redis', sub: 'redis-1', type: 'cache', health: 'good', x: 900, y: 250, appKey: 'shared' },
      { id: 'kafka', name: 'kafka', sub: 'kafka-1', type: 'mq', health: 'unknown', x: 760, y: 380, appKey: 'shared' },
      { id: 'stripe', name: 'stripe-gateway', type: 'external', health: 'unknown', x: 640, y: 410, appKey: 'shared' },
      // 未归类应用
      { id: 'email-gateway', name: 'email-gateway', type: 'external', health: 'good', x: 220, y: 380, appKey: 'external' },
    ];
    const edges: TEdge[] = [
      { from: 'web-storefront', to: 'api-gateway' },
      { from: 'web-storefront', to: 'user-api' },
      { from: 'api-gateway', to: 'auth-svc' },
      { from: 'api-gateway', to: 'catalog-api' },
      { from: 'api-gateway', to: 'payment-svc' },
      { from: 'payment-svc', to: 'inventory-svc', health: 'critical' },
      { from: 'payment-svc', to: 'checkout-api', health: 'warning' },
      { from: 'cdc-worker', to: 'etl-pipeline' },
      { from: 'notification-worker', to: 'payment-svc', health: 'warning' },
      { from: 'payment-svc', to: 'postgres' },
      { from: 'checkout-api', to: 'postgres' },
      { from: 'auth-svc', to: 'postgres' },
      { from: 'catalog-api', to: 'redis' },
      { from: 'api-gateway', to: 'redis' },
      { from: 'checkout-api', to: 'redis' },
      { from: 'payment-svc', to: 'kafka' },
      { from: 'payment-svc', to: 'stripe', health: 'warning' },
      { from: 'cdc-worker', to: 'kafka' },
      { from: 'checkout-api', to: 'email-gateway' },
    ];
    return { nodes, edges };
  })();

  // 摘要统计
  const totalNodes = nodes.length;
  const totalEdges = edges.length;
  const anomalyNodes = nodes.filter((n) => n.health === 'critical' || n.health === 'warning').length;

  // 只看异常 → 高亮过滤(MVP:调透明度,非真过滤避免视觉跳动)
  const displayNodes = anomalyOnly
    ? nodes.map((n) => ({ ...n, health: (n.health === 'critical' || n.health === 'warning' ? n.health : 'good') as THealth }))
    : nodes;

  return (
    <Layout style={shellStyle}>
      <TopMenuBar />
      <TopSecondaryNav active="topology" />
      <Content style={{ padding: '20px 24px 32px' }}>
        {/* 顶部工具栏:摘要 + 时间窗 + 环境 + 布局 + 只看异常 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            marginBottom: 12,
            flexWrap: 'wrap',
          }}
        >
          {/* 摘要计数 */}
          <Space size={4} align="center" style={{ ...surfaceCardStyle, padding: '4px 10px', borderRadius: 16 }}>
            <span style={{ ...tabularNumStyle, fontWeight: 600 }}>{totalNodes}</span>
            <Text type="secondary" style={{ fontSize: 12 }}>服务</Text>
            <span style={{ color: TOKENS.border, margin: '0 4px' }}>·</span>
            <span style={{ ...tabularNumStyle, fontWeight: 600 }}>{totalEdges}</span>
            <Text type="secondary" style={{ fontSize: 12 }}>依赖</Text>
            <span style={{ color: TOKENS.border, margin: '0 4px' }}>·</span>
            <span style={{ ...tabularNumStyle, fontWeight: 600, color: TOKENS.danger }}>{anomalyNodes}</span>
            <Text type="secondary" style={{ fontSize: 12 }}>异常</Text>
          </Space>

          {/* 时间窗 */}
          <Segmented
            value={timeWindow}
            onChange={(v) => setTimeWindow(v as TimeWindow)}
            options={[
              { value: '15m', label: '15m' },
              { value: '1h', label: '1h' },
              { value: '4h', label: '4h' },
              { value: '1d', label: '1d' },
              { value: '7d', label: '7d' },
            ]}
          />

          {/* 环境筛选 */}
          <Select
            defaultValue="all"
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部环境' },
              { value: 'prod', label: '生产' },
              { value: 'staging', label: '预发' },
            ]}
          />

          {/* 布局切换：默认层次，力导向为额外选项 */}
          <Segmented
            value={layout}
            onChange={(v) => setLayout(v as 'layered' | 'force')}
            options={[
              { value: 'layered', label: '层次' },
              { value: 'force', label: '力导向' },
            ]}
          />

          {/* 只看异常 */}
          <Button
            type={anomalyOnly ? 'primary' : 'default'}
            danger={anomalyOnly}
            onClick={() => setAnomalyOnly((v) => !v)}
          >
            ⚠ 只看异常
          </Button>
        </div>

        {/* 画布区 */}
        <div style={{ ...surfaceCardStyle, padding: 0, marginBottom: 12, position: 'relative' }}>
          {/* 左上:定位节点 + 缩放控件 */}
          <div
            style={{
              position: 'absolute',
              top: 12,
              left: 12,
              zIndex: 2,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <Input
              allowClear
              placeholder="定位节点"
              prefix={<SearchOutlined style={{ color: TOKENS.textTertiary }} />}
              style={{ width: 200 }}
            />
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                background: TOKENS.surface,
                border: `1px solid ${TOKENS.border}`,
                borderRadius: 6,
                overflow: 'hidden',
              }}
            >
              <button
                title="放大"
                style={{
                  border: 'none',
                  background: 'transparent',
                  height: 28,
                  width: 32,
                  cursor: 'pointer',
                  fontSize: 16,
                  color: TOKENS.textSecondary,
                  borderBottom: `1px solid ${TOKENS.border}`,
                }}
              >
                +
              </button>
              <button
                title="缩小"
                style={{
                  border: 'none',
                  background: 'transparent',
                  height: 28,
                  width: 32,
                  cursor: 'pointer',
                  fontSize: 16,
                  color: TOKENS.textSecondary,
                  borderBottom: `1px solid ${TOKENS.border}`,
                }}
              >
                −
              </button>
              <button
                title="重置"
                style={{
                  border: 'none',
                  background: 'transparent',
                  height: 28,
                  width: 32,
                  cursor: 'pointer',
                  fontSize: 13,
                  color: TOKENS.textSecondary,
                }}
              >
                ↺
              </button>
            </div>
          </div>

          {/* 右上:迷你缩略图(简化版:固定位置的小视图) */}
          <div
            style={{
              position: 'absolute',
              top: 12,
              right: 12,
              zIndex: 2,
              width: 110,
              height: 70,
              background: TOKENS.surface,
              border: `1px solid ${TOKENS.border}`,
              borderRadius: 6,
              padding: 6,
              display: 'flex',
              gap: 2,
              flexWrap: 'wrap',
              alignContent: 'flex-start',
              opacity: 0.85,
            }}
          >
            {nodes.map((n) => (
              <span
                key={n.id}
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: T_HEALTH_COLOR[n.health],
                }}
              />
            ))}
          </div>

          {/* 主图 */}
          <div style={{ padding: '14px 16px' }}>
            <TopologyGraph nodes={displayNodes} edges={edges} />
          </div>
        </div>

        {/* 底部图例 */}
        <div
          style={{
            ...surfaceCardStyle,
            padding: '10px 16px',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 16,
            fontSize: 12,
            color: TOKENS.textSecondary,
          }}
        >
          {/* 节点颜色 */}
          <Space size={12} wrap>
            <Space size={4}><span style={{ width: 10, height: 10, borderRadius: '50%', background: T_HEALTH_COLOR.good, display: 'inline-block' }} /><span>正常</span></Space>
            <Space size={4}><span style={{ width: 10, height: 10, borderRadius: '50%', background: T_HEALTH_COLOR.warning, display: 'inline-block' }} /><span>警告</span></Space>
            <Space size={4}><span style={{ width: 10, height: 10, borderRadius: '50%', background: T_HEALTH_COLOR.critical, display: 'inline-block' }} /><span>严重</span></Space>
            <Space size={4}><span style={{ width: 10, height: 10, borderRadius: '50%', background: T_HEALTH_COLOR.unknown, display: 'inline-block' }} /><span>未知</span></Space>
          </Space>
          <span style={{ color: TOKENS.border }}>·</span>
          {/* 节点类型 */}
          <Space size={12} wrap>
            <Space size={4}><span style={{ width: 12, height: 12, borderRadius: 2, background: '#e2e8f0', border: '1px solid #64748b', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 8 }}>DB</span><span>数据库</span></Space>
            <Space size={4}><span style={{ width: 12, height: 12, borderRadius: 2, background: '#e2e8f0', border: '1px solid #64748b', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 8 }}>C</span><span>缓存</span></Space>
            <Space size={4}><span style={{ width: 12, height: 12, borderRadius: 2, background: '#e2e8f0', border: '1px solid #64748b', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 8 }}>M</span><span>消息队列</span></Space>
            <Space size={4}><span style={{ width: 12, height: 12, borderRadius: 2, background: '#e2e8f0', border: '1px solid #64748b', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 8 }}>E</span><span>外部依赖</span></Space>
          </Space>
          <span style={{ color: TOKENS.border }}>·</span>
          {/* 节点大小=吞吐 */}
          <Space size={4}><span style={{ width: 8, height: 8, borderRadius: '50%', background: TOKENS.textTertiary, display: 'inline-block' }} /><span style={{ width: 14, height: 14, borderRadius: '50%', background: TOKENS.textTertiary, display: 'inline-block', marginLeft: -8 }} /><span style={{ marginLeft: 10 }}>节点大小 = 吞吐</span></Space>
          <span style={{ color: TOKENS.border }}>·</span>
          {/* 边粗细=调用量 */}
          <Space size={4}>
            <span style={{ width: 18, height: 1, background: '#cbd5e1', display: 'inline-block' }} />
            <span style={{ width: 18, height: 3, background: '#cbd5e1', display: 'inline-block', marginLeft: -4 }} />
            <span style={{ marginLeft: 6 }}>边粗细 = 调用量</span>
          </Space>
          <span style={{ color: TOKENS.border }}>·</span>
          <Space size={4}>
            <span style={{ width: 18, height: 2, background: 'repeating-linear-gradient(to right, #dc2626 0 4px, transparent 4px 8px)', display: 'inline-block' }} />
            <span style={{ color: TOKENS.danger }}>红 = 高错误率</span>
          </Space>
        </div>
      </Content>
    </Layout>
  );
}

/* ============================================================
 * 独立故事:SLO 列表 + 新建 SLO 抽屉(按截图2/3)
 * ============================================================ */
interface SloRow {
  key: string;
  name: string;
  target: string;
  sliType: string;
  objective: number;
  currentRate: number;
  budget: number;
  enabled: boolean;
  met: boolean;
}

const SLO_ROWS: SloRow[] = [
  {
    key: 'test',
    name: 'test',
    target: 'api-gateway',
    sliType: '可用性(非错误率)',
    objective: 99.9,
    currentRate: 100,
    budget: 100,
    enabled: true,
    met: true,
  },
];

function SloProgress({ value }: { value: number }) {
  const color = value >= 80 ? TOKENS.success : value >= 40 ? '#f59e0b' : TOKENS.danger;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
      <div style={{ flex: 1, height: 6, background: TOKENS.border, borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(100, value)}%`, height: '100%', background: color }} />
      </div>
      <span style={{ ...tabularNumStyle, fontSize: 12, color: TOKENS.textSecondary, width: 36 }}>
        {value}%
      </span>
    </div>
  );
}

function SloMetTag({ met }: { met: boolean }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '0 8px',
        height: 20,
        borderRadius: 10,
        background: met ? '#dcfce7' : '#fee2e2',
        color: met ? '#15803d' : '#b91c1c',
        fontSize: 11,
        fontWeight: 500,
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: '50%',
          background: met ? '#15803d' : '#b91c1c',
        }}
      />
      {met ? '达标' : '未达标'}
    </span>
  );
}

function NewSloDrawerMock({
  open,
  onClose,
  serviceOptions,
}: {
  open: boolean;
  onClose: () => void;
  serviceOptions: { value: string; label: string }[];
}) {
  const [objective, setObjective] = useState<number | null>(99.9);
  const [enabled, setEnabled] = useState(true);

  return (
    <Drawer
      title="新建 SLO"
      placement="right"
      width={420}
      open={open}
      onClose={onClose}
      footer={
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={onClose}>创建</Button>
        </Space>
      }
    >
      <div style={{ marginBottom: 16 }}>
        <Text style={{ display: 'block', marginBottom: 4 }}>
          <span style={{ color: TOKENS.danger }}>*</span> 名称
        </Text>
        <Input placeholder="如:结算服务可用性" />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ display: 'block', marginBottom: 4 }}>
          <span style={{ color: TOKENS.danger }}>*</span> 目标服务
        </Text>
        <Select
          showSearch
          placeholder="选择或输入服务名"
          style={{ width: '100%' }}
          options={serviceOptions}
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ display: 'block', marginBottom: 4 }}>端点(可选)</Text>
        <Input placeholder="限定到某个端点(SpanName),留空则为服务级" />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ display: 'block', marginBottom: 4 }}>环境(可选)</Text>
        <Input placeholder="限定环境,留空则统计全部环境" />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ display: 'block', marginBottom: 4 }}>
          <span style={{ color: TOKENS.danger }}>*</span> SLI 类型
        </Text>
        <Select
          defaultValue="availability"
          style={{ width: '100%' }}
          options={[
            { value: 'availability', label: '可用性(非错误率)' },
            { value: 'latency_p99', label: '时延(P99 < 阈值)' },
            { value: 'latency_p95', label: '时延(P95 < 阈值)' },
          ]}
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ display: 'block', marginBottom: 4 }}>
          <span style={{ color: TOKENS.danger }}>*</span> 目标达标率
        </Text>
        <InputNumber
          style={{ width: '100%' }}
          value={objective}
          onChange={(v) => setObjective(typeof v === 'number' ? v : null)}
          addonAfter="%"
          min={0}
          max={100}
          step={0.1}
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ display: 'block', marginBottom: 4 }}>
          <span style={{ color: TOKENS.danger }}>*</span> 评估窗口
        </Text>
        <Select
          defaultValue="rolling30d"
          style={{ width: '100%' }}
          options={[
            { value: 'rolling7d', label: '滚动 7 天' },
            { value: 'rolling30d', label: '滚动 30 天' },
            { value: 'rolling90d', label: '滚动 90 天' },
            { value: 'calendarMonth', label: '自然月' },
          ]}
        />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text>启用</Text>
        <Switch checked={enabled} onChange={setEnabled} />
      </div>
    </Drawer>
  );
}

function SloListMock() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [rows, setRows] = useState<SloRow[]>(SLO_ROWS);

  const serviceOptions = SERVICES.map((s) => ({ value: s.key, label: s.name }));

  const toggle = (key: string, enabled: boolean) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, enabled } : r)));
  };

  return (
    <Layout style={shellStyle}>
      <TopMenuBar />
      <TopSecondaryNav active="slo" />
      <Content style={{ padding: '20px 24px 32px' }}>
        <div
          style={{
            ...surfaceCardStyle,
            padding: '0 0 4px',
            position: 'relative',
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 12,
              right: 16,
              zIndex: 1,
            }}
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
              新建 SLO
            </Button>
          </div>
          <Table
            size="middle"
            rowKey="key"
            pagination={false}
            dataSource={rows}
            columns={[
              {
                title: '名称',
                dataIndex: 'name',
                render: (v, r) => (
                  <Space direction="vertical" size={4}>
                    <span style={{ color: TOKENS.primary, fontWeight: 500 }}>{v}</span>
                    <SloMetTag met={r.met} />
                  </Space>
                ),
              },
              { title: '目标对象', dataIndex: 'target', width: 160 },
              { title: 'SLI 类型', dataIndex: 'sliType', width: 160 },
              {
                title: '目标',
                dataIndex: 'objective',
                width: 100,
                render: (v) => <span style={tabularNumStyle}>{v.toFixed(1)}%</span>,
              },
              {
                title: '当前达标率',
                dataIndex: 'currentRate',
                width: 120,
                render: (v) => <span style={tabularNumStyle}>{v.toFixed(1)}%</span>,
              },
              {
                title: '错误预算剩余',
                dataIndex: 'budget',
                width: 180,
                render: (v) => <SloProgress value={v} />,
              },
              {
                title: '操作',
                width: 130,
                render: (_, r) => (
                  <Space size={8} align="center">
                    <Switch
                      size="small"
                      checked={r.enabled}
                      onChange={(v) => toggle(r.key, v)}
                    />
                    <a style={{ color: TOKENS.primary, cursor: 'pointer' }}>
                      <EditOutlined />
                    </a>
                    <a style={{ color: TOKENS.danger, cursor: 'pointer' }}>
                      <DeleteOutlined />
                    </a>
                  </Space>
                ),
              },
            ]}
          />
        </div>

        <NewSloDrawerMock
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          serviceOptions={serviceOptions}
        />
      </Content>
    </Layout>
  );
}

/* ============================================================
 * 独立故事:服务 / 拓扑 空状态占位
 * ============================================================ */
function EmptyStateMock({ active }: { active: 'service' | 'topology' }) {
  const copy = (() => {
    if (active === 'topology') {
      return {
        icon: <AppstoreOutlined />,
        title: '还没有服务拓扑数据',
        body: (
          <>
            接入 APM 后,这里会自动按「应用 × 健康度 × 调用关系」聚合展示所有被监控的服务。
          </>
        ),
        primary: '前往接入',
        secondary: '查看接入文档',
      };
    }
    return {
      icon: <CloudUploadOutlined />,
      title: '还没有接入任何应用',
      body: (
        <>
          接入 APM 后,这里会自动按「应用」(service.namespace)分组展示所有被监控的服务。
          <br />
          如果你暂时不打算设置 namespace,服务会被归入「未归类应用」卡片,后续可补全。
        </>
      ),
      primary: '前往接入',
      secondary: '查看接入文档',
    };
  })();

  return (
    <Layout style={shellStyle}>
      <TopMenuBar />
      <TopSecondaryNav active={active} />
      <Content style={{ padding: '20px 24px 32px' }}>
        <div style={{ ...surfaceCardStyle, padding: '64px 24px', textAlign: 'center' }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 16,
              background: TOKENS.primarySoft,
              color: TOKENS.primary,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 28,
              marginBottom: 16,
            }}
          >
            {copy.icon}
          </div>
          <Title level={4} style={{ margin: 0 }}>{copy.title}</Title>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 24 }}>
            {copy.body}
          </Paragraph>
          <Space>
            <Button type="primary">{copy.primary}</Button>
            <Button>{copy.secondary}</Button>
          </Space>
        </div>
      </Content>
    </Layout>
  );
}

/* ============================================================
 * Meta + Stories
 * ============================================================ */
const meta = {
  title: 'APM/Service Pages',
  parameters: { layout: 'fullscreen' },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const ServiceDirectoryAppView: Story = {
  name: '服务 → 服务(应用视角)',
  render: () => <ServiceShell initialPage="app-list" initialPerspective="application" />,
};

export const ServiceDirectoryServiceView: Story = {
  name: '服务 → 服务(服务视角)',
  render: () => <ServiceShell initialPage="service-list" initialPerspective="service" />,
};

export const ServiceAppDetail: Story = {
  name: '服务 → 应用详情',
  render: () => (
    <ServiceShell
      initialPage="app-detail"
      initialPerspective="application"
      initialApp={APPS.find((a) => a.key === 'billing') ?? null}
    />
  ),
};

export const ServiceDetail: Story = {
  name: '服务 → 服务详情',
  render: () => (
    <ServiceShell
      initialPage="service-detail"
      initialPerspective="application"
      initialApp={APPS.find((a) => a.key === 'billing') ?? null}
      initialService={SERVICE_OF['payment-svc']}
    />
  ),
};

export const ServiceTopology: Story = {
  name: '服务 → 服务拓扑(应用分组 + 节点三态)',
  render: () => <ServiceTopologyMock />,
};

export const ServiceEmpty: Story = {
  name: '服务 → 服务(空状态)',
  render: () => <EmptyStateMock active="service" />,
};

export const SloList: Story = {
  name: '服务 → SLO 列表',
  render: () => <SloListMock />,
};
