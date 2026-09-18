'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Descriptions, message as antdMessage, Segmented, Select, Spin, Table, Tag } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import CompactEmptyState from '@/components/compact-empty-state';
import useLogEventApi from '@/app/log/api/event';
import {
  AlertInfoEvidence,
  AlertSnapshotItem,
  formatClueTimestamp,
  formatPeriod,
  FrozenQueryClue,
  hasFrozenQueryClue,
  hasSnapshotRawData,
  historicalAlertInfo,
  parseAlertCondition,
  parseRawLogData,
  RawLogTableRow,
} from './alertRawLogEvidence';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface AlertRawLogWidgetProps {
  logAlertId: string;
}

interface AlertSnapshotsPayload {
  alert_info?: AlertInfoEvidence;
  snapshots?: AlertSnapshotItem[];
}

function renderLogGroups(logGroups: unknown) {
  if (!logGroups) return '--';
  if (Array.isArray(logGroups)) {
    if (!logGroups.length) return '--';
    return (
      <div className="flex flex-wrap gap-1">
        {logGroups.map((group, idx) => (
          <Tag key={idx} className="m-0 text-xs">
            {String(group)}
          </Tag>
        ))}
      </div>
    );
  }
  if (typeof logGroups === 'string' && logGroups.trim()) {
    return <Tag className="m-0 text-xs">{logGroups.trim()}</Tag>;
  }
  return '--';
}

function formatAlertType(
  alertType: unknown,
  t: (key: string, defaultVal?: string) => string,
) {
  if (alertType === 'keyword') {
    return (
      <Tag color="blue" className="m-0 text-xs">
        {t('log.event.keywordAlert')}
      </Tag>
    );
  }
  if (alertType === 'aggregate') {
    return (
      <Tag color="purple" className="m-0 text-xs">
        {t('log.event.aggregationAlert')}
      </Tag>
    );
  }
  return alertType ? <Tag className="m-0 text-xs">{String(alertType)}</Tag> : '--';
}

