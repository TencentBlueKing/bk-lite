import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useEffect, useState } from 'react';
import {
  Button,
  Collapse,
  Col,
  Layout,
  List,
  Row,
  Segmented,
  Space,
  Table,
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
 * 5 张汇总卡(全局健康度 / 活跃服务 / SLO 违约 / 最近错误 / 最近部署),
 * 首页是只读汇总,卡片内容来源于其他菜单的近窗数据(spec §3 / §4)。
 * 视觉风格:Linear 风格(白底、细线、克制色、大数字、SVG 自绘 sparkline)。
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
  danger: '#f43f5e',
  warning: '#f59e0b',
  neutral: '#94a3b8',
  // 5 个健康度等级色(从危险到健康)
  h1: '#f43f5e', // 严重
  h2: '#f59e0b', // 警告
  h3: '#94a3b8', // 待定
  h4: '#64748b', // 陈旧/失联
  h5: '#10b981', // 健康
};

const HEALTH_COLORS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: TOKENS.h1,
  2: TOKENS.h2,
  3: TOKENS.h3,
  4: TOKENS.h4,
  5: TOKENS.h5,
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
  explore: '?path=/story/apm-explore-pages--traces-search',
  events: '?path=/story/apm-events-pages--alerts-list',
  integration: '?path=/story/apm-integration-pages-添加接入--integration-catalog-story',
};

/* ============================================================
 * Sparkline(SVG 自绘,不引 echarts/recharts;spec §3 字段保持不变,仅呈现方式)
 * - line: 折线
 * - area: 折线 + 渐变面积
 * - bar:  柱状
 * ============================================================ */
type SparklineKind = 'line' | 'area' | 'bar';
function Sparkline({
  data,
  width = 100,
  height = 28,
  color = TOKENS.primary,
  kind = 'line',
  fillOpacity = 0.12,
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

  if (kind === 'bar') {
    const barW = (width - pad * 2) / data.length;
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {data.map((v, i) => {
          const h = ((v - min) / range) * (height - pad * 2);
          return (
            <rect
              key={i}
              x={pad + i * barW + barW * 0.15}
              y={height - pad - h}
              width={barW * 0.7}
              height={h}
              fill={color}
              opacity={0.85}
              rx={1}
            />
          );
        })}
      </svg>
    );
  }

  const points = data.map((v, i) => {
    const x = pad + i * xStep;
    const y = pad + (height - pad * 2) * (1 - (v - min) / range);
    return [x, y] as const;
  });
  const linePath = points
    .map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`))
    .join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1][0]} ${height - pad} L ${points[0][0]} ${height - pad} Z`;

  if (kind === 'area') {
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id={`spark-area-${color.replace('#', '')}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={fillOpacity} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#spark-area-${color.replace('#', '')})`} />
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

/* ---------- 多线 sparkline(用于 hero 健康度 5 状态趋势) ---------- */
function MultiLineSparkline({
  series,
  width = 320,
  height = 80,
}: {
  series: { data: number[]; color: string }[];
  width?: number;
  height?: number;
}) {
  const pad = 2;
  if (series.every((s) => s.data.length === 0)) return null;
  const allValues = series.flatMap((s) => s.data);
  const max = Math.max(...allValues);
  const min = Math.min(...allValues, 0);
  const range = max - min || 1;
  const len = series[0]?.data.length || 0;
  const xStep = (width - pad * 2) / Math.max(len - 1, 1);

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      {[0.25, 0.5, 0.75].map((p) => (
        <line
          key={p}
          x1={pad}
          y1={pad + (height - pad * 2) * p}
          x2={width - pad}
          y2={pad + (height - pad * 2) * p}
          stroke={TOKENS.border}
          strokeWidth={0.5}
        />
      ))}
      {series.map((s, i) => {
        const points = s.data.map((v, idx) => {
          const x = pad + idx * xStep;
          const y = pad + (height - pad * 2) * (1 - (v - min) / range);
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
            strokeWidth={1.2}
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity={0.85}
          />
        );
      })}
    </svg>
  );
}

/* ============================================================
 * 顶导(全局一级菜单):首页 / 服务 / 探索 / 事件 / 集成
 * "服务拓扑" / "SLO" 是"服务"一级菜单下的二级 tab,不在顶导中重复。
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
 * 首页工具栏:仅"刷新全部"按钮,首页时间窗不可自定义
 * ============================================================ */
function HomeToolbar({ onRefresh }: { onRefresh?: () => void }) {
  // 「X 秒前更新」 + auto refresh 倒计时:每 30 秒自动刷新一次,告诉用户数据新鲜度
  const REFRESH_INTERVAL = 30;
  const [lastUpdated, setLastUpdated] = useState<number>(Date.now());
  const [countdown, setCountdown] = useState<number>(REFRESH_INTERVAL);

  useEffect(() => {
    const t = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          setLastUpdated(Date.now());
          return REFRESH_INTERVAL;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, []);

  const handleRefresh = () => {
    setLastUpdated(Date.now());
    setCountdown(REFRESH_INTERVAL);
    onRefresh?.();
  };

  const ago = Math.max(0, Math.floor((Date.now() - lastUpdated) / 1000));
  const fresh = ago < 5;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 4px 20px 4px',
      }}
    >
      <Space size={12} align="baseline">
        <Title level={3} style={{ margin: 0, fontWeight: 600, letterSpacing: -0.3 }}>
          平台总览
        </Title>
        <Text style={{ fontSize: 13, color: TOKENS.textSecondary }}>
          各域近窗数据 · Group 隔离 · 首页时间窗不可自定义
        </Text>
      </Space>
      <Space size={12}>
        <Text style={{ fontSize: 12, color: fresh ? TOKENS.success : TOKENS.textTertiary }}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {ago === 0 ? '刚刚更新' : `${ago} 秒前更新`}
        </Text>
        <Text style={{ fontSize: 12, color: TOKENS.textTertiary, fontVariantNumeric: 'tabular-nums' }}>
          {countdown}s 后自动刷新
        </Text>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          style={{ borderRadius: 4 }}
        >
          刷新
        </Button>
      </Space>
    </div>
  );
}

