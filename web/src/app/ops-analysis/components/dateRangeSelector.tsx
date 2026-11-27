'use client';

import React, { useMemo, useRef, useState } from 'react';
import { DatePicker, Select } from 'antd';
import { CalendarOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';

import {
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

  const customVisible = customOpen || effectiveValue?.rangeType === 'custom';
  const fillsParent = Boolean(className?.split(/\s+/).includes('w-full'));
  const widthClass = fillsParent ? 'w-full' : 'w-[350px]';

  return (
    <div className={`relative min-w-0 w-full ${className ?? ''}`}>
      <div ref={selectRef} className="relative w-full">
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
          className={`${widthClass} [&_.ant-select-arrow]:invisible`}
          style={{
            opacity: customVisible ? 0 : 1,
            pointerEvents: customVisible ? 'none' : 'auto',
          }}
        />
        <RangePicker
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            zIndex: customVisible ? 1 : -1,
            opacity: customVisible ? 1 : 0,
            pointerEvents: customVisible ? 'auto' : 'none',
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
          suffixIcon={customVisible ? <CalendarOutlined className="text-(--color-text-4)" /> : null}
          allowClear={allowClear}
          disabled={disabled}
          status={effectiveStatus}
          placeholder={[t('dateRange.startDate'), t('dateRange.endDate')]}
          className={widthClass}
        />
        {!customVisible && (
          <CalendarOutlined
            className={`absolute top-1/2 z-2 -translate-y-1/2 cursor-pointer text-(--color-text-4) ${
              allowClear && effectiveValue ? 'right-8' : 'right-2.5'
            }`}
            onClick={handleIconClick}
          />
        )}
      </div>
    </div>
  );
};

export default DateRangeSelector;
