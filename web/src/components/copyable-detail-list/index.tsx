'use client';

import type { ReactNode } from 'react';
import { Button, Typography, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useCopy } from '@/hooks/useCopy';

const { Text } = Typography;

export interface CopyableDetailListItem {
  key?: string;
  label: ReactNode;
  value?: string | number | null;
  displayValue?: ReactNode;
  copyValue?: string | null;
  copyable?: boolean;
}

export interface CopyableDetailListProps {
  items: CopyableDetailListItem[];
  className?: string;
  labelWidthClassName?: string;
  placeholder?: string;
}

export default function CopyableDetailList({
  items,
  className,
  labelWidthClassName = 'w-24',
  placeholder = '-',
}: CopyableDetailListProps) {
  const { t } = useTranslation();
  const { copy } = useCopy();

  return (
    <div className={className}>
      {items.map((item, index) => {
        const rawValue = item.value;
        const hasValue = rawValue !== undefined && rawValue !== null && rawValue !== '';
        const hasCustomDisplay = item.displayValue !== undefined;
        const displayValue = item.displayValue ?? (hasValue ? String(rawValue) : placeholder);
        const copyValue = item.copyValue ?? (hasValue ? String(rawValue) : '');
        const canCopy = (item.copyable ?? true) && !!copyValue;
        const isEven = index % 2 === 0;
        const plainTextClassName = `text-xs ${canCopy ? 'text-gray-900' : 'text-gray-400 italic'}`;

        return (
          <div
            key={item.key || `${index}`}
            className={`flex items-start justify-between px-6 py-2 transition-all duration-200 hover:bg-blue-50 ${
              isEven ? 'bg-gray-50' : 'bg-white'
            }`}
          >
            <div className="flex min-w-0 flex-1 items-start space-x-6">
              <div className={`${labelWidthClassName} flex-shrink-0`}>
                <Text className="text-xs font-semibold text-gray-700">{item.label}</Text>
              </div>
              <div className="min-w-0 flex-1">
                {hasCustomDisplay ? (
                  <div
                    className={canCopy ? 'text-gray-900' : 'text-gray-400'}
                    style={{
                      wordBreak: 'break-word',
                      overflowWrap: 'break-word',
                      lineHeight: '1.2',
                    }}
                  >
                    {displayValue}
                  </div>
                ) : (
                  <Text
                    className={plainTextClassName}
                    style={{
                      wordBreak: 'break-word',
                      overflowWrap: 'break-word',
                      lineHeight: '1.2',
                    }}
                  >
                    {displayValue}
                  </Text>
                )}
              </div>
            </div>
            <div className="ml-4 mt-[2px] flex-shrink-0">
              <Button
                type="text"
                size="small"
                aria-label={t('common.copy')}
                icon={<CopyOutlined aria-hidden="true" />}
                disabled={!canCopy}
                className={`border-0 shadow-none transition-all duration-200 ${
                  canCopy
                    ? 'text-blue-500 hover:text-blue-700 hover:bg-blue-100'
                    : 'cursor-not-allowed text-gray-300'
                }`}
                style={{
                  minWidth: '32px',
                  height: '32px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                onClick={() => {
                  if (!canCopy) {
                    message.warning(t('common.noContentToCopy'));
                    return;
                  }
                  copy(copyValue);
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
