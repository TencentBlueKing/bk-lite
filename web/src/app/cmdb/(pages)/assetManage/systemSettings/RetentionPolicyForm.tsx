'use client';

import { Button, InputNumber, Modal, Radio, Space } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';

export type RetentionMode = 'off' | 'by_days' | 'by_count';

export interface RetentionPolicy {
  mode: RetentionMode;
  days: number | null;
  count: number | null;
}

export interface RetentionJob {
  status: 'idle' | 'running';
  started_at: string | null;
  finished_at: string | null;
  deleted_count: number;
  error: string;
  trigger: string;
}

export default function RetentionPolicyForm({
  policy,
  job,
  saving,
  onSave,
}: {
  policy: RetentionPolicy;
  job: RetentionJob;
  saving: boolean;
  onSave: (policy: RetentionPolicy) => void;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<RetentionMode>(policy.mode);
  const [days, setDays] = useState<number>(policy.days || 180);
  const [count, setCount] = useState<number>(policy.count || 10000);

  useEffect(() => {
    setMode(policy.mode);
    setDays(policy.days || 180);
    setCount(policy.count || 10000);
  }, [policy]);

  const running = job.status === 'running';
  const submit = () => {
    const next: RetentionPolicy =
      mode === 'off'
        ? { mode: 'off', days: null, count: null }
        : mode === 'by_days'
          ? { mode: 'by_days', days, count: null }
          : { mode: 'by_count', days: null, count };
    if (mode === 'off') {
      onSave(next);
      return;
    }
    Modal.confirm({
      title: t('SystemSettings.confirmTitle'),
      content: t('SystemSettings.confirmContent'),
      onOk: () => onSave(next),
    });
  };

  return (
    <div className="flex max-w-[640px] flex-col gap-4">
      <h3 className="text-base font-medium">{t('SystemSettings.retentionTitle')}</h3>
      <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)} disabled={running}>
        <Space direction="vertical">
          <Radio value="off">{t('SystemSettings.modeOff')}</Radio>
          <Radio value="by_days">{t('SystemSettings.modeDays')}</Radio>
          <Radio value="by_count">{t('SystemSettings.modeCount')}</Radio>
        </Space>
      </Radio.Group>
      {mode === 'by_days' ? (
        <label className="flex items-center gap-2">
          {t('SystemSettings.days')}
          <InputNumber min={1} value={days} onChange={(v) => setDays(Number(v) || 1)} disabled={running} />
        </label>
      ) : null}
      {mode === 'by_count' ? (
        <label className="flex items-center gap-2">
          {t('SystemSettings.count')}
          <InputNumber min={1} value={count} onChange={(v) => setCount(Number(v) || 1)} disabled={running} />
        </label>
      ) : null}
      <div className="text-[var(--color-text-3)]">
        {running ? t('SystemSettings.running') : null}
        {job.finished_at ? (
          <div>
            {t('SystemSettings.lastRun')}: {job.finished_at} · {t('SystemSettings.deletedCount')}: {job.deleted_count}
          </div>
        ) : null}
        {job.error ? <div>{job.error}</div> : null}
      </div>
      <Button type="primary" onClick={submit} loading={saving} disabled={running} autoInsertSpace={false}>
        {t('SystemSettings.save')}
      </Button>
    </div>
  );
}
