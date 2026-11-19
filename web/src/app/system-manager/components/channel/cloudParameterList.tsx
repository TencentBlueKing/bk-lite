'use client';

import React from 'react';
import { Button, Input, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';

export interface CloudTemplateParameter {
  source: 'title' | 'content' | 'literal';
  name: string;
  value: string;
}

interface CloudParameterListProps {
  value?: CloudTemplateParameter[];
  onChange?: (value: CloudTemplateParameter[]) => void;
  provider?: string;
}

const SOURCES = [
  { value: 'title', labelKey: 'system.channel.settings.cloudSourceTitle' },
  { value: 'content', labelKey: 'system.channel.settings.cloudSourceContent' },
  { value: 'literal', labelKey: 'system.channel.settings.cloudSourceLiteral' },
] as const;

const CloudParameterList: React.FC<CloudParameterListProps> = ({ value, onChange, provider }) => {
  const { t } = useTranslation();
  const items = Array.isArray(value) ? value : [];
  const update = (next: CloudTemplateParameter[]) => onChange?.(next);

  return (
    <div className="flex flex-col gap-2">
      {items.map((item, index) => (
        <div className="flex items-center gap-2" key={`${item.source}-${index}`}>
          <Select
            className="w-[120px]"
            value={item.source}
            options={SOURCES.map((source) => ({ value: source.value, label: t(source.labelKey) }))}
            onChange={(source) => {
              const next = items.slice();
              next[index] = { ...item, source };
              update(next);
            }}
          />
          {provider === 'aliyun' ? (
            <Input
              className="w-[140px]"
              value={item.name}
              placeholder={t('system.channel.settings.cloudParameterName')}
              onChange={(event) => {
                const next = items.slice();
                next[index] = { ...item, name: event.target.value };
                update(next);
              }}
            />
          ) : null}
          {item.source === 'literal' ? (
            <Input
              value={item.value}
              placeholder={t('system.channel.settings.cloudLiteral')}
              onChange={(event) => {
                const next = items.slice();
                next[index] = { ...item, value: event.target.value };
                update(next);
              }}
            />
          ) : null}
          <Button type="link" onClick={() => update(items.filter((_, itemIndex) => itemIndex !== index))}>
            {t('common.delete')}
          </Button>
        </div>
      ))}
      <Button
        disabled={items.length >= 20}
        type="dashed"
        onClick={() => update([...items, { source: 'content', name: '', value: '' }])}
      >
        {t('system.channel.settings.cloudAddParameter')}
      </Button>
    </div>
  );
};

export default CloudParameterList;
