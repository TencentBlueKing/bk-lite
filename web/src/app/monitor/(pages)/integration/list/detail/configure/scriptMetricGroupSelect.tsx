'use client';

import React, { useMemo, useState } from 'react';
import { Button, Divider, Input, Select, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import {
  CatalogMetricGroupOption,
  catalogGroupLabel,
  createCatalogMetricGroup,
  dedupeCatalogMetricGroups
} from './scriptMetricPersist';

interface ScriptMetricGroupSelectProps {
  value?: number;
  onChange?: (value: number | null) => void;
  groups: CatalogMetricGroupOption[];
  onGroupsChange?: (groups: CatalogMetricGroupOption[]) => void;
  onCreated?: (group: CatalogMetricGroupOption & { id: number }) => void;
  objectId?: string | number;
  pluginId?: string | number;
  disabled?: boolean;
  size?: 'small' | 'middle' | 'large';
  placeholder?: string;
  allowClear?: boolean;
  className?: string;
  loading?: boolean;
  onSearch?: (value: string) => void;
  filterOption?: boolean | ((input: string, option?: { label?: string }) => boolean);
}

const ScriptMetricGroupSelect: React.FC<ScriptMetricGroupSelectProps> = ({
  value,
  onChange,
  groups,
  onGroupsChange,
  onCreated,
  objectId,
  pluginId,
  disabled,
  size,
  placeholder,
  allowClear = true,
  className,
  loading,
  onSearch,
  filterOption = true
}) => {
  const { t } = useTranslation();
  const { post } = useApiClient();
  const [newName, setNewName] = useState('');
  const [searchText, setSearchText] = useState('');
  const [creating, setCreating] = useState(false);
  const canCreate = Boolean(objectId && pluginId) && !disabled;
  const uniqueGroups = useMemo(
    () =>
      dedupeCatalogMetricGroups(groups, { preferredPluginId: pluginId }).groups,
    [groups, pluginId]
  );
  const trimmedSearch = searchText.trim();
  const searchHasMatch =
    !trimmedSearch ||
    uniqueGroups.some((group) =>
      catalogGroupLabel(group).toLowerCase().includes(trimmedSearch.toLowerCase())
    );
  const showCreateFromSearch = canCreate && !!trimmedSearch && !searchHasMatch;
  const createNameReady = !!newName.trim() && !creating;

  const handleCreate = async (rawName?: string) => {
    const trimmed = String(rawName ?? newName).trim();
    if (!trimmed || !objectId || !pluginId || creating) {
      return;
    }
    const existing = uniqueGroups.find(
      (group) =>
        catalogGroupLabel(group).toLowerCase() === trimmed.toLowerCase() ||
        String(group.name || '').trim().toLowerCase() === trimmed.toLowerCase()
    );
    if (typeof existing?.id === 'number') {
      onChange?.(existing.id);
      setNewName('');
      setSearchText('');
      return;
    }
    setCreating(true);
    try {
      const created = await createCatalogMetricGroup({
        post,
        objectId,
        pluginId,
        name: trimmed
      });
      const nextGroups = uniqueGroups.some((group) => group.id === created.id)
        ? uniqueGroups
        : [...uniqueGroups, created];
      onGroupsChange?.(nextGroups);
      onChange?.(created.id);
      onCreated?.(created);
      setNewName('');
      setSearchText('');
      message.success(t('common.successfullyAdded'));
    } catch {
      message.error(t('common.operationFailed'));
    } finally {
      setCreating(false);
    }
  };

  return (
    <Select
      size={size}
      allowClear={allowClear}
      showSearch
      disabled={disabled}
      loading={loading || creating}
      optionFilterProp="label"
      filterOption={
        filterOption === false
          ? false
          : typeof filterOption === 'function'
            ? filterOption
            : true
      }
      className={className}
      placeholder={placeholder}
      value={value}
      searchValue={searchText}
      onChange={(next) => {
        setSearchText('');
        onChange?.(typeof next === 'number' ? next : null);
      }}
      onSearch={(text) => {
        setSearchText(text);
        onSearch?.(text);
      }}
      notFoundContent={
        showCreateFromSearch ? (
          <Button
            type="link"
            size="small"
            className="h-auto px-1"
            loading={creating}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => void handleCreate(trimmedSearch)}
          >
            {t(
              'monitor.integrations.createMetricGroupFromSearch',
              '新建『{name}』',
              { name: trimmedSearch }
            )}
          </Button>
        ) : undefined
      }
      options={uniqueGroups.map((group) => ({
        value: group.id as number,
        label: catalogGroupLabel(group) || String(group.id)
      }))}
      dropdownRender={(menu) => (
        <>
          {menu}
          {canCreate ? (
            <>
              <Divider className="my-2" />
              <div
                className="flex items-center gap-1 px-2 pb-1"
                onMouseDown={(event) => event.preventDefault()}
              >
                <Input
                  size="small"
                  value={newName}
                  disabled={creating}
                  className="min-w-0 flex-1"
                  placeholder={t(
                    'monitor.integrations.createMetricGroupPlaceholder',
                    '输入分组名'
                  )}
                  onChange={(event) => setNewName(event.target.value)}
                  onPressEnter={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    void handleCreate();
                  }}
                />
                <Button
                  size="small"
                  type="link"
                  className="h-auto shrink-0 px-1"
                  icon={<PlusOutlined />}
                  loading={creating}
                  disabled={!createNameReady}
                  onClick={() => void handleCreate()}
                >
                  {t('monitor.integrations.createMetricGroup', '新建分组')}
                </Button>
              </div>
            </>
          ) : null}
        </>
      )}
    />
  );
};

export default ScriptMetricGroupSelect;