const QueryClueBlock = ({
  clue,
  convertToLocalizedTime,
}: {
  clue: FrozenQueryClue | null | undefined;
  convertToLocalizedTime: (iso: string) => string;
}) => {
  const { t } = useTranslation();
  if (!hasFrozenQueryClue(clue)) {
    return (
      <CompactEmptyState description={t('log.event.queryClueUnavailable')} />
    );
  }

  const windowText =
    clue.window_start != null && clue.window_end != null
      ? `${formatClueTimestamp(clue.window_start, convertToLocalizedTime)} ~ ${formatClueTimestamp(clue.window_end, convertToLocalizedTime)}`
      : clue.window_start != null || clue.window_end != null
        ? formatClueTimestamp(clue.window_start || clue.window_end, convertToLocalizedTime)
        : '--';

  const conditionParsed = parseAlertCondition(
    clue.alert_condition,
    (clue as Record<string, unknown>).query,
  );

  const clueDescriptionsStyles = {
    label: {
      minWidth: '72px',
      whiteSpace: 'nowrap' as const,
      fontSize: '12px',
      lineHeight: '20px',
      color: 'var(--color-text-3)',
    },
    content: {
      fontSize: '12px',
      lineHeight: '20px',
    },
  };

  return (
    <div className="flex flex-col gap-1">
      <Descriptions
        column={{ xs: 1, sm: 2, lg: 3 }}
        size="small"
        className="text-xs [&_.ant-descriptions-item-container]:items-center"
        styles={clueDescriptionsStyles}
      >
        <Descriptions.Item label={t('log.event.strategyName')}>
          <span className="font-medium text-[var(--color-text-1)]">
            {clue.policy_name || '--'}
          </span>
        </Descriptions.Item>
        <Descriptions.Item label={t('log.integration.collectType')}>
          {clue.collect_type_name || clue.collect_type_id ? (
            <Tag className="m-0 text-xs">
              {String(clue.collect_type_name || clue.collect_type_id)}
            </Tag>
          ) : (
            '--'
          )}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.alertType')}>
          {formatAlertType(clue.alert_type, t)}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.integration.logGroup')}>
          {renderLogGroups(clue.log_groups)}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.period')}>
          {formatPeriod(clue.period, t)}
        </Descriptions.Item>
      </Descriptions>

      <Descriptions
        column={1}
        size="small"
        className="text-xs"
        styles={clueDescriptionsStyles}
      >
        <Descriptions.Item
          label={t('log.event.queryWindow')}
          className="[&_.ant-descriptions-item-container]:items-center"
        >
          <span className="font-mono text-xs leading-5 text-[var(--color-text-2)]">
            {windowText}
          </span>
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.queryCriteria')}>
          {conditionParsed ? (
            <div className="flex w-full flex-col gap-1.5 rounded border border-[var(--color-border)] bg-[var(--color-fill-1)] p-2 text-xs">
              {conditionParsed.query && (
                <div className="flex items-start gap-1.5">
                  <span className="shrink-0 font-medium text-[var(--color-text-3)]">
                    {t('log.event.searchQuery')}:
                  </span>
                  <code className="break-all font-mono text-xs font-semibold text-[var(--color-text-1)]">
                    {conditionParsed.query}
                  </code>
                </div>
              )}
              {conditionParsed.conditions && conditionParsed.conditions.length > 0 && (
                <div className="flex items-start gap-1.5">
                  <span className="shrink-0 font-medium text-[var(--color-text-3)]">
                    {t('log.event.filterRule')}:
                  </span>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {conditionParsed.conditions.map((c, i) => (
                      <React.Fragment key={i}>
                        {i > 0 && (
                          <span className="text-[10px] font-semibold text-[var(--color-text-3)]">
                            {conditionParsed.ruleMode || 'AND'}
                          </span>
                        )}
                        <span className="inline-flex items-center rounded border border-[var(--color-border)] bg-[var(--color-bg-1)] px-1.5 py-0.5 font-mono text-xs">
                          <span className="text-[var(--color-text-2)]">{c.field}</span>
                          <span className="mx-1 font-semibold text-[var(--color-primary)]">
                            {c.op}
                          </span>
                          <span className="text-[var(--color-text-1)]">{c.value}</span>
                        </span>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              )}
              {conditionParsed.groupBy && conditionParsed.groupBy.length > 0 && (
                <div className="flex items-start gap-1.5">
                  <span className="shrink-0 font-medium text-[var(--color-text-3)]">
                    {t('log.event.groupBy')}:
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {conditionParsed.groupBy.map((groupField, i) => (
                      <Tag key={i} className="m-0 text-xs">
                        {groupField}
                      </Tag>
                    ))}
                  </div>
                </div>
              )}
              {conditionParsed.rawText && (
                <code className="break-all font-mono text-xs text-[var(--color-text-2)]">
                  {conditionParsed.rawText}
                </code>
              )}
            </div>
          ) : (
            '--'
          )}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );
};

const AlertRawLogWidget = ({ logAlertId }: AlertRawLogWidgetProps) => {
  const { t } = useTranslation();
  const tRef = useRef(t);
  tRef.current = t;

  const { convertToLocalizedTime } = useLocalizedTime();
  const { getAlertSnapshots } = useLogEventApi();
  const getAlertSnapshotsRef = useRef(getAlertSnapshots);
  getAlertSnapshotsRef.current = getAlertSnapshots;

  const [payload, setPayload] = useState<AlertSnapshotsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const [selectedSnapshotIndex, setSelectedSnapshotIndex] = useState<number>(0);
  const [viewMode, setViewMode] = useState<'table' | 'json'>('table');

  useEffect(() => {
    let cancelled = false;
    const alertId = String(logAlertId || '').trim();
    if (!alertId) {
      setLoading(false);
      setError(tRef.current('common.loadFailed'));
      setPayload(null);
      return;
    }
    setLoading(true);
    setError(null);
    setPayload(null);
    getAlertSnapshotsRef
      .current(alertId)
      .then((data: AlertSnapshotsPayload) => {
        if (!cancelled) {
          const loadedSnapshots = data?.snapshots || [];
          setPayload(data || { snapshots: [] });
          // Default to latest snapshot (the last element)
          setSelectedSnapshotIndex(
            loadedSnapshots.length > 0 ? loadedSnapshots.length - 1 : 0,
          );
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              tRef.current,
              'log.event.publicWidgetNotFound',
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [logAlertId, reloadKey]);

  const snapshots = payload?.snapshots || [];
  const alertInfo = historicalAlertInfo(payload?.alert_info);

  const safeIndex =
    selectedSnapshotIndex >= 0 && selectedSnapshotIndex < snapshots.length
      ? selectedSnapshotIndex
      : Math.max(0, snapshots.length - 1);

  const currentSnapshot = snapshots[safeIndex];

  const parsedData = useMemo(() => {
    if (!currentSnapshot || !hasSnapshotRawData(currentSnapshot.raw_data)) {
      return { isTabular: false, isAggregate: false, rows: [], columns: [] };
    }
    return parseRawLogData(currentSnapshot.raw_data);
  }, [currentSnapshot]);

  const isCurrentTabular = parsedData.isTabular;
  const effectiveViewMode = isCurrentTabular ? viewMode : 'json';

  const tableColumns = useMemo(() => {
    if (!isCurrentTabular) return [];
    if (parsedData.isAggregate) {
      return parsedData.columns.map((col) => ({
        title: col.title,
        dataIndex: col.dataIndex,
        key: col.key,
        render: (val: unknown) => (
          <span className="font-mono text-xs text-[var(--color-text-1)]">
            {val != null ? String(val) : '--'}
          </span>
        ),
      }));
    }
    const cols = [];
    if (parsedData.timeKey) {
      cols.push({
        title: t('log.event.tableTime'),
        dataIndex: parsedData.timeKey,
        key: parsedData.timeKey,
        width: 175,
        render: (val: unknown) => (
          <span className="whitespace-nowrap font-mono text-xs text-[var(--color-text-2)]">
            {formatClueTimestamp(val, convertToLocalizedTime)}
          </span>
        ),
      });
    }
    if (parsedData.messageKey) {
      cols.push({
        title: t('log.event.tableMessage'),
        dataIndex: parsedData.messageKey,
        key: parsedData.messageKey,
        render: (val: unknown) => (
          <div className="break-all whitespace-pre-wrap font-mono text-xs leading-relaxed text-[var(--color-text-1)]">
            {val != null ? String(val) : '--'}
          </div>
        ),
      });
    }
    return cols;
  }, [convertToLocalizedTime, isCurrentTabular, parsedData, t]);

  const handleCopy = () => {
    if (!currentSnapshot || !hasSnapshotRawData(currentSnapshot.raw_data)) return;
    const content =
      typeof currentSnapshot.raw_data === 'string'
        ? currentSnapshot.raw_data
        : JSON.stringify(currentSnapshot.raw_data, null, 2);
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard
        .writeText(content)
        .then(() => {
          antdMessage.success(t('common.copySuccess'));
        })
        .catch(() => {
          antdMessage.warning(t('common.copyFailed'));
        });
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }

  if (!snapshots.length) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <CompactEmptyState description={t('common.noData')} />
      </div>
    );
  }

  const snapshotOptions = snapshots
    .map((item, index) => {
      const isLatest = index === snapshots.length - 1;
      const timeStr = item.event_time || item.snapshot_time;
      const formatted = timeStr
        ? formatClueTimestamp(timeStr, convertToLocalizedTime)
        : '';
      return {
        label: `#${index + 1}${isLatest ? ` (${t('log.event.snapshotLatest')})` : ''} · ${formatted || '--'}`,
        value: index,
      };
    })
    .reverse();

  return (
    <div className="flex min-h-[280px] min-w-0 flex-col gap-3">
      {/* 顶栏：轻量证据概览与多快照切换 */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3.5 py-2 text-xs shadow-sm">
        <div className="flex flex-wrap items-center gap-3 text-[var(--color-text-2)]">
          {alertInfo.source_id && (
            <span>
              <span className="text-[var(--color-text-3)]">{t('log.source')}: </span>
              <span className="font-mono text-[var(--color-text-1)]">
                {alertInfo.source_id}
              </span>
            </span>
          )}
          <span>
            <span className="text-[var(--color-text-3)]">
              {t('log.event.snapshotCount')}:{' '}
            </span>
            <span className="font-medium text-[var(--color-text-1)]">
              {snapshots.length}
            </span>
          </span>
        </div>

        {snapshots.length > 1 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-[var(--color-text-3)]">
              {t('log.event.snapshotVersion')}:
            </span>
            <Select
              size="small"
              value={safeIndex}
              onChange={setSelectedSnapshotIndex}
              className="min-w-[220px]"
              popupMatchSelectWidth={false}
              options={snapshotOptions}
            />
            {safeIndex !== snapshots.length - 1 && (
              <Button
                size="small"
                type="link"
                className="!p-0 text-xs"
                onClick={() => setSelectedSnapshotIndex(snapshots.length - 1)}
              >
                {t('log.event.backToLatest')}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* 发生时查询线索 */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
        <div className="mb-2 flex items-center justify-between">
          <span className="font-medium text-[var(--color-text-1)]">
            {t('log.event.queryClue')}
          </span>
          <span className="text-xs text-[var(--color-text-3)]">
            {t('log.event.hitTime')}:{' '}
            {formatClueTimestamp(
              currentSnapshot?.event_time || currentSnapshot?.snapshot_time,
              convertToLocalizedTime,
            )}
          </span>
        </div>
        <QueryClueBlock
          clue={currentSnapshot?.query_clue}
          convertToLocalizedTime={convertToLocalizedTime}
        />
      </div>

      {/* 原始日志 */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3.5 shadow-sm">
        <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium text-[var(--color-text-1)]">
            {t('log.event.originalLog')}
          </span>
          <div className="flex items-center gap-2">
            {isCurrentTabular && (
              <Segmented
                size="small"
                value={effectiveViewMode}
                onChange={(val) => setViewMode(val as 'table' | 'json')}
                options={[
                  { label: t('log.event.tableView'), value: 'table' },
                  { label: t('log.event.jsonView'), value: 'json' },
                ]}
              />
            )}
            {hasSnapshotRawData(currentSnapshot?.raw_data) && (
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={handleCopy}
              >
                {t('common.copy')}
              </Button>
            )}
          </div>
        </div>

        {hasSnapshotRawData(currentSnapshot?.raw_data) ? (
          effectiveViewMode === 'table' && isCurrentTabular ? (
            <Table
              rowKey="__id"
              size="small"
              dataSource={parsedData.rows}
              columns={tableColumns}
              pagination={
                parsedData.rows.length > 5
                  ? {
                    pageSize: 5,
                    size: 'small',
                    showSizeChanger: false,
                    className: '!mb-0',
                  }
                  : false
              }
              scroll={{ x: 'max-content' }}
              className="overflow-hidden rounded-md border border-[var(--color-border)]"
              expandable={
                !parsedData.isAggregate
                  ? {
                    expandedRowRender: (record: RawLogTableRow) => {
                      const entries = Object.entries(record).filter(
                        ([k]) =>
                          k !== '__id' &&
                            k !== parsedData.timeKey &&
                            k !== parsedData.messageKey,
                      );
                      return (
                          <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-2)] p-2.5">
                            <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-tight text-[var(--color-text-2)]">
                              {JSON.stringify(Object.fromEntries(entries), null, 2)}
                            </pre>
                          </div>
                      );
                    },
                    rowExpandable: (record: RawLogTableRow) => {
                      return Object.keys(record).some(
                        (k) =>
                          k !== '__id' &&
                            k !== parsedData.timeKey &&
                            k !== parsedData.messageKey,
                      );
                    },
                  }
                  : undefined
              }
            />
          ) : (
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <pre className="m-0 max-h-[360px] overflow-auto whitespace-pre-wrap break-all font-mono text-[12px] leading-relaxed text-[var(--color-text-1)]">
                {typeof currentSnapshot.raw_data === 'string'
                  ? currentSnapshot.raw_data
                  : JSON.stringify(currentSnapshot.raw_data, null, 2)}
              </pre>
            </div>
          )
        ) : (
          <CompactEmptyState description={t('log.event.rawDataUnavailable')} />
        )}
      </div>
    </div>
  );
};

export default AlertRawLogWidget;
