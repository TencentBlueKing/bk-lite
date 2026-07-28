import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import {
  Button,
  Col,
  Dropdown,
  Layout,
  Row,
  Segmented,
  Space,
  Table,
  Typography,
} from 'antd';
import {
  ApartmentOutlined,
  ApiOutlined,
  AppstoreOutlined,
  BellOutlined,
  CompassOutlined,
  DashboardOutlined,
  FieldTimeOutlined,
  FireOutlined,
  RadarChartOutlined,
  RocketOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';

const { Content } = Layout;
const { Title, Paragraph, Text } = Typography;

/* ============================================================
 * bklite APM · 首页 · 交互式故事书
 *
 * 7 段汇总(控制塔 / Datadog 风格):
 *   §3.1 KPI 概览    顶部 6 卡 + sparkline
 *                   (应用数量 / 服务数量 / 活跃告警数 /
 *                    请求量 / 错误请求数 / P95 延迟)
 *   §3.2 健康度分布  环形图(健康 / 警告 / 严重 / 未知) + 图例
 *   §3.3 健康度趋势  3 线时序图(整体 / 核心 / 外部依赖),1h/4h/1d 切换
 *   §3.4 实时告警    未恢复告警倒序,5 条 + 查看全部
 *   §3.5 服务 TOP5 错误率   横条(按严重度着色)
 *   §3.6 P95 响应时间 TOP5 横条(按严重度着色)
 *   §3.7 SLO 概览   4 列表格(服务 / 可用性目标 / 达成率 / 状态)
 *
 * 首页是只读汇总,卡片内容来源于其他菜单的近窗数据(spec §2 / §4)。
 * 视觉风格:克制色白底、细线、大数字、SVG 自绘图表(不引 echarts/recharts)。
 * P0 阶段不展示"最近部署"独立段(部署信息在服务菜单时序叠加)。
 * ============================================================ */

const TOKENS = {
  bg: '#fafbfc',
  surface: '#ffffff',
  border: '#ececec',
  borderStrong: '#e0e0e0',
  text: '#0f172a',
  textSecondary: '#64748b',
  textTertiary: '#94a3b8',
  primary: '#5e6ad2',
  primarySoft: '#eeeefd',
  success: '#10b981',
  successSoft: '#ecfdf5',
  danger: '#f43f5e',
  dangerSoft: '#fff1f2',
  warning: '#f59e0b',
  warningSoft: '#fffbeb',
  info: '#3b82f6',
  neutral: '#94a3b8',
  // 5 个健康度等级色(spec §3.2 数据模型,环形图只展示其中 4 段)
  h1: '#f43f5e', // 严重
  h2: '#f59e0b', // 警告
  h3: '#94a3b8', // 待定
  h4: '#64748b', // 陈旧/失联
  h5: '#10b981', // 健康
  // 环形图 4 段(未知 = 待定 + 陈旧/失联合并展示)
  donut: {
    healthy: '#10b981',
    warning: '#f59e0b',
    danger: '#f43f5e',
    unknown: '#cbd5e1',
  },
};

const shellStyle: React.CSSProperties = {
  minHeight: '100vh',
  background: TOKENS.bg,
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  color: TOKENS.text,
};

const surfaceCardStyle: React.CSSProperties = {
  background: TOKENS.surface,
  border: `1px solid ${TOKENS.border}`,
  borderRadius: 6,
};

const tabularNumStyle: React.CSSProperties = {
  fontVariantNumeric: 'tabular-nums',
};

/* ---------- 跨 Story URL ---------- */
const STORY_URLS = {
  home: '?path=/story/apm-home-pages--home-dashboard-story',
  service: '?path=/story/apm-service-pages--service-directory-app-view',
  topology: '?path=/story/apm-service-pages--service-topology',
  slo: '?path=/story/apm-service-pages--service-slo-list',
  sloConfig: '?path=/story/apm-service-pages--service-slo-create',
  explore: '?path=/story/apm-explore-pages--traces-search',
  events: '?path=/story/apm-events-pages--alerts-list',
  integration: '?path=/story/apm-integration-pages-添加接入--integration-catalog-story',
};

/* ============================================================
 * Sparkline(SVG 自绘,line / area)
 * 用于 KPI 卡底部与右侧(无轴无网格,纯趋势)
 * ============================================================ */
type SparklineKind = 'line' | 'area';
function Sparkline({
  data,
  width = 100,
  height = 28,
  color = TOKENS.primary,
  kind = 'line',
  fillOpacity = 0.18,
}: {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  kind?: SparklineKind;
  fillOpacity?: number;
}) {
  if (data.length === 0) return null;
  const pad = 1;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const xStep = (width - pad * 2) / Math.max(data.length - 1, 1);

  const points = data.map((v, i) => {
    const x = pad + i * xStep;
    const y = pad + (height - pad * 2) * (1 - (v - min) / range);
    return [x, y] as const;
  });
  const linePath = points
    .map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`))
    .join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1][0]} ${height - pad} L ${points[0][0]} ${height - pad} Z`;
  const gradId = `spark-area-${color.replace('#', '')}-${width}-${height}`;

  if (kind === 'area') {
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={fillOpacity} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#${gradId})`} />
        <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      </svg>
    );
  }

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* ============================================================
 * DonutChart(环形图,SVG 自绘,用于 §3.2 健康度分布)
 * - 4 段(健康/警告/严重/未知),按 count 比例分配角度
 * - 段与段之间 1px 白缝
 * - 中心展示总数(可选副标题)
 * ============================================================ */
function DonutChart({
  data,
  size = 180,
  innerRatio = 0.62,
}: {
  data: { label: string; count: number; color: string }[];
  size?: number;
  innerRatio?: number;
}) {
  const total = data.reduce((acc, d) => acc + d.count, 0);
  if (total === 0) return null;
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 2;
  const ir = r * innerRatio;
  const gap = 0.012; // 段间角度间隙(弧度,1px 视觉效果)

  let cumAngle = -Math.PI / 2; // 从 12 点钟方向开始
  const paths = data.map((d) => {
    const angle = (d.count / total) * Math.PI * 2;
    const start = cumAngle + gap / 2;
    const end = cumAngle + angle - gap / 2;
    cumAngle += angle;
    if (end - start <= 0) return null;

    const x1 = cx + r * Math.cos(start);
    const y1 = cy + r * Math.sin(start);
    const x2 = cx + r * Math.cos(end);
    const y2 = cy + r * Math.sin(end);
    const ix1 = cx + ir * Math.cos(end);
    const iy1 = cy + ir * Math.sin(end);
    const ix2 = cx + ir * Math.cos(start);
    const iy2 = cy + ir * Math.sin(start);
    const largeArc = end - start > Math.PI ? 1 : 0;
    return {
      d:
        `M ${x1} ${y1} ` +
        `A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} ` +
        `L ${ix1} ${iy1} ` +
        `A ${ir} ${ir} 0 ${largeArc} 0 ${ix2} ${iy2} Z`,
      color: d.color,
    };
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {paths.map(
        (p, i) => p && <path key={i} d={p.d} fill={p.color} stroke="#ffffff" strokeWidth={1} />,
      )}
    </svg>
  );
}

/* ============================================================
 * TrendChart(多线时序图,SVG 自绘,用于 §3.3 健康度趋势)
 * - 网格 + Y 轴百分比刻度 + X 轴时间刻度 + 3 条折线
 * - 段间留白,不画平滑曲线
 * ============================================================ */
function TrendChart({
  series,
  xLabels,
  yLabels,
  width = 520,
  height = 220,
  padding = { top: 16, right: 12, bottom: 28, left: 40 },
  yMin = 0,
  yMax = 100,
  yUnit = '%',
}: {
  series: { name: string; data: number[]; color: string }[];
  xLabels: string[];
  yLabels: string[];
  width?: number;
  height?: number;
  padding?: { top: number; right: number; bottom: number; left: number };
  yMin?: number;
  yMax?: number;
  yUnit?: string;
}) {
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  const xStep = innerW / Math.max(xLabels.length - 1, 1);
  const yRange = yMax - yMin;
  const toX = (i: number) => padding.left + i * xStep;
  const toY = (v: number) => padding.top + innerH * (1 - (v - yMin) / yRange);

  // Y 网格线
  const yTicks = yLabels.map((lbl) => {
    const v = parseFloat(lbl);
    return { label: lbl, y: toY(v) };
  });

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      {/* 横向网格 */}
      {yTicks.map((t, i) => (
        <g key={i}>
          <line
            x1={padding.left}
            x2={width - padding.right}
            y1={t.y}
            y2={t.y}
            stroke={TOKENS.border}
            strokeWidth={0.5}
            strokeDasharray={i === yTicks.length - 1 ? undefined : '2 2'}
          />
          <text
            x={padding.left - 6}
            y={t.y + 3}
            textAnchor="end"
            fontSize={10}
            fill={TOKENS.textTertiary}
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {t.label}
            {yUnit}
          </text>
        </g>
      ))}
      {/* X 轴标签 */}
      {xLabels.map((lbl, i) => (
        <text
          key={i}
          x={toX(i)}
          y={height - padding.bottom + 16}
          textAnchor="middle"
          fontSize={10}
          fill={TOKENS.textTertiary}
        >
          {lbl}
        </text>
      ))}
      {/* 3 条折线 */}
      {series.map((s, i) => {
        if (s.data.length === 0) return null;
        const xSeg = innerW / Math.max(s.data.length - 1, 1);
        const points = s.data.map((v, idx) => {
          const x = padding.left + idx * xSeg;
          const y = toY(v);
          return [x, y] as const;
        });
        const d = points
          .map(([x, y], idx) => (idx === 0 ? `M ${x} ${y}` : `L ${x} ${y}`))
          .join(' ');
        return (
          <path
            key={i}
            d={d}
            fill="none"
            stroke={s.color}
            strokeWidth={1.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        );
      })}
    </svg>
  );
}

/* ============================================================
 * Top5BarChart(横条,SVG 自绘,用于 §3.5 / §3.6 服务排行)
 * - 5 行,每行: 服务名(左) | 横条(中,按值比例 + 按严重度着色) | 数值(右) | 副信息(右下)
 * ============================================================ */
function Top5BarChart({
  rows,
  valueFormatter,
  colorOf,
  subField,
}: {
  rows: { name: string; value: number; sub: string }[];
  valueFormatter: (v: number) => string;
  colorOf: (v: number) => string;
  subField: string;
}) {
  const max = Math.max(...rows.map((r) => r.value), 0.0001);
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {rows.map((r, i) => {
        const pct = (r.value / max) * 100;
        const color = colorOf(r.value);
        return (
          <div
            key={i}
            style={{
              display: 'grid',
              gridTemplateColumns: '120px 1fr 70px',
              alignItems: 'center',
              gap: 12,
              padding: '10px 0',
              borderBottom: i < rows.length - 1 ? `1px solid ${TOKENS.border}` : 'none',
            }}
          >
            <a
              style={{
                color: TOKENS.text,
                fontSize: 13,
                fontWeight: 500,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={r.name}
            >
              {r.name}
            </a>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <div
                style={{
                  flex: 1,
                  height: 4,
                  background: TOKENS.bg,
                  borderRadius: 2,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${pct}%`,
                    height: '100%',
                    background: color,
                    borderRadius: 2,
                    transition: 'width 0.2s',
                  }}
                />
              </div>
              <span
                style={{
                  ...tabularNumStyle,
                  fontSize: 11,
                  color: TOKENS.textTertiary,
                  minWidth: 100,
                  textAlign: 'right',
                }}
              >
                {subField} {r.sub}
              </span>
            </div>
            <span
              style={{
                ...tabularNumStyle,
                fontSize: 14,
                color: color,
                fontWeight: 600,
                textAlign: 'right',
              }}
            >
              {valueFormatter(r.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ============================================================
 * 顶导(全局一级菜单):首页 / 服务 / 探索 / 事件 / 集成
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
 * 时间窗 segmented(右上角全局控件,样式对齐服务页)
 * 5 个固定档位:15m / 1h / 4h / 1d / 7d(默认 1h)
 * ============================================================ */
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

/* ============================================================
 * 首页工具栏:仅右侧时间窗控件,无标题/副标题/刷新状态
 * 首页作为 P0 入口无需展示页面名,顶部即为内容
 * ============================================================ */
function HomeToolbar({
  timeWindow,
  onTimeWindowChange,
}: {
  timeWindow: TimeWindow;
  onTimeWindowChange: (v: TimeWindow) => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        padding: '0 4px 16px 4px',
      }}
    >
      <TimeWindowControl value={timeWindow} onChange={onTimeWindowChange} />
    </div>
  );
}

/* ============================================================
 * §3.1 KPI 概览 · 单卡
 * 字段(图标 + 指标名 + 主数值 + sparkline),不放较昨日
 * ============================================================ */
interface KpiConfig {
  key: string;
  label: string;
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  value: React.ReactNode;
  unit?: string;
  trend: number[];
  sparkColor: string;
  sparkKind?: SparklineKind;
}

function KpiCard({ kpi }: { kpi: KpiConfig }) {
  return (
    <div
      style={{
        ...surfaceCardStyle,
        padding: '18px 20px 14px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      {/* 顶部: 图标 + 指标名 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 4,
            background: kpi.iconBg,
            color: kpi.iconColor,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          {kpi.icon}
        </div>
        <span style={{ fontSize: 12, color: TOKENS.textSecondary, fontWeight: 500 }}>
          {kpi.label}
        </span>
      </div>

      {/* 主数值(只展示当前值,无较昨日) */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
        <span
          style={{
            ...tabularNumStyle,
            fontSize: 28,
            fontWeight: 600,
            color: TOKENS.text,
            lineHeight: 1.1,
            letterSpacing: -0.5,
          }}
        >
          {kpi.value}
        </span>
        {kpi.unit && (
          <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{kpi.unit}</span>
        )}
      </div>

      {/* sparkline */}
      <div style={{ marginTop: 'auto', paddingTop: 4 }}>
        <Sparkline
          data={kpi.trend}
          width={200}
          height={28}
          color={kpi.sparkColor}
          kind={kpi.sparkKind || 'area'}
        />
      </div>
    </div>
  );
}

/* ============================================================
 * §3.1 KPI 概览 · 6 卡横排
 * ============================================================ */
const KPI_DATA: KpiConfig[] = [
  {
    key: 'apps',
    label: '应用数量',
    icon: <ApartmentOutlined />,
    iconBg: TOKENS.primarySoft,
    iconColor: TOKENS.primary,
    value: '24',
    trend: [16, 17, 18, 19, 20, 21, 21, 22, 22, 22, 23, 23, 23, 23, 23, 24, 24, 24, 24, 24, 24, 24, 24, 24],
    sparkColor: TOKENS.primary,
    sparkKind: 'area',
  },
  {
    key: 'services',
    label: '服务数量',
    icon: <AppstoreOutlined />,
    iconBg: TOKENS.primarySoft,
    iconColor: TOKENS.primary,
    value: '128',
    trend: [120, 120, 121, 121, 122, 122, 123, 123, 124, 124, 124, 125, 125, 125, 125, 125, 126, 126, 126, 127, 127, 127, 128, 128],
    sparkColor: TOKENS.primary,
    sparkKind: 'area',
  },
  {
    key: 'alerts',
    label: '活跃告警数',
    icon: <BellOutlined />,
    iconBg: TOKENS.dangerSoft,
    iconColor: TOKENS.danger,
    value: '6',
    trend: [1, 1, 2, 1, 2, 3, 2, 1, 2, 1, 2, 2, 3, 2, 1, 1, 1, 2, 2, 3, 2, 2, 1, 1, 2, 3, 4, 6],
    sparkColor: TOKENS.danger,
    sparkKind: 'area',
  },
  {
    key: 'requests',
    label: '请求量',
    icon: <ApiOutlined />,
    iconBg: TOKENS.primarySoft,
    iconColor: TOKENS.primary,
    value: '3.42',
    unit: 'k req/s',
    trend: [2.8, 2.9, 2.85, 2.95, 3.0, 3.05, 3.1, 3.0, 3.15, 3.1, 3.2, 3.25, 3.2, 3.3, 3.25, 3.3, 3.35, 3.3, 3.4, 3.35, 3.4, 3.38, 3.4, 3.42],
    sparkColor: TOKENS.primary,
    sparkKind: 'area',
  },
  {
    key: 'errors',
    label: '错误请求数',
    icon: <WarningOutlined />,
    iconBg: TOKENS.dangerSoft,
    iconColor: TOKENS.danger,
    value: '17',
    unit: '/s',
    trend: [3, 4, 5, 6, 7, 8, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 15, 15, 16, 16, 16, 17, 17, 17],
    sparkColor: TOKENS.danger,
    sparkKind: 'area',
  },
  {
    key: 'p95',
    label: 'P95 延迟',
    icon: <FieldTimeOutlined />,
    iconBg: TOKENS.warningSoft,
    iconColor: TOKENS.warning,
    value: '285',
    unit: 'ms',
    trend: [180, 195, 210, 220, 230, 240, 250, 255, 260, 265, 270, 275, 275, 280, 280, 285, 280, 285, 285, 290, 290, 285, 285, 285],
    sparkColor: TOKENS.warning,
    sparkKind: 'area',
  },
];

function KpiStrip() {
  return (
    <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
      {KPI_DATA.map((k) => (
        <Col key={k.key} xs={12} sm={8} md={8} lg={4} xl={4}>
          <KpiCard kpi={k} />
        </Col>
      ))}
    </Row>
  );
}

/* ============================================================
 * §3.2 健康度分布(环形图)
 * 4 段:健康 / 警告 / 严重 / 未知(待定 + 陈旧/失联合并展示)
 * ============================================================ */
const HEALTH_DISTRIBUTION = [
  { label: '健康', count: 82, color: TOKENS.donut.healthy },
  { label: '警告', count: 28, color: TOKENS.donut.warning },
  { label: '严重', count: 12, color: TOKENS.donut.danger },
  { label: '未知', count: 6, color: TOKENS.donut.unknown }, // 待定 + 陈旧/失联合并
];

function HealthDistributionCard() {
  const total = HEALTH_DISTRIBUTION.reduce((a, b) => a + b.count, 0);
  return (
    <div style={{ ...surfaceCardStyle, padding: '20px 24px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Space size={8} align="center">
          <DashboardOutlined style={{ color: TOKENS.primary, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            服务健康度分布
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>近窗 15 分钟</Text>
        </Space>
        <a href={STORY_URLS.service} style={{ color: TOKENS.primary, fontSize: 13 }}>
          查看全部 →
        </a>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 16, alignItems: 'center' }}>
        {/* 环形图 + 中心数字 */}
        <div style={{ position: 'relative', width: 180, height: 180 }}>
          <DonutChart data={HEALTH_DISTRIBUTION} size={180} />
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            <span
              style={{
                ...tabularNumStyle,
                fontSize: 32,
                fontWeight: 600,
                color: TOKENS.text,
                lineHeight: 1.1,
                letterSpacing: -0.5,
              }}
            >
              {total}
            </span>
            <span style={{ fontSize: 11, color: TOKENS.textTertiary, marginTop: 2 }}>总服务数</span>
          </div>
        </div>
        {/* 图例 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {HEALTH_DISTRIBUTION.map((d) => {
            const pct = ((d.count / total) * 100).toFixed(0);
            return (
              <div
                key={d.label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 13,
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 2,
                    background: d.color,
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: TOKENS.text, fontWeight: 500, flex: 1 }}>{d.label}</span>
                <span style={{ ...tabularNumStyle, color: TOKENS.text, fontWeight: 600 }}>{d.count}</span>
                <span style={{ ...tabularNumStyle, color: TOKENS.textTertiary, minWidth: 36, textAlign: 'right' }}>
                  ({pct}%)
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
 * §3.3 健康度趋势(3 线时序图)
 * 3 条线:整体健康度 / 核心服务 / 外部依赖
 * 时间窗:1h / 4h / 1d(默认 1h)
 * ============================================================ */
const TREND_RANGES = {
  '1h': {
    labels: ['09:00', '09:15', '09:30', '09:45', '10:00'],
    series: [
      {
        name: '整体健康度',
        data: [88, 89, 90, 91, 90, 91, 92, 92, 91, 92, 92, 92, 92, 92, 92, 92, 92, 92, 92, 92, 93, 92, 92, 92],
        color: TOKENS.success,
      },
      {
        name: '核心服务',
        data: [96, 96, 97, 97, 96, 97, 97, 98, 98, 97, 98, 98, 98, 98, 98, 98, 98, 98, 98, 98, 99, 99, 98, 98],
        color: TOKENS.primary,
      },
      {
        name: '外部依赖',
        data: [78, 80, 79, 81, 82, 80, 82, 83, 82, 84, 85, 84, 86, 85, 87, 86, 88, 87, 86, 88, 87, 88, 89, 88],
        color: TOKENS.warning,
      },
    ],
  },
  '4h': {
    labels: ['06:00', '07:00', '08:00', '09:00', '10:00'],
    series: [
      {
        name: '整体健康度',
        data: [89, 90, 91, 90, 92],
        color: TOKENS.success,
      },
      {
        name: '核心服务',
        data: [97, 97, 98, 97, 98],
        color: TOKENS.primary,
      },
      {
        name: '外部依赖',
        data: [80, 82, 83, 81, 87],
        color: TOKENS.warning,
      },
    ],
  },
  '1d': {
    labels: ['昨日 10:00', '14:00', '18:00', '22:00', '今日 10:00'],
    series: [
      {
        name: '整体健康度',
        data: [93, 91, 90, 89, 92],
        color: TOKENS.success,
      },
      {
        name: '核心服务',
        data: [98, 98, 97, 96, 98],
        color: TOKENS.primary,
      },
      {
        name: '外部依赖',
        data: [85, 83, 82, 80, 88],
        color: TOKENS.warning,
      },
    ],
  },
};

function HealthTrendCard() {
  const [range, setRange] = useState<'1h' | '4h' | '1d'>('1h');
  const conf = TREND_RANGES[range];

  return (
    <div style={{ ...surfaceCardStyle, padding: '20px 24px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <RadarChartOutlined style={{ color: TOKENS.primary, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            服务健康度趋势
          </Title>
        </Space>
        <Dropdown
          menu={{
            items: [
              { key: '1h', label: '近 1 小时' },
              { key: '4h', label: '近 4 小时' },
              { key: '1d', label: '近 1 天' },
            ],
            onClick: ({ key }) => setRange(key as '1h' | '4h' | '1d'),
            selectedKeys: [range],
          }}
        >
          <a style={{ color: TOKENS.text, fontSize: 13, cursor: 'pointer' }}>
            {range === '1h' ? '近 1 小时' : range === '4h' ? '近 4 小时' : '近 1 天'} ▾
          </a>
        </Dropdown>
      </div>
      <TrendChart
        series={conf.series}
        xLabels={conf.labels}
        yLabels={['100', '75', '50', '25', '0']}
        width={520}
        height={220}
      />
      {/* 图例 */}
      <div style={{ display: 'flex', gap: 16, marginTop: 8, flexWrap: 'wrap' }}>
        {conf.series.map((s) => {
          const avg = s.data.length
            ? (s.data.reduce((a, b) => a + b, 0) / s.data.length).toFixed(1)
            : '—';
          return (
            <Space key={s.name} size={6} align="center">
              <span
                style={{
                  width: 10,
                  height: 2,
                  background: s.color,
                  display: 'inline-block',
                }}
              />
              <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{s.name}</span>
              <span style={{ ...tabularNumStyle, fontSize: 12, color: TOKENS.text, fontWeight: 600 }}>
                {avg}%
              </span>
            </Space>
          );
        })}
      </div>
    </div>
  );
}

/* ============================================================
 * §3.4 实时告警(未恢复,倒序,最多 5 条)
 * ============================================================ */
const REALTIME_ALERTS = [
  { key: '1', service: 'payment-service', name: '错误率过高', state: '严重' as const, ago: '刚刚' },
  { key: '2', service: 'checkout-api', name: '响应时间过长', state: '警告' as const, ago: '2 分钟前' },
  { key: '3', service: 'auth-service', name: '实例不可用', state: '严重' as const, ago: '5 分钟前' },
  { key: '4', service: 'user-service', name: '错误率升高', state: '警告' as const, ago: '5 分钟前' },
  { key: '5', service: 'catalog-api', name: 'CPU 使用率过高', state: '警告' as const, ago: '10 分钟前' },
];

const ALERT_STATE_STYLE: Record<'严重' | '警告', { color: string; bg: string }> = {
  严重: { color: TOKENS.danger, bg: TOKENS.dangerSoft },
  警告: { color: TOKENS.warning, bg: TOKENS.warningSoft },
};

function RealtimeAlertsCard() {
  return (
    <div style={{ ...surfaceCardStyle, padding: '20px 24px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <BellOutlined style={{ color: TOKENS.danger, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            实时告警
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>未恢复</Text>
        </Space>
        <a href={STORY_URLS.events} style={{ color: TOKENS.primary, fontSize: 13 }}>
          查看全部 →
        </a>
      </div>
      {REALTIME_ALERTS.length === 0 ? (
        <div
          style={{
            padding: '40px 0',
            textAlign: 'center',
            color: TOKENS.success,
            fontSize: 13,
          }}
        >
          ✓ 一切正常,无未恢复告警
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {REALTIME_ALERTS.map((a, i) => {
            const s = ALERT_STATE_STYLE[a.state];
            return (
              <div
                key={a.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 0',
                  borderBottom: i < REALTIME_ALERTS.length - 1 ? `1px solid ${TOKENS.border}` : 'none',
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: s.color,
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <a
                    style={{
                      color: TOKENS.text,
                      fontSize: 13,
                      fontWeight: 500,
                      display: 'block',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                    title={`${a.service} · ${a.name}`}
                  >
                    {a.service}
                  </a>
                  <div style={{ fontSize: 11, color: TOKENS.textTertiary, marginTop: 2 }}>
                    {a.name}
                  </div>
                </div>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    color: s.color,
                    background: s.bg,
                    padding: '2px 8px',
                    borderRadius: 3,
                  }}
                >
                  {a.state}
                </span>
                <span
                  style={{
                    ...tabularNumStyle,
                    fontSize: 11,
                    color: TOKENS.textTertiary,
                    minWidth: 60,
                    textAlign: 'right',
                  }}
                >
                  {a.ago}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * §3.5 服务 TOP5 按错误率
 * 横条,按严重度着色(≥ 1% 红,≥ 0.1% 黄,< 0.1% 绿)
 * ============================================================ */
const TOP5_ERROR_RATE = [
  { name: 'payment-service', value: 7.21, sub: '856ms' },
  { name: 'checkout-api', value: 2.89, sub: '612ms' },
  { name: 'auth-service', value: 1.65, sub: '398ms' },
  { name: 'order-service', value: 0.72, sub: '210ms' },
  { name: 'inventory-service', value: 0.41, sub: '186ms' },
];

function errorRateColor(v: number) {
  if (v >= 1) return TOKENS.danger;
  if (v >= 0.1) return TOKENS.warning;
  return TOKENS.success;
}

function Top5ByErrorRateCard() {
  return (
    <div style={{ ...surfaceCardStyle, padding: '20px 24px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <FireOutlined style={{ color: TOKENS.danger, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            服务 TOP5 (按错误率)
          </Title>
        </Space>
        <a href={STORY_URLS.service} style={{ color: TOKENS.primary, fontSize: 13 }}>
          查看全部 →
        </a>
      </div>
      <Top5BarChart
        rows={TOP5_ERROR_RATE}
        valueFormatter={(v) => `${v.toFixed(2)}%`}
        colorOf={errorRateColor}
        subField="P95"
      />
    </div>
  );
}

/* ============================================================
 * §3.6 P95 响应时间 TOP5
 * 横条,按严重度着色(≥ 1s 红,≥ 300ms 黄,< 300ms 绿)
 * ============================================================ */
const TOP5_P95 = [
  { name: 'checkout-api', value: 856, sub: '124/s' },
  { name: 'payment-service', value: 612, sub: '342/s' },
  { name: 'order-service', value: 398, sub: '1.2k/s' },
  { name: 'user-service', value: 210, sub: '568/s' },
  { name: 'catalog-api', value: 186, sub: '1.4k/s' },
];

function p95Color(v: number) {
  if (v >= 1000) return TOKENS.danger;
  if (v >= 300) return TOKENS.warning;
  return TOKENS.success;
}

function Top5ByP95Card() {
  return (
    <div style={{ ...surfaceCardStyle, padding: '20px 24px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <ThunderboltOutlined style={{ color: TOKENS.warning, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            P95 响应时间 TOP5
          </Title>
        </Space>
        <a href={STORY_URLS.service} style={{ color: TOKENS.primary, fontSize: 13 }}>
          查看全部 →
        </a>
      </div>
      <Top5BarChart
        rows={TOP5_P95}
        valueFormatter={(v) => `${v}ms`}
        colorOf={p95Color}
        subField="吞吐"
      />
    </div>
  );
}

/* ============================================================
 * §3.7 SLO 概览(4 列表格:服务 / 可用性目标 / 达成率 / 状态)
 * 状态:达成(绿) / 未达成(红)
 * ============================================================ */
const SLO_OVERVIEW = [
  { key: '1', service: 'payment-service', target: '99.9%', rate: '98.6%', met: false },
  { key: '2', service: 'checkout-api', target: '99.5%', rate: '99.7%', met: true },
  { key: '3', service: 'api-gateway', target: '99.9%', rate: '99.92%', met: true },
  { key: '4', service: 'auth-service', target: '99.0%', rate: '98.1%', met: false },
  { key: '5', service: 'inventory-service', target: '99.5%', rate: '99.8%', met: true },
];

function SloOverviewCard() {
  return (
    <div style={{ ...surfaceCardStyle, padding: '20px 24px', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <Space size={8} align="center">
          <DashboardOutlined style={{ color: TOKENS.primary, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            SLO 概览
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>已配置 SLO</Text>
        </Space>
        <a href={STORY_URLS.slo} style={{ color: TOKENS.primary, fontSize: 13 }}>
          查看全部 →
        </a>
      </div>
      {SLO_OVERVIEW.length === 0 ? (
        <div
          style={{
            padding: '40px 0',
            textAlign: 'center',
            color: TOKENS.textSecondary,
            fontSize: 13,
          }}
        >
          暂无 SLO 配置
          <div style={{ marginTop: 8 }}>
            <a href={STORY_URLS.sloConfig} style={{ color: TOKENS.primary }}>
              前往配置 →
            </a>
          </div>
        </div>
      ) : (
        <Table
          size="small"
          rowKey="key"
          pagination={false}
          dataSource={SLO_OVERVIEW}
          showHeader
          style={{ marginTop: 4 }}
          columns={[
            {
              title: '服务',
              dataIndex: 'service',
              render: (v) => <a style={{ color: TOKENS.text, fontWeight: 500, fontSize: 13 }}>{v}</a>,
            },
            {
              title: '可用性目标',
              dataIndex: 'target',
              width: 110,
              align: 'right' as const,
              render: (v) => (
                <span style={{ ...tabularNumStyle, fontSize: 13, color: TOKENS.textSecondary }}>{v}</span>
              ),
            },
            {
              title: '达成率',
              dataIndex: 'rate',
              width: 100,
              align: 'right' as const,
              render: (v, r) => {
                const color = r.met ? TOKENS.success : TOKENS.danger;
                return (
                  <span
                    style={{
                      ...tabularNumStyle,
                      fontSize: 13,
                      color,
                      fontWeight: 600,
                    }}
                  >
                    {v}
                  </span>
                );
              },
            },
            {
              title: '状态',
              dataIndex: 'met',
              width: 90,
              align: 'center' as const,
              render: (v: boolean) => {
                const label = v ? '达成' : '未达成';
                const color = v ? TOKENS.success : TOKENS.danger;
                const bg = v ? TOKENS.successSoft : TOKENS.dangerSoft;
                return (
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 500,
                      color,
                      background: bg,
                      padding: '2px 10px',
                      borderRadius: 3,
                      display: 'inline-block',
                      minWidth: 50,
                    }}
                  >
                    {label}
                  </span>
                );
              },
            },
          ]}
        />
      )}
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
        padding: '80px 32px',
        textAlign: 'center',
        marginTop: 16,
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 12,
          background: TOKENS.primarySoft,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 20,
        }}
      >
        <RocketOutlined style={{ fontSize: 24, color: TOKENS.primary }} />
      </div>
      <Title level={4} style={{ marginBottom: 8, fontWeight: 600 }}>
        还没有接入任何应用
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 24, fontSize: 13 }}>
        前往集成菜单完成首次接入,数分钟内即可在首页看到 6 个 KPI 与 7 段汇总。
      </Paragraph>
      <Space size={8}>
        <Button type="primary" href={STORY_URLS.integration} style={{ borderRadius: 4 }}>
          前往集成菜单
        </Button>
        <Button href={STORY_URLS.explore} style={{ borderRadius: 4 }}>
          查看调用链示例
        </Button>
      </Space>
    </div>
  );
}

/* ============================================================
 * HomeDashboard · 完整首页
 * 布局:TopMenuBar + HomeToolbar
 *       + KpiStrip(6 卡)
 *       + Row1[健康度分布 | 健康度趋势 | 实时告警]
 *       + Row2[TOP5 错误率 | P95 TOP5 | SLO 概览]
 * ============================================================ */
function HomeDashboard() {
  const [empty, setEmpty] = useState(false);
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('1h');
  return (
    <div style={shellStyle}>
      <TopMenuBar active="home" />
      <Content style={{ padding: '24px 32px 40px' }}>
        <HomeToolbar timeWindow={timeWindow} onTimeWindowChange={setTimeWindow} />
        {empty ? (
          <HomeEmptyState />
        ) : (
          <>
            <KpiStrip />
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={8}>
                <HealthDistributionCard />
              </Col>
              <Col xs={24} lg={8}>
                <HealthTrendCard />
              </Col>
              <Col xs={24} lg={8}>
                <RealtimeAlertsCard />
              </Col>
            </Row>
            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} lg={8}>
                <Top5ByErrorRateCard />
              </Col>
              <Col xs={24} lg={8}>
                <Top5ByP95Card />
              </Col>
              <Col xs={24} lg={8}>
                <SloOverviewCard />
              </Col>
            </Row>
            <div
              style={{
                marginTop: 24,
                paddingTop: 16,
                borderTop: `1px solid ${TOKENS.border}`,
                textAlign: 'center',
              }}
            >
              <Button
                type="text"
                size="small"
                onClick={() => setEmpty(true)}
                style={{ color: TOKENS.textTertiary, fontSize: 12 }}
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
