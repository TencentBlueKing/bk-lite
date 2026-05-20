'use client';

import React, { useState } from 'react';
import { Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { EllipsisOutlined, EyeOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { SourceItem } from '@/app/alarm/types/integration';
import { getHealth, getLogoColor, formatEventCount, formatTimestamp } from '../utils/health';

interface IntegrationCardProps {
  src: SourceItem;
}

const IntegrationCard: React.FC<IntegrationCardProps> = ({ src }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [hovered, setHovered] = useState(false);

  const health = getHealth(src);
  const logoColor = getLogoColor(src.source_id);
  const monogram = src.name.slice(0, 2).toUpperCase();

  const menuItems: MenuProps['items'] = [
    { key: 'edit', label: t('integration.editConfig') },
    { key: 'copy', label: t('integration.copySecret') },
    { key: 'logs', label: t('integration.viewLogs') },
    { type: 'divider' },
    { key: 'delete', label: t('integration.deleteSource'), danger: true },
  ];

  const handleMenuClick: MenuProps['onClick'] = () => {
    // Menu actions are no-op stubs per design
  };

  return (
    <div
      className="rounded-xl border bg-[var(--color-bg-1)] p-[20px_20px_16px] relative transition-all duration-200 cursor-default"
      style={{
        borderColor: hovered ? '#c8d0e0' : 'var(--color-border)',
        boxShadow: hovered ? '0 4px 20px rgba(0,0,0,0.06)' : 'none',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Header: logo + name + badge + menu */}
      <div className="flex items-center gap-3 mb-4">
        {/* Circular logo */}
        <div
          className="w-[42px] h-[42px] rounded-full shrink-0 grid place-items-center overflow-hidden"
          style={{
            background: src.logo ? logoColor : `${logoColor}14`,
            border: src.logo ? 'none' : `1.5px solid ${logoColor}30`,
          }}
        >
          {src.logo ? (
            <img src={src.logo} alt={src.name} className="w-[22px] h-[22px]" />
          ) : (
            <svg viewBox="0 0 24 24" width="22" height="22">
              <text
                x="12"
                y="16"
                fontSize="11"
                fontWeight="700"
                textAnchor="middle"
                fill={logoColor}
                fontFamily="-apple-system, Helvetica"
              >
                {monogram}
              </text>
            </svg>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[15px] font-semibold text-[var(--color-text-1)] whitespace-nowrap truncate">
              {src.name}
            </span>
            <span
              className="text-[11px] font-medium px-2 rounded-[10px] leading-5 whitespace-nowrap shrink-0"
              style={{ color: health.color, background: health.bg }}
            >
              {t(health.labelKey)}
            </span>
          </div>
        </div>

        {/* Three-dot menu */}
        <Dropdown
          menu={{ items: menuItems, onClick: handleMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <div className="w-6 h-6 rounded-md grid place-items-center cursor-pointer text-[var(--color-text-3)] hover:bg-[#f2f3f5] shrink-0">
            <EllipsisOutlined className="text-base" style={{ transform: 'rotate(90deg)' }} />
          </div>
        </Dropdown>
      </div>

      {/* Metrics */}
      <div className="flex flex-col gap-[6px] mb-4">
        <div className="flex items-center text-[13px] text-[var(--color-text-2)]">
          <span className="text-[var(--color-text-3)] w-[100px] shrink-0">{t('integration.eventCount')}</span>
          <span className="font-semibold tabular-nums">{formatEventCount(src.event_count)}</span>
        </div>
        <div className="flex items-center text-[13px] text-[var(--color-text-2)]">
          <span className="text-[var(--color-text-3)] w-[100px] shrink-0">{t('integration.lastEventTime')}</span>
          <span className="tabular-nums">{formatTimestamp(src.last_event_time)}</span>
        </div>
      </div>

      {/* Footer actions */}
      <div className="border-t border-[#f2f3f5] pt-3 flex items-center">
        <button
          type="button"
          className="flex items-center gap-[6px] text-[13px] text-[var(--color-primary)] font-medium cursor-pointer bg-transparent border-none p-0 hover:opacity-70 transition-opacity"
          onClick={() => router.push(`/alarm/integration/detail?sourceItemId=${src.id}`)}
        >
          <EyeOutlined className="text-sm" />
          {t('integration.viewDetail')}
        </button>
      </div>
    </div>
  );
};

export default IntegrationCard;
