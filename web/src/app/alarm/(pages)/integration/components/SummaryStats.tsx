'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { SourceItem } from '@/app/alarm/types/integration';
import { STATUS_TEXT, HEALTH_BG, SOURCE_LOGO_FALLBACK } from '@/app/alarm/constants/colors';

interface StatCardProps {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value: string | number;
  unit?: string;
  subtitle?: string;
  subtitleColor?: string;
}

const KPI_WASH =
  'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 1.5%, var(--color-bg)) 0%, var(--color-bg) 32%)';

const StatCard: React.FC<StatCardProps> = ({ icon, iconBg, label, value, unit, subtitle, subtitleColor }) => (
  <div
    className="flex flex-1 items-center gap-4 rounded-lg border border-[var(--color-border-1)] p-3 shadow-[0_1px_3px_rgba(0,0,0,0.03)] sm:px-3.5 sm:py-3"
    style={{ background: KPI_WASH }}
  >
    <div
      className="grid h-[46px] w-[46px] shrink-0 place-items-center rounded-full text-[22px]"
      style={{ background: iconBg }}
    >
      {icon}
    </div>
    <div>
      <div className="mb-1 text-xs font-medium text-[var(--color-text-3)]">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-xl font-bold leading-none text-[var(--color-text-1)] tabular-nums sm:text-2xl">{value}</span>
        {unit && <span className="text-[13px] font-medium text-[var(--color-text-3)]">{unit}</span>}
      </div>
      {subtitle && (
        <div className="mt-[3px] text-[11px]" style={{ color: subtitleColor || 'var(--color-text-3)' }}>
          {subtitle}
        </div>
      )}
    </div>
  </div>
);

interface DailyEventStats {
  today_count: number;
  yesterday_count: number;
}

interface SummaryStatsProps {
  sources: SourceItem[];
  dailyStats?: DailyEventStats | null;
}

function formatTrend(today: number, yesterday: number, t: (key: string) => string): { text: string; color: string } {
  if (yesterday === 0) {
    return { text: t('integration.statComparedYesterday'), color: 'var(--color-text-3)' };
  }
  const diff = today - yesterday;
  const pct = ((diff / yesterday) * 100).toFixed(1);
  if (diff > 0) {
    return { text: `↑ ${pct}%`, color: STATUS_TEXT.TREND_UP_RED };
  }
  if (diff < 0) {
    return { text: `↓ ${Math.abs(parseFloat(pct))}%`, color: STATUS_TEXT.TREND_DOWN_GREEN };
  }
  return { text: '— 0%', color: 'var(--color-text-3)' };
}

const SummaryStats: React.FC<SummaryStatsProps> = ({ sources, dailyStats }) => {
  const { t } = useTranslation();

  const total = sources.length;
  const H3 = 3 * 60 * 60 * 1000;
  const now = Date.now();
  const activeSources = sources.filter(s => {
    if (!s.last_event_time) return false;
    return now - new Date(s.last_event_time).getTime() < H3;
  }).length;

  const todayCount = dailyStats?.today_count ?? 0;
  const yesterdayCount = dailyStats?.yesterday_count ?? 0;
  const trend = dailyStats
    ? formatTrend(todayCount, yesterdayCount, t)
    : { text: t('integration.statComparedYesterday'), color: 'var(--color-text-3)' };

  return (
    <div className="mb-5 flex gap-3">
      <StatCard
        icon={
          <svg viewBox="0 0 24 24" width="24" height="24">
            <path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z" fill={SOURCE_LOGO_FALLBACK} />
          </svg>
        }
        iconBg={HEALTH_BG.BLUE_BG}
        label={t('integration.statTotal')}
        value={total}
        unit={t('integration.statUnitSources')}
      />
      <StatCard
        icon={
          <svg viewBox="0 0 24 24" width="24" height="24">
            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill={STATUS_TEXT.TREND_DOWN_GREEN} />
          </svg>
        }
        iconBg={HEALTH_BG.GREEN_BG}
        label={t('integration.statTodayEvents')}
        value={todayCount.toLocaleString()}
        unit={t('integration.statUnitEvents')}
        subtitle={trend.text}
        subtitleColor={trend.color}
      />
      <StatCard
        icon={
          <svg viewBox="0 0 24 24" width="24" height="24">
            <circle cx="12" cy="12" r="8" fill="none" stroke={STATUS_TEXT.WARN_ORANGE} strokeWidth="2" />
            <path d="M12 8v4l3 3" fill="none" stroke={STATUS_TEXT.WARN_ORANGE} strokeWidth="2" strokeLinecap="round" />
          </svg>
        }
        iconBg={HEALTH_BG.ORANGE_BG}
        label={t('integration.statActive')}
        value={activeSources}
        unit={t('integration.statUnitSources')}
        subtitle={t('integration.statActiveHint')}
      />
    </div>
  );
};

export default SummaryStats;
