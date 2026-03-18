'use client';

import React, { useMemo } from 'react';
import { TreeSelect } from 'antd';
import type { DefaultOptionType } from 'antd/es/select';
import { useTranslation } from '@/utils/i18n';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import styles from './index.module.scss';

interface CollectTaskOption {
  id: number | string;
  name: string;
  plugin?: string;
  category?: string;
  plugin_name?: string;
  category_name?: string;
}

interface CollectTaskTreeSelectProps {
  value?: string | number;
  onChange?: (value: string | undefined) => void;
  placeholder?: string;
  disabled?: boolean;
}

const buildTreeData = (tasks: CollectTaskOption[]): DefaultOptionType[] => {
  const categoryMap = new Map<
    string,
    {
      categoryLabel: string;
      plugins: Map<string, {
        pluginLabel: string;
        tasks: Array<{ value: string; title: string }>;
      }>;
    }
  >();

  tasks.forEach((task) => {
    if (task?.id === undefined || task?.id === null || !task?.name) {
      return;
    }

    const category = task.category || 'unknown';
    const categoryLabel = task.category_name || category;
    const plugin = task.plugin || 'unknown';
    const pluginLabel = task.plugin_name || plugin;
    const taskValue = String(task.id);

    if (!categoryMap.has(category)) {
      categoryMap.set(category, {
        categoryLabel,
        plugins: new Map(),
      });
    }

    const categoryEntry = categoryMap.get(category)!;
    if (!categoryEntry.plugins.has(plugin)) {
      categoryEntry.plugins.set(plugin, {
        pluginLabel,
        tasks: [],
      });
    }

    categoryEntry.plugins.get(plugin)!.tasks.push({
      value: taskValue,
      title: task.name,
    });
  });

  return Array.from(categoryMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, categoryEntry]) => ({
      value: `category:${category}`,
      title: categoryEntry.categoryLabel || category,
      selectable: false,
      children: Array.from(categoryEntry.plugins.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([plugin, pluginEntry]) => ({
          value: `plugin:${category}:${plugin}`,
          title: pluginEntry.pluginLabel || plugin,
          selectable: false,
          children: [...pluginEntry.tasks].sort((a, b) => a.title.localeCompare(b.title)),
        })),
    }));
};

const CollectTaskTreeSelect: React.FC<CollectTaskTreeSelectProps> = ({
  value,
  onChange,
  placeholder,
  disabled = false,
}) => {
  const { t } = useTranslation();
  const taskOptions = useAssetDataStore((state) => state.collectTaskOptions);

  const treeData = useMemo(() => buildTreeData(taskOptions), [taskOptions]);

  return (
    <TreeSelect
      popupClassName={styles.collectTaskTreeSelect}
      treeData={treeData}
      value={value == null || value === '' ? undefined : String(value)}
      onChange={(nextValue) => onChange?.(nextValue ? String(nextValue) : undefined)}
      placeholder={placeholder || t('pleaseSelect')}
      disabled={disabled}
      loading={false}
      allowClear
      showSearch
      treeDefaultExpandAll={false}
      treeNodeFilterProp="title"
      dropdownStyle={{ maxHeight: 360, overflow: 'auto' }}
      style={{ width: '100%' }}
    />
  );
};

export default CollectTaskTreeSelect;
