'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Descriptions, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import useLogEventApi from '@/app/log/api/event';
import {
  AlertInfoEvidence,
  AlertSnapshotItem,
  FrozenQueryClue,
  hasFrozenQueryClue,
  hasSnapshotRawData,
  historicalAlertInfo,
} from './alertRawLogEvidence';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface AlertRawLogWidgetProps {
  logAlertId: string;
}

interface AlertSnapshotsPayload {
  alert_info?: AlertInfoEvidence;
  snapshots?: AlertSnapshotItem[];
}

function formatClueValue(value: unknown): string {
  if (value == null || value === '') return '--';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return '--';
  }
}

const QueryClueBlock = ({ clue }: { clue: FrozenQueryClue | null | undefined }) => {
  const { t } = useTranslation();
  if (!hasFrozenQueryClue(clue)) {
    return (
      <CompactEmptyState description={t('log.event.queryClueUnavailable')} />
    );
  }
  const windowText =
    clue.window_start != null && clue.window_end != null
      ? `${clue.window_start} – ${clue.window_end}`
      : '--';
  return (
    <Descriptions column={1} size="small">
      <Descriptions.Item label={t('log.event.strategyName')}>
        {formatClueValue(clue.policy_name)}
      </Descriptions.Item>
      <Descriptions.Item label={t('log.integration.collectType')}>
        {formatClueValue(clue.collect_type_name || clue.collect_type_id)}
      </Descriptions.Item>
      <Descriptions.Item label={t('log.integration.logGroup')}>
        {formatClueValue(clue.log_groups)}
      </Descriptions.Item>
      <Descriptions.Item label={t('log.event.queryWindow')}>
        {windowText}
      </Descriptions.Item>
      <Descriptions.Item label={t('log.event.period')}>
        {formatClueValue(clue.period)}
      </Descriptions.Item>
      <Descriptions.Item label={t('log.event.alertType')}>
        {formatClueValue(clue.alert_type)}
      </Descriptions.Item>
      <Descriptions.Item label={t('log.event.queryCriteria')}>
        {formatClueValue(clue.alert_condition)}
      </Descriptions.Item>
    </Descriptions>
  );
};

const AlertRawLogWidget = ({ logAlertId }: AlertRawLogWidgetProps) => {
  const { t } = useTranslation();
  const { getAlertSnapshots } = useLogEventApi();
  const getAlertSnapshotsRef = useRef(getAlertSnapshots);
  getAlertSnapshotsRef.current = getAlertSnapshots;
  const [payload, setPayload] = useState<AlertSnapshotsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const alertId = String(logAlertId || '').trim();
    if (!alertId) {
      setLoading(false);
      setError(t('common.loadFailed'));
      setPayload(null);
      return;
    }
    setLoading(true);
    setError(null);
    setPayload(null);
    getAlertSnapshotsRef
      .current(alertId)
      .then((data: AlertSnapshotsPayload) => {
        if (!cancelled) setPayload(data || { snapshots: [] });
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              t,
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
  }, [logAlertId, reloadKey, t]);

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

  const snapshots = payload?.snapshots || [];
  const alertInfo = historicalAlertInfo(payload?.alert_info);
  if (!snapshots.length) {
    return (
      <div className="flex min-h-[280px] items-center justify-center">
        <CompactEmptyState description={t('common.noData')} />
      </div>
    );
  }

  return (
    <div className="flex min-h-[280px] min-w-0 flex-col gap-3">
      {(alertInfo.source_id || alertInfo.level || alertInfo.start_event_time || alertInfo.content) && (
        <div className="rounded-md border border-[var(--color-border-2)] p-3">
          <Descriptions column={1} size="small">
            <Descriptions.Item label={t('log.source')}>
              {alertInfo.source_id || '--'}
            </Descriptions.Item>
            <Descriptions.Item label={t('log.event.level')}>
              {alertInfo.level || '--'}
            </Descriptions.Item>
            <Descriptions.Item label={t('log.event.firstAlertTime')}>
              {alertInfo.start_event_time || '--'}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.description')}>
              {alertInfo.content || '--'}
            </Descriptions.Item>
          </Descriptions>
        </div>
      )}
      {snapshots.map((item, index) => (
        <div
          key={item.event_id || `${item.snapshot_time || 'snapshot'}-${index}`}
          className="rounded-md border border-[var(--color-border-2)] p-3"
        >
          <div className="mb-2 text-[var(--color-text-3)]">
            {item.event_time || item.snapshot_time || '--'}
          </div>
          <div className="mb-2 text-[var(--color-text-2)]">
            {t('log.event.queryClue')}
          </div>
          <QueryClueBlock clue={item.query_clue} />
          <div className="mb-2 mt-3 text-[var(--color-text-2)]">
            {t('log.event.originalLog')}
          </div>
          {hasSnapshotRawData(item.raw_data) ? (
            <pre className="m-0 max-h-[320px] overflow-auto whitespace-pre-wrap break-all text-[12px] text-[var(--color-text-1)]">
              {JSON.stringify(item.raw_data, null, 2)}
            </pre>
          ) : (
            <CompactEmptyState description={t('log.event.rawDataUnavailable')} />
          )}
        </div>
      ))}
    </div>
  );
};

export default AlertRawLogWidget;
