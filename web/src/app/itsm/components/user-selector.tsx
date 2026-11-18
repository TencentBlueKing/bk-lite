'use client';

import UserAvatar from '@/components/user-avatar';
import { Select } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';

interface UserOption {
  label: string;
  value: string;
}

interface UserSelectorProps {
  value?: string[];
  onChange?: (value: string[]) => void;
  multiple?: boolean;
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  allowClear?: boolean;
}

const PAGE_SIZE = 10;

export function UserSelector({ value = [], onChange, multiple = true, placeholder, disabled, ariaLabel, allowClear = false }: UserSelectorProps) {
  const { t } = useTranslation();
  const api = useItsmApi();
  const [opened, setOpened] = useState(false);
  const [options, setOptions] = useState<UserOption[]>([]);
  const [loading, setLoading] = useState(false);
  const pageRef = useRef(1);
  const totalRef = useRef(0);
  const keywordRef = useRef('');
  const loadingRef = useRef(false);
  const requestRef = useRef(0);

  const load = (page: number, keyword: string, append: boolean) => {
    if (!api.ready || loadingRef.current) {
      return;
    }
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    loadingRef.current = true;
    setLoading(true);
    void api.searchUsers(keyword, page).then((data) => {
      if (requestId !== requestRef.current) {
        return;
      }
      const payload = data as { items?: Array<{ username: string; display_name: string }>; count?: number };
      const rows = (payload.items || []).map((item) => ({
        label: item.display_name && item.display_name !== item.username ? `${item.display_name} (${item.username})` : item.username,
        value: item.username,
      }));
      totalRef.current = payload.count || 0;
      pageRef.current = page;
      keywordRef.current = keyword;
      setOptions((current) => {
        const merged = append ? [...current, ...rows.filter((row) => !current.some((item) => item.value === row.value))] : rows;
        const selected = value
          .filter((item) => !merged.some((row) => row.value === item))
          .map((item) => ({ label: item, value: item }));
        return [...selected, ...merged];
      });
    }).catch(() => undefined).finally(() => {
      if (requestId === requestRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    });
  };

  useEffect(() => {
    if (!api.ready || !opened || disabled) {
      return;
    }
    load(1, '', false);
  }, [api.ready, api.searchUsers, opened, disabled]);

  return (
    <Select
      aria-label={ariaLabel}
      allowClear={allowClear}
      mode={multiple ? 'multiple' : undefined}
      showSearch
      className="w-full"
      placeholder={placeholder || t('itsm.admin.searchUser')}
      disabled={disabled}
      value={multiple ? value : value[0]}
      options={options}
      loading={loading}
      filterOption={false}
      onOpenChange={open => { if (open) setOpened(true); }}
      onSearch={(text) => {
        loadingRef.current = false;
        load(1, text.trim(), false);
      }}
      onPopupScroll={(event) => {
        const target = event.target as HTMLElement;
        if (loadingRef.current || options.length >= totalRef.current) {
          return;
        }
        if (target.scrollTop + target.clientHeight < target.scrollHeight - 8) {
          return;
        }
        load(pageRef.current + 1, keywordRef.current, true);
      }}
      onChange={(next) => {
        const picked = Array.isArray(next) ? next : next ? [String(next)] : [];
        onChange?.(picked.slice(0, multiple ? picked.length : 1));
      }}
      optionRender={(option) => (
        <span className="inline-flex items-center gap-2">
          <UserAvatar userName={String(option.value)} size="small" />
          {option.label}
        </span>
      )}
      notFoundContent={loading ? t('itsm.admin.loadingUsers') : t('itsm.admin.noUsers')}
    />
  );
}

export { PAGE_SIZE };
