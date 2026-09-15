'use client';

import React, { useMemo, useRef, useState } from 'react';
import { Button, Select, Spin } from 'antd';
import { useSourceApi } from '@/app/alarm/api/integration';
import type { AlertSourceOption } from '@/app/alarm/types/integration';
import { useTranslation } from '@/utils/i18n';

interface SourceNameSelectProps {
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
  status?: 'error';
}

const SourceNameSelect = ({ value, onChange, disabled, status }: SourceNameSelectProps) => {
  const { t } = useTranslation();
  const { getAlertSourceOptions } = useSourceApi();
  const [sources, setSources] = useState<AlertSourceOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const loaded = useRef(false);
  const pending = useRef(false);
  const options = useMemo(() => {
    // 匹配协议按名称保存；同名来源合为一个选项，ID 用于展示和搜索。
    const names = new Map<string, AlertSourceOption[]>();
    sources.forEach(source => {
      if (!source.name?.trim()) return;
      names.set(source.name, [...(names.get(source.name) || []), source]);
    });
    return Array.from(names, ([name, items]) => ({
      value: name,
      label: `${name} (ID: ${items.map(item => item.id).join(', ')})`,
      search: [name, ...items.flatMap(item => [String(item.id), item.source_id])].join(' '),
    }));
  }, [sources]);

  const load = async () => {
    if (pending.current || loaded.current) return;
    pending.current = true;
    setLoading(true);
    setFailed(false);
    try {
      setSources(await getAlertSourceOptions());
      loaded.current = true;
    } catch {
      setFailed(true);
    } finally {
      pending.current = false;
      setLoading(false);
    }
  };

  return <Select<string[]>
    className="w-full" mode="multiple" showSearch allowClear maxCount={50}
    aria-label={t('alarmCommon.sourceSelect')} placeholder={t('common.selectTip')}
    value={value} onChange={onChange} disabled={disabled} status={status}
    options={options} optionFilterProp="search" optionLabelProp="value" loading={loading}
    onOpenChange={open => { if (open) void load(); }}
    notFoundContent={loading ? <Spin size="small" /> : failed ?
      <Button type="link" onClick={() => void load()}>{t('alarmCommon.sourceOptionsRetry')}</Button> : undefined}
  />;
};

export default SourceNameSelect;
