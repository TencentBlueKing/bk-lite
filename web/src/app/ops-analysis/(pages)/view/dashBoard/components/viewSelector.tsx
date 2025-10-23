import React, { useState, useEffect } from 'react';
import { Modal, Menu, List, Input, Spin, Empty } from 'antd';
import {
  LineChartOutlined,
  BarChartOutlined,
  PieChartOutlined,
  NumberOutlined,
  DashboardOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ComponentSelectorProps } from '@/app/ops-analysis/types/dashBoard';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const ComponentSelector: React.FC<ComponentSelectorProps> = ({
  visible,
  onCancel,
  onOpenConfig,
}) => {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [selectedTagId, setSelectedTagId] = useState<number | null>(null);
  const [currentDataSources, setCurrentDataSources] = useState<
    DatasourceItem[]
  >([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);

  const { tagList, tagsLoading, fetchTags } = useOpsAnalysis();
  const { getDataSourceList } = useDataSourceApi();

  const getChartIcon = (chartTypes: any[]) => {
    const iconClass = 'text-[16px] text-[var(--color-primary)]';

    const iconMap = {
      line: <LineChartOutlined className={iconClass} />,
      bar: <BarChartOutlined className={iconClass} />,
      pie: <PieChartOutlined className={iconClass} />,
      single: <NumberOutlined className={iconClass} />,
    };

    if (!chartTypes?.length) {
      return (
        <DashboardOutlined className="text-[20px] text-[var(--color-primary)]" />
      );
    }

    const icons = chartTypes.map((type, index) => (
      <span key={index} className="inline-block">
        {iconMap[type as keyof typeof iconMap] || (
          <DashboardOutlined className={iconClass} />
        )}
      </span>
    ));

    return <div className="flex gap-1">{icons}</div>;
  };

  const fetchDataSourcesByTag = async (tagItemId: number) => {
    try {
      setDataSourcesLoading(true);
      const list = await getDataSourceList({ tags: tagItemId });
      setCurrentDataSources(list || []);
    } catch (error) {
      console.error('获取数据源列表失败:', error);
      setCurrentDataSources([]);
    } finally {
      setDataSourcesLoading(false);
    }
  };

  useEffect(() => {
    if (visible) {
      fetchTags();
    } else {
      setSelectedTagId(null);
      setCurrentDataSources([]);
      setSearch('');
    }
  }, [visible, fetchTags]);

  useEffect(() => {
    if (selectedTagId) {
      fetchDataSourcesByTag(selectedTagId);
    }
  }, [selectedTagId]);

  useEffect(() => {
    if (visible && tagList.length > 0 && !selectedTagId) {
      setSelectedTagId(tagList[0].id);
    }
  }, [visible, tagList, selectedTagId]);

  const filteredDataSources = currentDataSources.filter(
    (item: DatasourceItem) =>
      item.name.toLowerCase().includes(search.toLowerCase())
  );

  const handleTagSelect = (tagItemId: number) => {
    setSelectedTagId(tagItemId);
    setSearch('');
  };

  const handleConfig = (item: DatasourceItem) => {
    onOpenConfig?.(item);
    onCancel();
  };

  const menuItems = tagList.map((tag) => ({
    key: tag.id,
    label: tag.name,
  }));

  return (
    <Modal
      title={t('dashboard.title')}
      open={visible}
      onCancel={onCancel}
      footer={null}
      width={680}
      style={{ top: '16%' }}
      styles={{ body: { height: '50vh', overflowY: 'hidden' } }}
    >
      <div className="h-full flex mt-2">
        {/* 左侧标签菜单 */}
        <div className="w-44 border-r border-gray-200 pr-4">
          {tagsLoading ? (
            <div className="flex justify-center py-8 mt-10">
              <Spin size="small" />
            </div>
          ) : (
            <div className="max-h-96 overflow-y-auto">
              <Menu
                mode="vertical"
                selectedKeys={selectedTagId ? [selectedTagId.toString()] : []}
                items={menuItems}
                onSelect={({ key }) => handleTagSelect(Number(key))}
                className="border-none [&_.ant-menu-item]:h-8 [&_.ant-menu-item]:leading-8 [&_.ant-menu-item]:mb-1 [&.ant-menu]:border-r-0"
                style={{
                  backgroundColor: 'transparent',
                  borderRight: 'none',
                }}
                theme="light"
              />
            </div>
          )}
        </div>

        {/* 右侧数据源列表 */}
        <div className="flex-1 pl-4">
          <Input.Search
            placeholder={t('common.search')}
            allowClear
            className="mb-4"
            onSearch={(value) => setSearch(value)}
            onClear={() => setSearch('')}
          />

          {dataSourcesLoading ? (
            <div className="flex justify-center py-8 mt-10">
              <Spin size="default" />
            </div>
          ) : (
            <div className="h-96 overflow-y-auto">
              <List
                size="small"
                dataSource={filteredDataSources}
                locale={{
                  emptyText: (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('common.noData')}
                    />
                  ),
                }}
                renderItem={(item: DatasourceItem) => (
                  <List.Item
                    className="cursor-pointer hover:bg-blue-50 flex items-center gap-3 justify-between p-3 border border-gray-200 rounded mb-2 last:mb-0"
                    onClick={() => handleConfig(item)}
                  >
                    <div className="flex flex-col gap-1 leading-relaxed">
                      <span className="font-medium leading-5">{item.name}</span>
                      <span className="text-xs text-[var(--color-text-2)] leading-4">
                        {item.desc || '--'}
                      </span>
                    </div>
                    {getChartIcon(item.chart_type)}
                  </List.Item>
                )}
              />
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default ComponentSelector;
