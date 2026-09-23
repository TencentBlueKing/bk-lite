'use client';

import React, { useMemo, useRef, useState } from 'react';
import { Button, Select, Spin } from 'antd';
import { useSourceApi } from '@/app/alarm/api/integration';
import { normalizeRuleTags } from '@/app/alarm/utils/multivalueRules';
import { useTranslation } from '@/utils/i18n';

interface PushSourceSelectProps {
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
  status?: 'error';
}

const MAX_COUNT = 50;

const PushSourceSelect = ({ value, onChange, disabled, status }: PushSourceSelectProps) => {
  const { t } = useTranslation();
  const { getPushSourceIdOptions } = useSourceApi();
  const [catalog, setCatalog] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const loaded = useRef(false);
  const pending = useRef(false);
  const catalogSet = useMemo(() => new Set(catalog), [catalog]);
  const selected = value.filter(item => catalogSet.has(item));
  const manual = value.filter(item => !catalogSet.has(item));
  const publish = (next: string[]) => onChange(normalizeRuleTags(next).slice(0, MAX_COUNT));

  const load = async () => {
    if (pending.current || loaded.current) return;
    pending.current = true;
    setLoading(true);
    setFailed(false);
    try {
      const rows = await getPushSourceIdOptions();
      setCatalog(Array.isArray(rows) ? rows.filter((item): item is string => typeof item === 'string' && !!item.trim()) : []);
      loaded.current = true;
    } catch {
      setFailed(true);
    } finally {
      pending.current = false;
      setLoading(false);
    }
  };

  return <div className="w-full space-y-2">
    <Select<string[]>
      className="w-full" mode="multiple" showSearch allowClear maxCount={MAX_COUNT - manual.length} maxLength={256}
      aria-label={t('alarmCommon.pushSourceSelect')} placeholder={t('common.selectTip')}
      value={selected} onChange={next => publish([...next, ...manual])} disabled={disabled} status={status}
      options={catalog.map(item => ({ value: item, label: item }))} optionFilterProp="value" loading={loading}
      onOpenChange={open => { if (open) void load(); }}
      notFoundContent={loading ? <Spin size="small" /> : failed ?
        <Button type="link" onClick={() => void load()}>{t('alarmCommon.pushSourceOptionsRetry')}</Button> :
        t('alarmCommon.pushSourceEmpty')}
    />
    <Select<string[]>
      className="w-full" mode="tags" open={false} suffixIcon={null} options={[]}
      aria-label={t('alarmCommon.pushSourceInput')} placeholder={t('alarmCommon.multiValuePlaceholder')}
      value={manual} disabled={disabled} status={status} maxCount={MAX_COUNT - selected.length} maxLength={256}
      onChange={next => {
        const tags = normalizeRuleTags(next);
        publish([...selected, ...tags.filter(item => catalogSet.has(item)), ...tags.filter(item => !catalogSet.has(item))]);
      }}
    />
  </div>;
};

export default PushSourceSelect;
