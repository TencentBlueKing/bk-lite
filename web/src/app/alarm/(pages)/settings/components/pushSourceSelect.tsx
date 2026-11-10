'use client';

import React, { useRef, useState } from 'react';
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

  return (
    <Select<string[]>
      className="w-full"
      mode="tags"
      showSearch
      allowClear
      maxCount={MAX_COUNT}
      maxLength={256}
      aria-label={t('alarmCommon.pushSourceSelect')}
      placeholder={t('alarmCommon.pushSourcePlaceholder', '选择或输入，回车添加')}
      value={value}
      disabled={disabled}
      status={status}
      options={catalog.map((item) => ({ value: item, label: item }))}
      optionFilterProp="value"
      loading={loading}
      onChange={(next) => onChange(normalizeRuleTags(next).slice(0, MAX_COUNT))}
      onOpenChange={(open) => {
        if (open) void load();
      }}
      notFoundContent={
        loading ? (
          <Spin size="small" />
        ) : failed ? (
          <Button type="link" onClick={() => void load()}>
            {t('alarmCommon.pushSourceOptionsRetry')}
          </Button>
        ) : catalog.length ? (
          t('alarmCommon.pushSourcePressEnter', '按回车添加')
        ) : (
          t('alarmCommon.pushSourceEmpty', '暂无已识别监控源，可输入后回车添加')
        )
      }
    />
  );
};

export default PushSourceSelect;