/* ============================================================
 * 全局健康度大卡(顶部 hero,左 60% 大数字 + 5 状态分布,右 40% 24h multisparkline)
 * 字段:严重/警告/待定/陈旧/失联/健康/总数 (spec §3.1)
 * ============================================================ */
function GlobalHealthCard() {
  const buckets = [
    { level: 1 as const, label: '严重', count: 2 },
    { level: 2 as const, label: '警告', count: 3 },
    { level: 3 as const, label: '待定', count: 4 },
    { level: 4 as const, label: '陈旧/失联', count: 1 },
    { level: 5 as const, label: '健康', count: 22 },
  ];
  const total = buckets.reduce((a, b) => a + b.count, 0);
  const healthy = buckets[buckets.length - 1].count;
  const danger = buckets[0].count + buckets[1].count;

  // 24h mock 趋势(5 状态,24 个点,基于健康数稳定 + 严重数后段升)
  const trend = {
    h1: [0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 2, 1, 1, 2, 2, 1, 2, 2, 2, 1, 2, 2],
    h2: [2, 2, 2, 3, 2, 2, 3, 3, 2, 3, 3, 3, 2, 3, 3, 3, 3, 2, 3, 3, 3, 3, 3, 3],
    h3: [5, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
    h4: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    h5: [22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22],
  };

  return (
    <div
      style={{
        ...surfaceCardStyle,
        padding: '28px 32px',
        marginBottom: 16,
      }}
    >
      {/* 事故 banner:放到 hero 顶部,danger > 0 时显示(SRE 5 秒判断的关键信号) */}
      {danger > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            background: `${TOKENS.danger}10`,
            border: `1px solid ${TOKENS.danger}40`,
            borderRadius: 4,
            padding: '12px 16px',
            marginBottom: 20,
          }}
        >
          <BellOutlined
            style={{ fontSize: 18, color: TOKENS.danger, flexShrink: 0 }}
          />
          <div style={{ flex: 1, fontSize: 13, color: TOKENS.text }}>
            当前有 <b style={{ color: TOKENS.danger, fontSize: 15 }}>{danger}</b> 个服务处于严重 / 警告状态
            <span style={{ color: TOKENS.textTertiary, marginLeft: 8 }}>
              严重 {buckets[0].count} · 警告 {buckets[1].count}
            </span>
          </div>
          <Button
            type="primary"
            danger
            size="small"
            style={{ borderRadius: 4, fontWeight: 500 }}
            href={STORY_URLS.service}
          >
            立即处理 →
          </Button>
        </div>
      )}

      {/* 顶部行 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 24,
        }}
      >
        <Space size={10} align="center">
          <ThunderboltOutlined style={{ color: TOKENS.primary, fontSize: 16 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            全局健康度
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>
            汇总本 Group 内 {total} 个服务 · 健康分级
          </Text>
        </Space>
        <a
          href={STORY_URLS.service}
          style={{
            color: TOKENS.primary,
            fontSize: 13,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 2,
          }}
        >
          按健康严重度排序 <CaretRightOutlined />
        </a>
      </div>

      {/* 主区:左数字 + 分布,右 24h 趋势 */}
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 32, alignItems: 'center' }}>
        {/* 左:大数字 + 5 段分布条 + 5 chip */}
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6 }}>
            <span
              style={{
                fontSize: 56,
                fontWeight: 600,
                color: TOKENS.text,
                lineHeight: 1,
                letterSpacing: -1.5,
                ...tabularNumStyle,
              }}
            >
              {healthy}
            </span>
            <span style={{ fontSize: 16, color: TOKENS.textSecondary, fontWeight: 500 }}>
              个服务健康
            </span>
            <span style={{ fontSize: 13, color: TOKENS.textTertiary, ...tabularNumStyle }}>
              / {total} 总数
            </span>
          </div>

          {/* 5 段 stacked bar */}
          <div
            style={{
              display: 'flex',
              height: 6,
              borderRadius: 3,
              overflow: 'hidden',
              background: TOKENS.bg,
              marginBottom: 16,
            }}
          >
            {buckets.map((b) => {
              const widthPct = (b.count / total) * 100;
              if (widthPct === 0) return null;
              return (
                <div
                  key={b.level}
                  style={{
                    width: `${widthPct}%`,
                    background: HEALTH_COLORS[b.level],
                    transition: 'width 0.2s',
                  }}
                />
              );
            })}
          </div>

          {/* 5 chip */}
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {buckets.map((b) => (
              <div key={b.level} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 2,
                    background: HEALTH_COLORS[b.level],
                    display: 'inline-block',
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    fontSize: 13,
                    color: TOKENS.text,
                    fontWeight: 600,
                    ...tabularNumStyle,
                  }}
                >
                  {b.count}
                </span>
                <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{b.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 右:24h 趋势 + 图例 */}
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 8,
            }}
          >
            <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>近 24 小时趋势</span>
            <span style={{ fontSize: 11, color: TOKENS.textTertiary }}>5 状态曲线</span>
          </div>
          <MultiLineSparkline
            width={360}
            height={80}
            series={[
              { data: trend.h1, color: TOKENS.h1 },
              { data: trend.h5, color: TOKENS.h5 },
            ]}
          />
          <div
            style={{
              display: 'flex',
              gap: 10,
              flexWrap: 'wrap',
              marginTop: 6,
            }}
          >
            {buckets.map((b) => (
              <div key={b.level} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 1,
                    background: HEALTH_COLORS[b.level],
                    display: 'inline-block',
                  }}
                />
                <span style={{ fontSize: 11, color: TOKENS.textTertiary }}>{b.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

    </div>
  );
}

