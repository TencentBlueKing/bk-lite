'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RightOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import styles from './index.module.scss';
import { ChangeRecordScenarioTag } from './ChangeRecordScenarioTag';
import {
  SCENARIO_COLORS,
  groupChangeRecordsByMonth,
} from './changeRecordView';
import type { ChangeRecord } from './changeRecordTypes';

const MONTH_PREVIEW = 6;

export function ChangeRecordTimeline({
  records,
  selectedId,
  onSelect,
  scenarioLabel,
  typeLabel,
  showModelName,
}: {
  records: ChangeRecord[];
  selectedId: number | string | null;
  onSelect: (id: number | string) => void;
  scenarioLabel: (key: string) => string;
  typeLabel: (key: string) => string;
  showModelName: (id: string) => string;
}) {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const grouped = useMemo(() => groupChangeRecordsByMonth(records), [records]);
  const [activeMonth, setActiveMonth] = useState<string | null>(null);
  const [expandedMonths, setExpandedMonths] = useState<Record<string, boolean>>(
    {},
  );
  const monthRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const timelineListRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (grouped.length && !activeMonth) {
      setActiveMonth(grouped[0].month);
    }
  }, [grouped, activeMonth]);

  const handleMonthClick = useCallback((month: string) => {
    setActiveMonth(month);
    const el = monthRefs.current[month];
    const container = timelineListRef.current;
    if (el && container) {
      const top = el.offsetTop - container.offsetTop;
      container.scrollTo({ top, behavior: 'smooth' });
    }
  }, []);

  return (
    <div className={styles.timelineBody}>
      <div className={styles.monthNav}>
        {grouped.map((group) => (
          <div
            key={group.month}
            className={`${styles.monthItem} ${
              activeMonth === group.month ? styles.monthActive : ''
            }`}
            onClick={() => handleMonthClick(group.month)}
          >
            <span>{group.month}</span>
            <span className={styles.monthBadge}>{group.count}</span>
          </div>
        ))}
      </div>

      <div className={styles.timelineList} ref={timelineListRef}>
        {grouped.length === 0 && (
          <CompactEmptyState
            className="mt-[60px]"
            description={t('common.noData')}
          />
        )}
        {grouped.map((group) => {
          const expanded = expandedMonths[group.month];
          const visible = expanded ? group.list : group.list.slice(0, MONTH_PREVIEW);
          return (
            <div
              key={group.month}
              className={styles.monthGroup}
              ref={(el) => {
                monthRefs.current[group.month] = el;
              }}
            >
              <div className={styles.monthHeading}>{group.month}</div>
              {visible.map((item) => {
                const colors =
                  SCENARIO_COLORS[item.scenario] ||
                  SCENARIO_COLORS.ordinary_attribute_change;
                const isSelected = String(selectedId) === String(item.id);
                return (
                  <div
                    key={String(item.id)}
                    className={`${styles.timelineItem} ${
                      isSelected ? styles.selected : ''
                    }`}
                    onClick={() => onSelect(item.id)}
                  >
                    <div
                      className={styles.timelineDot}
                      style={{ background: colors.dot, borderColor: colors.bg }}
                    />
                    <div className={styles.timelineContent}>
                      <div className={styles.timelineMeta}>
                        <span>
                          ●{' '}
                          {item.created_at
                            ? convertToLocalizedTime(item.created_at, 'MM-DD HH:mm')
                            : ''}
                        </span>
                        <ChangeRecordScenarioTag
                          scenario={item.scenario}
                          label={scenarioLabel(item.scenario)}
                        />
                      </div>
                      <div className={styles.timelineTitle}>
                        {item.message ||
                          `${typeLabel(item.type)}${
                            item.model_object || showModelName(item.model_id)
                          }`}
                      </div>
                      <div className={styles.timelineOperator}>
                        {t('Model.changeRecord.operatorLabel')}：
                        {item.operator || '--'}
                      </div>
                    </div>
                    <div className="shrink-0 pt-4 text-[var(--color-text-4)]">
                      <RightOutlined className="text-xs" />
                    </div>
                  </div>
                );
              })}
              {group.list.length > MONTH_PREVIEW && !expanded && (
                <div
                  className={styles.expandAll}
                  onClick={() =>
                    setExpandedMonths((prev) => ({ ...prev, [group.month]: true }))
                  }
                >
                  {t('Model.changeRecord.expandAll')} ({group.list.length}) ▾
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
