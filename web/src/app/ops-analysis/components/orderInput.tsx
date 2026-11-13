'use client';

import React, { useMemo } from 'react';
import { Select } from 'antd';
import type { OrderFieldOption } from '@/app/ops-analysis/types/dataSource';
import { parseOrderValue, serializeOrderValue } from '@/app/ops-analysis/utils/orderValue';
import { useTranslation } from '@/utils/i18n';

interface OrderInputProps {
  value?: unknown;
  onChange?: (value: string) => void;
  fields: OrderFieldOption[];
  disabled?: boolean;
}

/**
 * 槽位负责行宽。Form.Item 里的 Select 带 width:100%，直接并排时升降序会占满整行。
 */
const OrderInput: React.FC<OrderInputProps> = ({
  value,
  onChange,
  fields,
  disabled = false,
}) => {
  const { t } = useTranslation();
  const parsed = parseOrderValue(value);
  const options = useMemo(() => {
    const known = fields.map((field) => ({ label: field.label, value: field.value }));
    if (parsed.field && !known.some((item) => item.value === parsed.field)) {
      known.unshift({ label: parsed.field, value: parsed.field });
    }
    return known;
  }, [fields, parsed.field]);

  return (
    <div className="flex w-full min-w-0 items-center gap-2">
      <div data-slot="order-field" className="min-w-[72px] flex-1 basis-0">
        <Select
          aria-label={t('dashboard.order.field')}
          data-testid="order-field"
          className="w-full"
          style={{ width: '100%' }}
          allowClear
          disabled={disabled}
          placeholder={t('dashboard.order.field')}
          value={parsed.field || undefined}
          options={options}
          onChange={(field) => onChange?.(serializeOrderValue(String(field || ''), parsed.descending))}
        />
      </div>
      <div data-slot="order-direction" className="w-[96px] shrink-0">
        <Select
          aria-label={t('dashboard.order.direction')}
          data-testid="order-direction"
          className="w-full"
          style={{ width: '100%' }}
          disabled={disabled || !parsed.field}
          value={parsed.descending ? 'desc' : 'asc'}
          options={[
            { label: t('dashboard.order.asc'), value: 'asc' },
            { label: t('dashboard.order.desc'), value: 'desc' },
          ]}
          onChange={(direction) => onChange?.(serializeOrderValue(parsed.field, direction === 'desc'))}
        />
      </div>
    </div>
  );
};

export default OrderInput;
