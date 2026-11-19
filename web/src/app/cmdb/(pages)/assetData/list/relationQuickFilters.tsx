'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Select, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { QuickFilterSlot, RelationFilter, relationFilterPayload } from './relationQuickFilter';

interface Option {
  value: string;
  label: string;
}

interface RelationQuickFiltersProps {
  slots: QuickFilterSlot[];
  onChange: (filters: RelationFilter[]) => void;
}

function withSelectedLabels(options: Option[], selected: string[], labels: Record<string, string>) {
  const seen = new Set(options.map((item) => item.value));
  const kept = selected
    .filter((value) => !seen.has(value))
    .map((value) => ({ value, label: labels[value] || value }));
  return [...kept, ...options];
}

const RelationQuickFilters: React.FC<RelationQuickFiltersProps> = ({ slots, onChange }) => {
  const { t } = useTranslation();
  const { searchInstances } = useInstanceApi();
  const searchRef = useRef(searchInstances);
  searchRef.current = searchInstances;
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [options, setOptions] = useState<Record<string, Option[]>>({});
  const [loadingId, setLoadingId] = useState('');
  const [openId, setOpenId] = useState('');
  const timers = useRef<Record<string, number>>({});
  const labels = useRef<Record<string, string>>({});

  useEffect(() => () => {
    Object.values(timers.current).forEach((timer) => window.clearTimeout(timer));
  }, []);

  if (!slots.length) return null;

  const loadOptions = async (slot: QuickFilterSlot, keyword: string) => {
    setLoadingId(slot.modelAsstId);
    try {
      const text = keyword.trim();
      const data = await searchRef.current({
        model_id: slot.targetModelId,
        page: 1,
        page_size: 20,
        query_list: text ? [{ field: 'inst_name', type: 'str*', value: text }] : [],
      });
      const next = (data?.insts || [])
        .map((item: { inst_uuid?: string; inst_name?: string }) => ({
          value: String(item.inst_uuid || ''),
          label: item.inst_name || String(item.inst_uuid || ''),
        }))
        .filter((item: Option) => item.value);
      next.forEach((item: Option) => {
        labels.current[item.value] = item.label;
      });
      setOptions((current) => ({ ...current, [slot.modelAsstId]: next }));
    } catch {
      setOptions((current) => ({ ...current, [slot.modelAsstId]: [] }));
    } finally {
      setLoadingId('');
    }
  };

  const emit = (next: Record<string, string[]>) => {
    setSelected(next);
    onChange(relationFilterPayload(next));
  };

  return (
    <span className="inline-flex shrink-0 items-center gap-2">
      {slots.map((slot) => (
        <Select
          key={slot.modelAsstId}
          className="shrink-0"
          style={{ width: 168 }}
          mode="multiple"
          allowClear
          showSearch
          filterOption={false}
          maxTagCount={1}
          placeholder={t('AdvancedFilter.belongsTo', '所属{name}', { name: slot.labelName })}
          value={selected[slot.modelAsstId] || []}
          options={withSelectedLabels(options[slot.modelAsstId] || [], selected[slot.modelAsstId] || [], labels.current)}
          notFoundContent={loadingId === slot.modelAsstId ? <Spin size="small" /> : null}
          open={openId === slot.modelAsstId}
          onOpenChange={(open) => {
            setOpenId(open ? slot.modelAsstId : '');
            if (open) void loadOptions(slot, '');
          }}
          onSearch={(keyword) => {
            window.clearTimeout(timers.current[slot.modelAsstId]);
            timers.current[slot.modelAsstId] = window.setTimeout(() => {
              void loadOptions(slot, keyword);
            }, 300);
          }}
          onChange={(values: string[]) => {
            values.forEach((value) => {
              labels.current[value] = labels.current[value] || value;
            });
            emit({ ...selected, [slot.modelAsstId]: values });
            setOpenId('');
          }}
        />
      ))}
    </span>
  );
};

export default RelationQuickFilters;