/* ============================================================
 * 活跃服务(按环境分组:prod / staging / dev)
 * 服务清单字段:服务名、版本、吞吐、错误率、P99 时延
 * ============================================================ */
const ACTIVE_SERVICES = {
  prod: [
    {
      name: 'payment-svc', version: 'v5.3.0', throughput: '342/s', errorRate: '20%', p99: '265ms',
      health: 1 as 1 | 2 | 3 | 4 | 5,
      errTrend: [2, 3, 4, 3, 5, 6, 7, 8, 9, 11, 12, 14, 15, 17, 18, 20],
    },
    {
      name: 'checkout-api', version: 'v3.1.3', throughput: '124/s', errorRate: '2.9%', p99: '358ms',
      health: 2 as 1 | 2 | 3 | 4 | 5,
      errTrend: [0.5, 0.8, 1.2, 1.5, 2.0, 2.3, 2.1, 1.8, 2.5, 2.6, 2.7, 2.9, 2.8, 2.9, 3.0, 2.9],
    },
    {
      name: 'api-gateway', version: 'v2.8.0', throughput: '2.1k/s', errorRate: '0.12%', p99: '473ms',
      health: 4 as 1 | 2 | 3 | 4 | 5,
      errTrend: [0.05, 0.08, 0.06, 0.09, 0.10, 0.08, 0.11, 0.10, 0.09, 0.11, 0.12, 0.10, 0.11, 0.12, 0.10, 0.12],
    },
    {
      name: 'catalog-api', version: 'v1.9.2', throughput: '1.4k/s', errorRate: '0.08%', p99: '64ms',
      health: 5 as 1 | 2 | 3 | 4 | 5,
      errTrend: [0.10, 0.09, 0.08, 0.09, 0.08, 0.07, 0.08, 0.08, 0.07, 0.08, 0.08, 0.07, 0.08, 0.08, 0.07, 0.08],
    },
    {
      name: 'auth-svc', version: 'v3.0.2', throughput: '1.2k/s', errorRate: '0.05%', p99: '38ms',
      health: 5 as 1 | 2 | 3 | 4 | 5,
      errTrend: [0.06, 0.05, 0.05, 0.04, 0.05, 0.06, 0.05, 0.04, 0.05, 0.05, 0.04, 0.05, 0.05, 0.05, 0.04, 0.05],
    },
  ],
  staging: [
    {
      name: 'payment-svc', version: 'v5.4.0-rc1', throughput: '46/s', errorRate: '0.3%', p99: '124ms',
      health: 5 as 1 | 2 | 3 | 4 | 5,
      errTrend: [0.4, 0.3, 0.3, 0.2, 0.3, 0.3, 0.4, 0.3, 0.2, 0.3, 0.3, 0.2, 0.3, 0.3, 0.3, 0.3],
    },
    {
      name: 'notification-worker', version: 'v1.3.0-beta', throughput: '12/s', errorRate: '0%', p99: '88ms',
      health: 5 as 1 | 2 | 3 | 4 | 5,
      errTrend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    },
  ],
  dev: [
    {
      name: 'payment-svc', version: 'v5.5.0-dev', throughput: '4/s', errorRate: '0%', p99: '92ms',
      health: 5 as 1 | 2 | 3 | 4 | 5,
      errTrend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    },
  ],
};

