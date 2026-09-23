'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button, Collapse } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DisconnectOutlined,
  ReloadOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';

import { useRumQueries, type RumApplicationStatus } from '@/app/rum/api';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import SemanticBadge from '@/components/semantic-badge';
import { toneSemanticPalette } from '@/app/rum/lib/cwv';
import { useTranslation } from '@/utils/i18n';

export default function SelfCheck({ application }: { application: string }) {
  const { t } = useTranslation();
  const { getApplicationStatus } = useRumQueries();
  const [status, setStatus] = useState<RumApplicationStatus | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  const run = useCallback(async () => {
    if (!application) return;
    setPending(true);
    setError('');
    try {
      setStatus(await getApplicationStatus(application));
    } catch (err) {
      setStatus(null);
      setError(rumErrorMessage(err, t));
    } finally {
      setPending(false);
    }
  }, [application, getApplicationStatus, t]);

  useEffect(() => {
    void run();
  }, [run]);

  const verdict = !status
    ? null
    : status.status === 'connected'
      ? 'connected'
      : status.status === 'disabled'
        ? 'disabled'
        : 'waiting';
  const summaryKey =
    status?.controllerUnreachable && verdict === 'waiting' ? 'unreachable' : verdict;

  function layerRow(label: string, state: 'ok' | 'waiting') {
    return (
      <div className="flex items-center justify-between gap-2 py-1.5 text-sm">
        <span className="text-[var(--color-text-3)]">{label}</span>
        {state === 'ok' ? (
          <span className="inline-flex items-center gap-1 text-[var(--color-success)]">
            <CheckCircleOutlined /> {t('rum.verdict.connected', 'RUM 已接通')}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-[var(--color-primary)]">
            <ClockCircleOutlined /> {t('rum.verdict.waiting', '等待数据')}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {verdict ? (
            <SemanticBadge
              label={t(`rum.verdict.${verdict}`)}
              {...toneSemanticPalette(
                verdict === 'connected' ? 'success' : verdict === 'disabled' ? 'neutral' : 'info',
              )}
            />
          ) : null}
          {verdict && summaryKey ? (
            <span className="text-sm text-[var(--color-text-3)]">
              {t(`rum.selfCheck.summary.${summaryKey}`)}
            </span>
          ) : null}
        </div>
        <Button icon={<ReloadOutlined aria-hidden="true" />} loading={pending} onClick={() => void run()}>
          {t('rum.selfCheck.rerun', '重新自检')}
        </Button>
      </div>
      {error ? (
        <div className="flex items-center gap-1 text-sm text-[var(--color-fail)]">
          <CloseCircleOutlined className="shrink-0" /> {error}
        </div>
      ) : null}
      {status ? (
        <Collapse
          size="small"
          ghost
          defaultActiveKey={status.status !== 'connected' ? ['diagnostics'] : []}
          items={[
            {
              key: 'diagnostics',
              label: (
                <span className="text-xs font-semibold text-[var(--color-text-3)]">
                  {t('rum.selfCheck.diagnostics', '诊断详情')}
                </span>
              ),
              children: (
                <div className="divide-y divide-[var(--color-border-2)]">
                  {status.controllerUnreachable ? (
                    <div className="flex items-center gap-1 py-1.5 text-sm text-[var(--theme-color-status-warning)]">
                      <DisconnectOutlined className="shrink-0" />{' '}
                      {t('rum.selfCheck.controllerUnreachable', 'RUM 控制面不可达，无法确认接入状态')}
                    </div>
                  ) : null}
                  {layerRow(t('rum.selfCheck.gateway', '网关接收'), status.gateway.state)}
                  {layerRow(t('rum.selfCheck.store', '数据落库'), status.store.state)}
                </div>
              ),
            },
          ]}
        />
      ) : null}
    </div>
  );
}
