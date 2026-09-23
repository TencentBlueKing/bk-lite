'use client';

import React, { useMemo, useState, type ReactNode } from 'react';
import { Empty, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import ListPageHeader from '@/components/list-page-header';

const { Search } = Input;

function defaultSearchText<T>(item: T): string {
  const name = (item as { name?: unknown }).name;
  return typeof name === 'string' ? name : '';
}

interface SystemManagerEntityGridProps<T> {
  title?: string;
  description?: string;
  items: T[];
  loading?: boolean;
  search?: boolean;
  searchPlaceholder?: string;
  onSearch?: (value: string) => void;
  getSearchText?: (item: T) => string;
  actions?: ReactNode;
  emptyDescription?: string;
  emptySearchDescription?: string;
  emptyAction?: ReactNode;
  getItemKey: (item: T) => React.Key;
  renderCard: (item: T) => ReactNode;
  gridClassName?: string;
  compactSkeleton?: boolean;
}

export default function SystemManagerEntityGrid<T>({
  title,
  description,
  items,
  loading = false,
  search = true,
  searchPlaceholder,
  onSearch,
  getSearchText = defaultSearchText,
  actions,
  emptyDescription,
  emptySearchDescription,
  emptyAction,
  getItemKey,
  renderCard,
  gridClassName = 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5',
  compactSkeleton = false,
}: SystemManagerEntityGridProps<T>) {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    onSearch?.(value);
  };

  const filteredItems = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) return items;
    return items.filter((item) => getSearchText(item).toLowerCase().includes(keyword));
  }, [getSearchText, items, searchTerm]);

  const toolbar = (search || actions) ? (
    <>
      {search ? (
        <Search
          allowClear
          enterButton
          className="w-60"
          placeholder={searchPlaceholder || `${t('common.search')}...`}
          onSearch={handleSearch}
          defaultValue={searchTerm}
        />
      ) : null}
      {actions}
    </>
  ) : null;

  const keyword = searchTerm.trim();
  const emptyText = keyword
    ? (emptySearchDescription || emptyDescription || t('common.noData'))
    : (emptyDescription || t('common.noData'));

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      {title ? (
        <ListPageHeader title={title} description={description} actions={toolbar} />
      ) : toolbar ? (
        <div className="mb-4 flex flex-wrap items-center justify-end gap-2">{toolbar}</div>
      ) : null}

      {loading ? (
        <CardGridSkeleton className={gridClassName} compact={compactSkeleton} />
      ) : filteredItems.length === 0 ? (
        <div className="flex min-h-[240px] flex-1 items-center justify-center">
          <Empty
            className="!my-0"
            description={<span className="text-sm text-[var(--color-text-3)]">{emptyText}</span>}
          >
            {keyword ? null : emptyAction}
          </Empty>
        </div>
      ) : (
        <div className={`grid gap-4 ${gridClassName}`}>
          {filteredItems.map((item) => (
            <div key={getItemKey(item)} className="h-full">
              {renderCard(item)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
