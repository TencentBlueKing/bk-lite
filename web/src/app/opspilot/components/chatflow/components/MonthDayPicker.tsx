'use client';

import React, { useState } from 'react';
import { Popover } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface MonthDayPickerProps {
  value?: number | 'last';
  onChange?: (value: number | 'last') => void;
  disabled?: boolean;
}

const MonthDayPicker: React.FC<MonthDayPickerProps> = ({
  value = 1,
  onChange,
  disabled = false,
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const days = Array.from({ length: 31 }, (_, i) => i + 1);
  const warningDays = [29, 30, 31];

  const getDisplayText = () => {
    if (value === 'last') {
      return t('chatflow.nodeConfig.lastDayOfMonth');
    }
    return t('chatflow.nodeConfig.dayOfMonth', undefined, { day: value });
  };

  const handleSelect = (day: number | 'last') => {
    onChange?.(day);
    setOpen(false);
  };

  const popoverContent = (
    <div className="w-[280px]">
      {/* 每月最后一天选项 */}
      <div
        className={`px-3 py-2 rounded cursor-pointer mb-2 ${
          value === 'last'
            ? 'bg-[var(--color-primary)] text-white'
            : 'hover:bg-gray-100'
        }`}
        onClick={() => handleSelect('last')}
      >
        {t('chatflow.nodeConfig.lastDayOfMonth')}
      </div>

      {/* 日期网格 */}
      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => {
          const isSelected = value === day;
          const isWarning = warningDays.includes(day);

          return (
            <div
              key={day}
              className={`
                w-8 h-8 flex items-center justify-center rounded cursor-pointer text-sm
                ${isSelected 
                ? 'bg-[var(--color-primary)] text-white' 
                : isWarning
                  ? 'text-orange-500 hover:bg-orange-50'
                  : 'hover:bg-gray-100'
                }
              `}
              onClick={() => handleSelect(day)}
            >
              {day}
            </div>
          );
        })}
      </div>

      {/* 提示文字 */}
      <div className="mt-2 text-xs text-gray-400">
        <span className="text-orange-500">29-31</span> {t('chatflow.nodeConfig.dayMayNotExist')}
      </div>
    </div>
  );

  return (
    <Popover
      content={popoverContent}
      trigger="click"
      open={disabled ? false : open}
      onOpenChange={disabled ? undefined : setOpen}
      placement="bottomLeft"
      arrow={false}
      overlayInnerStyle={{ padding: '12px' }}
    >
      <div
        className={`
          px-3 py-1.5 border border-gray-300 rounded-md cursor-pointer
          flex items-center justify-between min-w-[140px]
          ${disabled ? 'bg-gray-100 cursor-not-allowed' : 'hover:border-[var(--color-primary)]'}
        `}
        onClick={disabled ? undefined : () => setOpen(!open)}
      >
        <span>{getDisplayText()}</span>
        <DownOutlined className="text-gray-400 text-xs" />
      </div>
    </Popover>
  );
};

export default MonthDayPicker;
