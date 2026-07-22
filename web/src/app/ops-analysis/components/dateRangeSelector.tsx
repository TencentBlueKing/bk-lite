'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DatePicker, Select } from 'antd';
import { CalendarOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';

import {
  DEFAULT_DATE_RANGE_VALUE,
  DateRangeType,
  DateRangeValue,
} from '@/app/ops-analysis/types/dateRange';
import { validateDateRangeValue } from '@/app/ops-analysis/utils/dateRange';
import { useTranslation } from '@/utils/i18n';
import {
  completeCustomDateRange,
  getDateRangeSelectorValue,
  toDateRangePickerValue,
} from './dateRangeSelectorModel';

const { RangePicker } = DatePicker;

const QUICK_RANGE_TYPES: Exclude<DateRangeType, 'custom'>[] = [
  'today',
  'yesterday',
  'this_week',
  'last_week',
  'this_month',
  'last_month',
  'last_7_days',
  'last_30_days',
  'last_90_days',
];

export interface DateRangeSelectorProps {
  value?: DateRangeValue | null;
  onChange?: (value: DateRangeValue | null) => void;
  disabled?: boolean;
  allowClear?: boolean;
  status?: 'error' | 'warning';
  className?: string;
}

const DateRangeSelector: React.FC<DateRangeSelectorProps> = ({
  value,
  onChange,
  disabled = false,
  allowClear = true,
  status,
  className,
}) => {
  const { t } = useTranslation();
  const initializedRef = useRef(false);
  const effectiveValue = getDateRangeSelectorValue(value);
  const effectiveStatus = status ?? (
    value !== undefined && !validateDateRangeValue(value).valid ? 'error' : undefined
  );
  const [customOpen, setCustomOpen] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const selectRef = useRef<HTMLDivElement>(null);
  const [customDraft, setCustomDraft] = useState<[Dayjs | null, Dayjs | null] | null>(
    () => toDateRangePickerValue(value),
  );

  useEffect(() => {
    if (value === undefined && !initializedRef.current) {
      initializedRef.current = true;
      onChange?.({ ...DEFAULT_DATE_RANGE_VALUE });
    }
  }, [onChange, value]);

  const options = useMemo(() => [
    ...QUICK_RANGE_TYPES.map((rangeType) => ({
      value: rangeType,
      label: t(`dateRange.${rangeType}`),
    })),
    { value: 'custom', label: t('dateRange.custom') },
  ], [t]);

  const handleTypeChange = (rangeType: DateRangeType) => {
    if (rangeType === 'custom') {
      setCustomDraft(toDateRangePickerValue(value));
      setCustomOpen(true);
      return;
    }

    setCustomOpen(false);
    setCustomDraft(null);
    onChange?.({ rangeType });
  };

  const handleCustomChange = (dates: [Dayjs | null, Dayjs | null] | null) => {
    setCustomDraft(dates);
    if (!dates) {
      onChange?.(null);
      setCustomOpen(false);
      return;
    }

    const completed = completeCustomDateRange(dates);
    if (completed) {
      onChange?.(completed);
      setCustomOpen(false);
    }
  };

  const handleClear = () => {
    setCustomDraft(null);
    setCustomOpen(false);
    onChange?.(null);
  };

  const handleIconClick = () => {
    selectRef.current?.querySelector<HTMLElement>('.ant-select-selector')?.click();
  };

  return (
    <div className={`relative w-full ${className ?? ''}`}>
      <div ref={selectRef} className="w-full">
        <Select<DateRangeType>
          value={customOpen ? 'custom' : effectiveValue?.rangeType}
          options={options}
          open={dropdownOpen}
          onChange={handleTypeChange}
          onClear={handleClear}
          onOpenChange={setDropdownOpen}
          allowClear={allowClear}
          disabled={disabled}
          status={effectiveStatus}
          placeholder={t('dateRange.placeholder')}
            className={`w-[350px] ${className ?? ''}`}
        />
        <RangePicker
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: customOpen || effectiveValue?.rangeType === 'custom' ? 1 : -1,
          }}
          value={customOpen ? customDraft : toDateRangePickerValue(effectiveValue)}
          onCalendarChange={(dates) => setCustomDraft(dates as [Dayjs | null, Dayjs | null] | null)}
          onChange={(dates) => handleCustomChange(dates as [Dayjs | null, Dayjs | null] | null)}
          onOpenChange={(open) => {
            setCustomOpen(open);
            if (!open && !completeCustomDateRange(customDraft)) {
              setCustomDraft(toDateRangePickerValue(value));
            }
          }}
          open={customOpen}
          format="YYYY-MM-DD"
          allowClear={allowClear}
          disabled={disabled}
          status={effectiveStatus}
          placeholder={[t('dateRange.startDate'), t('dateRange.endDate')]}
          className={`w-[350px] ${className ?? ''}`}
        />
        <CalendarOutlined
          className="absolute right-2 top-1/2 z-2 -translate-y-1/2 cursor-pointer text-(--color-text-4)"
          onClick={handleIconClick}
        />
      </div>
    </div>
  );
};

export default DateRangeSelector;
