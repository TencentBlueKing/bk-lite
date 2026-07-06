'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, InputRef, Tooltip } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import type { IconFontData, IconGlyph } from '@/app/system-manager/types/application';

interface IconFontSelectorProps {
  value?: string;
  onChange: (iconName: string) => void;
  variant?: 'square' | 'compact';
  className?: string;
}

const IconFontSelector: React.FC<IconFontSelectorProps> = ({
  value,
  onChange,
  variant = 'compact',
  className = '',
}) => {
  const { t } = useTranslation();
  const [iconSelectorVisible, setIconSelectorVisible] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [icons, setIcons] = useState<IconGlyph[]>([]);
  const iconSelectorRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<InputRef>(null);

  useEffect(() => {
    const loadIconData = async () => {
      try {
        const response = await fetch('/iconfont.json');
        if (!response.ok) {
          throw new Error(`Failed to fetch icon data: ${response.status}`);
        }
        const iconData: IconFontData = await response.json();
        setIcons(iconData.glyphs || []);
      } catch {
        setIcons([]);
      }
    };

    loadIconData();
  }, []);

  const filteredIcons = useMemo(
    () =>
      icons.filter((icon) =>
        !searchValue ||
        icon.name.toLowerCase().includes(searchValue.toLowerCase()) ||
        icon.font_class.toLowerCase().includes(searchValue.toLowerCase())
      ),
    [icons, searchValue]
  );

  useEffect(() => {
    if (iconSelectorVisible && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 100);
    }
  }, [iconSelectorVisible]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (iconSelectorRef.current && !iconSelectorRef.current.contains(event.target as Node)) {
        setIconSelectorVisible(false);
      }
    };

    if (iconSelectorVisible) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [iconSelectorVisible]);

  const toggleIconSelector = () => {
    setIconSelectorVisible((prev) => !prev);
    setSearchValue('');
  };

  const handleIconSelect = (iconName: string) => {
    onChange(iconName);
    setIconSelectorVisible(false);
  };

  return (
    <div className={`relative ${className}`}>
      <Button
        onClick={toggleIconSelector}
        className={
          variant === 'square'
            ? 'flex h-14 w-14 items-center justify-center px-4 py-1 text-left'
            : 'flex h-10 w-full items-center justify-start gap-3 rounded-lg border-[var(--color-border)] bg-[var(--color-bg)] px-3'
        }
      >
        {value ? (
          <>
            <span className="flex items-center justify-center rounded-md bg-[var(--color-fill-2)] p-2">
              <Icon type={value} className="text-lg" />
            </span>
            {variant === 'compact' ? (
              <span className="truncate text-sm text-[var(--color-text-2)]">{value}</span>
            ) : null}
          </>
        ) : (
          <span className={variant === 'square' ? 'text-xs' : 'text-sm text-[var(--color-text-3)]'}>
            {t('system.application.selectIcon')}
          </span>
        )}
      </Button>

      {iconSelectorVisible && (
        <div
          ref={iconSelectorRef}
          className={
            variant === 'square'
              ? 'absolute left-0 z-50 mt-2 max-h-[300px] w-[360px] overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-lg'
              : 'absolute left-0 right-0 z-50 mt-2 max-h-[300px] overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-4 shadow-lg'
          }
        >
          <Input
            ref={searchInputRef}
            placeholder={t('system.application.searchIcon')}
            prefix={<SearchOutlined />}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            className="mb-3"
            allowClear
          />

          {filteredIcons.length > 0 ? (
            <div className="grid grid-cols-6 gap-2">
              {filteredIcons.map((icon) => (
                <Tooltip key={icon.font_class} title={icon.name}>
                  <button
                    type="button"
                    className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border p-2 transition-colors ${
                      value === icon.font_class
                        ? 'border-[var(--color-primary)] bg-[var(--color-bg-active)]'
                        : 'border-transparent hover:border-[var(--color-border-3)] hover:bg-[var(--color-bg-hover)]'
                    }`}
                    onClick={() => handleIconSelect(icon.font_class)}
                  >
                    <Icon
                      type={icon.font_class}
                      className="mb-1 h-[1em] w-[1em] overflow-hidden align-[-0.15em] text-xl"
                    />
                  </button>
                </Tooltip>
              ))}
            </div>
          ) : (
            <div className="py-4 text-center text-sm text-[var(--color-text-3)]">
              {t('system.application.noIconsFound')}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default IconFontSelector;
