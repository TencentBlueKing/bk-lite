'use client';

import React from 'react';
import { Button, Input, Select } from 'antd';
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

interface SelectOption {
  label: string;
  value: string;
}

interface OpenApiDocsToolbarProps {
  query: string;
  onQueryChange: (value: string) => void;
  serviceFilter: string;
  onServiceFilterChange: (value: string) => void;
  methodFilter: string;
  onMethodFilterChange: (value: string) => void;
  kindFilter: string;
  onKindFilterChange: (value: string) => void;
  serviceOptions: SelectOption[];
  methodOptions: SelectOption[];
  kindOptions: SelectOption[];
  hasActiveFilters: boolean;
  onResetFilters: () => void;
  exporting: boolean;
  loading: boolean;
  filteredCount: number;
  onExport: () => void;
  onRefresh: () => void;
}

const OpenApiDocsToolbar: React.FC<OpenApiDocsToolbarProps> = ({
  query,
  onQueryChange,
  serviceFilter,
  onServiceFilterChange,
  methodFilter,
  onMethodFilterChange,
  kindFilter,
  onKindFilterChange,
  serviceOptions,
  methodOptions,
  kindOptions,
  hasActiveFilters,
  onResetFilters,
  exporting,
  loading,
  filteredCount,
  onExport,
  onRefresh,
}) => {
  const { t } = useTranslation();

  return (
    <FilterToolbar
      align="between"
      className="border-b border-[var(--color-border-1)] pb-3"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <Input
          allowClear
          prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
          className="w-72"
          placeholder={t('system.settings.openapiDocs.searchPlaceholder')}
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
        />
        <Select
          className="w-36"
          value={serviceFilter}
          onChange={onServiceFilterChange}
          options={serviceOptions}
        />
        <Select
          className="w-28"
          value={methodFilter}
          onChange={onMethodFilterChange}
          options={methodOptions}
        />
        <Select
          className="w-28"
          value={kindFilter}
          onChange={onKindFilterChange}
          options={kindOptions}
        />
        {hasActiveFilters && (
          <Button type="link" size="small" onClick={onResetFilters}>
            {t('system.settings.openapiDocs.resetFilter')}
          </Button>
        )}
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          loading={exporting}
          disabled={!filteredCount || loading}
          onClick={onExport}
        >
          {t('system.settings.openapiDocs.exportPdf')}
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-[var(--color-text-3)]">
          {t('system.settings.openapiDocs.totalCount', undefined, { count: filteredCount })}
        </span>
        <Button
          type="text"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={onRefresh}
          aria-label={t('common.refresh')}
          title={t('common.refresh')}
        />
      </div>
    </FilterToolbar>
  );
};

export default OpenApiDocsToolbar;
