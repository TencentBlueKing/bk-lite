'use client';

import React from 'react';
import { Input, Select, Button } from 'antd';
import { SearchOutlined, UndoOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface FilterBarProps {
  search: string;
  onSearch: (value: string) => void;
  typeFilter: string;
  onTypeFilter: (value: string) => void;
  statusFilter: string;
  onStatusFilter: (value: string) => void;
  onReset: () => void;
}

const FilterBar: React.FC<FilterBarProps> = ({
  search,
  onSearch,
  typeFilter,
  onTypeFilter,
  statusFilter,
  onStatusFilter,
  onReset,
}) => {
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-3 mb-[18px]">
      <Input
        value={search}
        onChange={e => onSearch(e.target.value)}
        placeholder={t('integration.searchPlaceholder')}
        prefix={<SearchOutlined className="text-[var(--color-text-4)]" />}
        className="!w-[220px]"
        allowClear
      />

      <div className="flex items-center gap-[6px]">
        <span className="text-[13px] text-[var(--color-text-2)]">{t('integration.integrationType')}</span>
        <Select
          value={typeFilter}
          onChange={onTypeFilter}
          className="!min-w-[90px]"
          options={[
            { value: 'all', label: t('integration.typeAll') },
            { value: 'push', label: 'Push' },
            { value: 'pull', label: 'Pull' },
            { value: 'agent', label: 'Agent' },
          ]}
        />
      </div>

      <div className="flex items-center gap-[6px]">
        <span className="text-[13px] text-[var(--color-text-2)]">{t('integration.statusFilter')}</span>
        <Select
          value={statusFilter}
          onChange={onStatusFilter}
          className="!min-w-[90px]"
          options={[
            { value: 'all', label: t('integration.statusAll') },
            { value: 'healthy', label: t('integration.statusHealthy') },
            { value: 'warning', label: t('integration.statusWarning') },
            { value: 'inactive', label: t('integration.statusInactive') },
          ]}
        />
      </div>

      <Button
        icon={<UndoOutlined />}
        onClick={onReset}
      >
        {t('integration.reset')}
      </Button>
    </div>
  );
};

export default FilterBar;
