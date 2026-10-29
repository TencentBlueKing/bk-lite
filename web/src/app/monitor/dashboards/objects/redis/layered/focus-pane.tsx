'use client';

import React from 'react';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import {
  ProDashLoading,
  ProFocusCard,
  ProInfoHint,
  ProSection,
  ThinTimeSeries,
  proChromeClass
} from '../../host/layered/pro-chrome';
import FocusShortcutTitle from '../../host/layered/focus-shortcut-title';
import { describeFocusAxis, formatFocusHeadline, seriesSampleValues } from '../../host/layered/focus-axis';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import type { MetricUnit } from '../../../shared/types';
import { REDIS_PALETTE } from '../config';
import hostLayered from '../../host/layered/layered.module.scss';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisChartPoints, redisLatest, type RedisMetricMap } from './series';

export type RedisTopicTab = 'memory' | 'cache' | 'clients' | 'throughput';

interface FocusCardSpec {
  metric: string;
  labelKey: RedisCategoryCopyKey;
  unit: MetricUnit;
  color: string;
  ctaKey: RedisCategoryCopyKey;
  tab: RedisTopicTab;
}

/** 未命中用 config 里的 redis_keyspace_misses_rate，其 query 为 rate(redis_keyspace_misses[window])。 */
const FOCUS_CARDS: readonly FocusCardSpec[] = [
  {
    metric: 'redis_keyspace_misses_rate',
    labelKey: 'focusMiss',
    unit: 'cps',
    color: REDIS_PALETTE.rose,
    ctaKey: 'viewHitTrend',
    tab: 'cache'
  },
  {
    metric: 'redis_mem_fragmentation_ratio',
    labelKey: 'focusFrag',
    unit: 'none',
    color: REDIS_PALETTE.amber,
    ctaKey: 'viewMemory',
    tab: 'memory'
  },
  {
    metric: 'redis_blocked_clients',
    labelKey: 'focusBlocked',
    unit: 'counts',
    color: REDIS_PALETTE.orange,
    ctaKey: 'viewClients',
    tab: 'clients'
  }
];

const FOCUS_STEPS: ReadonlyArray<{ title: RedisCategoryCopyKey; detail: RedisCategoryCopyKey }> = [
  { title: 'focusStepCards', detail: 'focusStepCardsHint' },
  { title: 'focusStepPerf', detail: 'focusStepPerfHint' },
  { title: 'focusStepMemory', detail: 'focusStepMemoryHint' },
  { title: 'focusStepClients', detail: 'focusStepClientsHint' }
];

function FocusStepFlow({ steps }: { steps: readonly { title: string; detail: string }[] }) {
  return (
    <div className="flex max-w-[500px] flex-col gap-2">
      <div className="flex flex-wrap items-center">
        {steps.map((step, index) => (
          <React.Fragment key={step.title}>
            {index > 0 ? (
              <span aria-hidden className="mx-1 text-[12px] leading-none text-[#d9d9d9]">→</span>
            ) : null}
            <span className="inline-flex h-6 items-center rounded-[4px] border border-[#f0f0f0] bg-[#f5f5f5] px-2 text-[12px] leading-none text-[#595959]">
              {step.title}
            </span>
          </React.Fragment>
        ))}
      </div>
      <div className="flex flex-col gap-1">
        {steps.map((step) => (
          <p key={step.title} className="m-0 text-[12px] leading-[18px]">
            <span className="font-semibold text-[#595959]">{step.title}</span>
            <span className="text-[#8c8c8c]"> {step.detail}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

export default function FocusPane({
  metricMap,
  pending,
  onOpen
}: {
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
  onOpen: (tab: RedisTopicTab) => void;
}) {
  const { t } = useDashboardText();
  const text = (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
  const proTime = useProTimeWindow();
  const window = proTime?.window ?? null;
  const steps = FOCUS_STEPS.map((step) => ({
    title: text(step.title),
    detail: text(step.detail)
  }));

  return (
    <div data-redis-pane="focus" className="min-w-0">
      <ProSection
        title={text('tabFocus')}
        hint={(
          <ProInfoHint
            kind="redis-focus"
            label={steps.map((step) => `${step.title} ${step.detail}`).join(' → ')}
            content={<FocusStepFlow steps={steps} />}
          />
        )}
      >
        <div className={`${proChromeClass.shortcutGrid} ${hostLayered.shortcutGrid3}`}>
          {FOCUS_CARDS.map((card) => {
            const isFrag = card.metric === 'redis_mem_fragmentation_ratio';
            const plotted = redisChartPoints(
              metricMap,
              [{ name: card.metric, label: text(card.labelKey) }],
              window
            );
            const axis = describeFocusAxis(card.unit, seriesSampleValues(plotted));
            const latest = redisLatest(metricMap, card.metric);
            const loading = pending.has(card.metric) && plotted.length === 0 && latest == null;
            const unitLabel = isFrag ? text('fragTimes') : axis.unitLabel;
            return (
              <ProFocusCard key={card.metric}>
                <div
                  className={proChromeClass.shortcutCopy}
                  data-redis-focus={card.metric}
                  data-redis-state={loading ? 'loading' : latest == null ? 'empty' : 'value'}
                >
                  <FocusShortcutTitle
                    label={text(card.labelKey)}
                    unit={unitLabel}
                    hint={isFrag ? (
                      <ProInfoHint kind="redis-focus-frag" text={text('fragIdeal')} />
                    ) : undefined}
                  />
                  {loading ? (
                    <ProDashLoading size="small" />
                  ) : latest == null ? (
                    <div className="flex flex-col gap-1" data-redis-empty="reading">
                      <div className="text-[14px] font-semibold leading-5 text-[var(--color-text-1)]">
                        {text('readingEmpty')}
                      </div>
                      <p className="m-0 text-[12px] leading-5 text-[var(--color-text-2)]">
                        {text('readingEmptyTip')}
                      </p>
                    </div>
                  ) : (
                    <div className={proChromeClass.shortcutValue} style={{ color: card.color }}>
                      {isFrag ? latest.toFixed(2) : formatFocusHeadline(axis, latest)}
                    </div>
                  )}
                  <button type="button" className={proChromeClass.jumpBtn} onClick={() => onOpen(card.tab)}>
                    {text(card.ctaKey)}
                  </button>
                </div>
                {plotted.length > 0 ? (
                  <ThinTimeSeries
                    bare
                    numericAxis
                    className={proChromeClass.focusChart}
                    title=""
                    unit={card.unit}
                    data={plotted}
                    legends={[{ label: text(card.labelKey), color: card.color }]}
                  />
                ) : (
                  <div className={proChromeClass.focusChart} />
                )}
              </ProFocusCard>
            );
          })}
        </div>
      </ProSection>
    </div>
  );
}