function HealthDot({ level }: { level: 1 | 2 | 3 | 4 | 5 }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
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
  // 默认按错误率降序排序,让 SRE 一眼看到 top 出问题服务
  const rows = [...ACTIVE_SERVICES[env]].sort(
    (a, b) => parseFloat(b.errorRate) - parseFloat(a.errorRate),
  );

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
          <AppstoreOutlined style={{ color: TOKENS.primary, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            活跃服务
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>近窗 15 分钟</Text>
        </Space>
        <a href={STORY_URLS.service} style={{ color: TOKENS.primary, fontSize: 13 }}>
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
        showHeader={false}
        style={{ marginTop: 4 }}
        columns={[
          {
            title: '服务',
            dataIndex: 'name',
            render: (v, r) => (
              <Space size={6} align="center">
                <HealthDot level={r.health} />
                <a style={{ color: TOKENS.text, fontWeight: 500, fontSize: 13 }}>{v}</a>
              </Space>
            ),
          },
          {
            title: '版本',
            dataIndex: 'version',
            width: 110,
            render: (v) => (
              <span style={{ fontFamily: 'ui-monospace, "SF Mono", monospace', fontSize: 11, color: TOKENS.textSecondary }}>
                {v}
              </span>
            ),
          },
          {
            title: '吞吐',
            dataIndex: 'throughput',
            width: 70,
            align: 'right' as const,
            render: (v) => (
              <span style={{ ...tabularNumStyle, fontSize: 13, color: TOKENS.text }}>{v}</span>
            ),
          },
          {
            title: '错误率',
            dataIndex: 'errorRate',
            width: 80,
            align: 'right' as const,
            render: (v, r) => {
              const n = parseFloat(v);
              const danger = !isNaN(n) && n >= 1;
              return (
                <Space size={6} align="center" style={{ justifyContent: 'flex-end' }}>
                  <span
                    style={{
                      ...tabularNumStyle,
                      fontSize: 13,
                      color: danger ? TOKENS.danger : TOKENS.text,
                      fontWeight: danger ? 600 : 400,
                    }}
                  >
                    {v}
                  </span>
                  <Sparkline data={r.errTrend} width={48} height={16} color={danger ? TOKENS.danger : TOKENS.success} kind="line" />
                </Space>
              );
            },
          },
          {
            title: 'P99',
            dataIndex: 'p99',
            width: 64,
            align: 'right' as const,
            render: (v, r) => {
              const num = parseInt(v, 10);
              const danger = r.health <= 2 && num > 200;
              return (
                <span
                  style={{
                    ...tabularNumStyle,
                    fontSize: 13,
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
    budgetTrend: [82, 78, 74, 70, 65, 58, 52, 48, 44, 40, 36, 32, 28],
  },
  {
    key: '2',
    service: 'checkout-api',
    slo: 'P99 < 400ms',
    budget: 56,
    burn: 4.1,
    state: 'risk' as const,
    evaluated: '5 分钟前',
    budgetTrend: [88, 84, 80, 76, 72, 68, 66, 64, 62, 60, 58, 57, 56],
  },
  {
    key: '3',
    service: 'api-gateway',
    slo: '可用性 ≥ 99.5%',
    budget: 82,
    burn: 1.3,
    state: 'ok' as const,
    evaluated: '5 分钟前',
    budgetTrend: [92, 90, 88, 87, 86, 85, 84, 84, 83, 83, 82, 82, 82],
  },
];

function SloBreachCard() {
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
          <FireOutlined style={{ color: TOKENS.warning, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            SLO 违约摘要
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>近窗 1 小时</Text>
        </Space>
        <a href={STORY_URLS.slo} style={{ color: TOKENS.primary, fontSize: 13 }}>
          进入 SLO →
        </a>
      </div>
      <Table
        size="small"
        rowKey="key"
        pagination={false}
        dataSource={SLO_BREACH}
        showHeader={false}
        columns={[
          {
            title: '服务',
            dataIndex: 'service',
            render: (v) => <a style={{ color: TOKENS.text, fontWeight: 500, fontSize: 13 }}>{v}</a>,
          },
          { title: 'SLO', dataIndex: 'slo', width: 140, render: (v) => <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{v}</span> },
          {
            title: '剩余预算',
            dataIndex: 'budget',
            width: 180,
            render: (v, r) => {
              const danger = v <= 30;
              const warn = v <= 60;
              const color = danger ? TOKENS.danger : warn ? TOKENS.warning : TOKENS.success;
              return (
                <Space size={8} align="center">
                  <div style={{ width: 80, height: 4, background: TOKENS.bg, borderRadius: 2, overflow: 'hidden', flexShrink: 0 }}>
                    <div style={{ width: `${v}%`, height: '100%', background: color }} />
                  </div>
                  <span
                    style={{
                      ...tabularNumStyle,
                      fontSize: 13,
                      color,
                      fontWeight: 600,
                      minWidth: 30,
                    }}
                  >
                    {v}%
                  </span>
                  <Sparkline data={r.budgetTrend} width={48} height={16} color={color} kind="line" />
                </Space>
              );
            },
          },
          {
            title: '燃尽率',
            dataIndex: 'burn',
            width: 60,
            align: 'right' as const,
            render: (v) => {
              const danger = v >= 5;
              const warn = v >= 2;
              return (
                <span
                  style={{
                    ...tabularNumStyle,
                    fontSize: 13,
                    color: danger ? TOKENS.danger : warn ? TOKENS.warning : TOKENS.text,
                    fontWeight: 600,
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
            width: 70,
            render: (v) => {
              const map: Record<string, { color: string; bg: string; label: string }> = {
                breach: { color: TOKENS.danger, bg: `${TOKENS.danger}10`, label: '违约' },
                risk: { color: TOKENS.warning, bg: `${TOKENS.warning}10`, label: '高风险' },
                ok: { color: TOKENS.success, bg: `${TOKENS.success}10`, label: '健康' },
              };
              const s = map[v] || map.ok;
              return (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    color: s.color,
                    background: s.bg,
                    padding: '2px 8px',
                    borderRadius: 3,
                    display: 'inline-block',
                  }}
                >
                  {s.label}
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
    state: '待分诊' as '待分诊' | '已分诊' | '已解决' | '已排除',
    countTrend: [2, 3, 5, 8, 12, 18, 25, 32, 45, 58, 78, 102, 142],
  },
  {
    key: '2',
    title: 'HTTP 502 from upstream checkout-api',
    service: 'checkout-api',
    firstSeen: '38 分钟前',
    count: 24,
    spiking: false,
    state: '已分诊' as '待分诊' | '已分诊' | '已解决' | '已排除',
    countTrend: [0, 0, 1, 2, 3, 5, 8, 10, 14, 17, 20, 22, 24],
  },
  {
    key: '3',
    title: '连接 Redis 超时 (read timeout 5s)',
    service: 'api-gateway',
    firstSeen: '1 小时前',
    count: 8,
    spiking: false,
    state: '已解决' as '待分诊' | '已分诊' | '已解决' | '已排除',
    regression: true,
    countTrend: [8, 8, 7, 6, 4, 2, 1, 0, 0, 0, 0, 0, 0],
  },
  {
    key: '4',
    title: '老版本遗留告警,经排查非生产路径',
    service: 'notification-worker',
    firstSeen: '3 小时前',
    count: 3,
    spiking: false,
    state: '已排除' as '待分诊' | '已分诊' | '已解决' | '已排除',
    countTrend: [3, 3, 3, 3, 3, 2, 1, 0, 0, 0, 0, 0, 0],
  },
];

const STATE_STYLE: Record<string, { color: string; bg: string }> = {
  待分诊: { color: TOKENS.danger, bg: `${TOKENS.danger}10` },
  已分诊: { color: TOKENS.primary, bg: `${TOKENS.primary}10` },
  已解决: { color: TOKENS.success, bg: `${TOKENS.success}10` },
  已排除: { color: TOKENS.textSecondary, bg: TOKENS.bg },
};

function RecentIssuesCard() {
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
          <BugOutlined style={{ color: TOKENS.danger, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            最近错误
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>近窗 1 小时</Text>
        </Space>
        <Space size={4}>
          <span
            style={{
              fontSize: 11,
              color: TOKENS.danger,
              background: `${TOKENS.danger}10`,
              padding: '2px 8px',
              borderRadius: 3,
            }}
          >
            激增 1
          </span>
          <span
            style={{
              fontSize: 11,
              color: TOKENS.warning,
              background: `${TOKENS.warning}10`,
              padding: '2px 8px',
              borderRadius: 3,
            }}
          >
            回归 1
          </span>
          <a href={STORY_URLS.explore} style={{ color: TOKENS.primary, fontSize: 13, marginLeft: 6 }}>
            进入错误 →
          </a>
        </Space>
      </div>
      <List
        size="small"
        dataSource={RECENT_ISSUES}
        split={false}
        renderItem={(it) => {
          const s = STATE_STYLE[it.state];
          return (
            <List.Item
              style={{
                padding: '12px 0',
                borderBottom: `1px solid ${TOKENS.border}`,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <span
                style={{
                  ...tabularNumStyle,
                  fontSize: 18,
                  fontWeight: 600,
                  color: it.state === '已解决' || it.state === '已排除' ? TOKENS.textSecondary : TOKENS.text,
                  minWidth: 44,
                  textAlign: 'right',
                }}
              >
                {it.count}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Space size={6} align="center" wrap>
                  {it.spiking && (
                    <span style={{ fontSize: 11, color: TOKENS.danger, fontWeight: 500 }}>激增</span>
                  )}
                  {it.regression && (
                    <span style={{ fontSize: 11, color: TOKENS.warning, fontWeight: 500 }}>回归</span>
                  )}
                  <a style={{ color: TOKENS.text, fontSize: 13, fontWeight: 500 }}>{it.title}</a>
                </Space>
                <div style={{ fontSize: 11, color: TOKENS.textTertiary, marginTop: 3 }}>
                  {it.service} · 首现 {it.firstSeen}
                </div>
              </div>
              <Sparkline data={it.countTrend} width={64} height={20} color={s.color} kind="area" />
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 500,
                  color: s.color,
                  background: s.bg,
                  padding: '2px 8px',
                  borderRadius: 3,
                  minWidth: 50,
                  textAlign: 'center',
                }}
              >
                {it.state}
              </span>
            </List.Item>
          );
        }}
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

// 7 天部署频次(bar sparkline,1-3 次/天)
const DEPLOY_FREQ = [0, 1, 0, 2, 1, 0, 3];

function RecentDeploysCard() {
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
          <RocketOutlined style={{ color: TOKENS.success, fontSize: 15 }} />
          <Title level={5} style={{ margin: 0, fontWeight: 600 }}>
            最近部署
          </Title>
          <Text style={{ fontSize: 12, color: TOKENS.textSecondary }}>近窗 7 天 · 按服务分组</Text>
        </Space>
        <Space size={8} align="center">
          <Text style={{ fontSize: 11, color: TOKENS.textTertiary }}>7d 频次</Text>
          <Sparkline data={DEPLOY_FREQ} width={56} height={20} color={TOKENS.success} kind="bar" />
          <a href={STORY_URLS.service} style={{ color: TOKENS.primary, fontSize: 13 }}>
            进入服务 →
          </a>
        </Space>
      </div>
      <Collapse
        defaultActiveKey={RECENT_DEPLOYS.map((g) => g.service)}
        ghost
        size="small"
        items={RECENT_DEPLOYS.map((grp) => ({
          key: grp.service,
          label: (
            <Space size={8} align="center">
              <Text strong style={{ fontSize: 13, color: TOKENS.text }}>{grp.service}</Text>
              <span
                style={{
                  fontSize: 11,
                  color: TOKENS.textSecondary,
                  background: TOKENS.bg,
                  padding: '1px 8px',
                  borderRadius: 3,
                }}
              >
                {grp.items.length} 次
              </span>
            </Space>
          ),
          children: (
            <div style={{ padding: '4px 0 8px 4px' }}>
              {grp.items.map((d, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 0',
                    borderBottom: idx < grp.items.length - 1 ? `1px solid ${TOKENS.border}` : 'none',
                  }}
                >
                  <Space size={10} align="center">
                    <span
                      style={{
                        fontFamily: 'ui-monospace, "SF Mono", monospace',
                        fontSize: 12,
                        color: d.source === 'CI' ? TOKENS.primary : TOKENS.textSecondary,
                        background: d.source === 'CI' ? TOKENS.primarySoft : TOKENS.bg,
                        padding: '2px 6px',
                        borderRadius: 3,
                      }}
                    >
                      {d.version}
                    </span>
                    <span style={{ fontSize: 12, color: TOKENS.textSecondary }}>{d.time}</span>
                    <span style={{ fontSize: 11, color: TOKENS.textTertiary }}>
                      {d.source === 'CI' ? 'CI 上报' : '推断'}
                    </span>
                  </Space>
                  <span style={{ fontSize: 12, color: TOKENS.textTertiary }}>{d.by}</span>
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
        前往集成菜单完成首次接入,数分钟内即可在首页看到全局健康度与活跃服务。
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
 * 布局:TopMenuBar + HomeToolbar + Hero GlobalHealthCard(全宽)
 *       + 2x2 网格(活跃服务 / SLO 违约 / 最近错误 / 最近部署)
 * ============================================================ */
function HomeDashboard() {
  const [empty, setEmpty] = useState(false);
  return (
    <div style={shellStyle}>
      <TopMenuBar active="home" />
      <Content style={{ padding: '24px 32px 40px' }}>
        <HomeToolbar onRefresh={() => undefined} />
        {empty ? (
          <HomeEmptyState />
        ) : (
          <>
            <GlobalHealthCard />
            <Row gutter={[20, 20]}>
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
