import React, { useState, useEffect } from 'react';
import { Modal, Menu, List, Input, Spin, Empty, Tag } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ComponentSelectorProps } from '@/app/ops-analysis/types/dashBoard';
import { TagItem } from '@/app/ops-analysis/types/namespace';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import type {
  DatasourceItem,
  ChartType,
} from '@/app/ops-analysis/types/dataSource';

const ComponentSelector: React.FC<ComponentSelectorProps> = ({
  visible,
  onCancel,
  onOpenConfig,
}) => {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [selectedTagId, setSelectedTagId] = useState<number | null>(null);
  const [hoveredDatasourceId, setHoveredDatasourceId] = useState<number | null>(
    null,
  );
  const [currentDataSources, setCurrentDataSources] = useState<
    DatasourceItem[]
  >([]);
  const [tagList, setTagList] = useState<TagItem[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);

  const { getDataSourceBriefList } = useDataSourceApi();
  const { getTagList } = useNamespaceApi();

  const chartTypeLabels: Record<string, string> = {
    line: t('dataSource.lineChart'),
    bar: t('dataSource.barChart'),
    pie: t('dataSource.pieChart'),
    single: t('dataSource.singleValue'),
    gauge: t('dataSource.gauge'),
    table: t('dataSource.table'),
    message: t('dataSource.message'),
    topN: t('dataSource.topN'),
  };

  const getChartTags = (chartTypes: ChartType[]) => {
    if (!chartTypes?.length) return null;
    return (
      <div className="flex gap-1.5 flex-wrap pt-0.5">
        {chartTypes.map((type, index) => (
          <Tag
            key={index}
            bordered={false}
            className="m-0 rounded-full border border-(--color-border-3) bg-(--color-fill-3) px-2 py-0 text-xs font-medium leading-5 text-(--color-text-2) shadow-sm"
          >
            {chartTypeLabels[type] || type}
          </Tag>
        ))}
      </div>
    );
  };

  useEffect(() => {
    const fetchTags = async () => {
      try {
        setTagsLoading(true);
        const response = await getTagList({ page_size: -1 });
        setTagList(Array.isArray(response) ? response : []);
      } catch (error) {
        console.error('获取标签列表失败:', error);
        setTagList([]);
      } finally {
        setTagsLoading(false);
      }
    };

    if (visible) {
      if (tagList.length === 0) {
        void fetchTags();
      }
    } else {
      setHoveredDatasourceId(null);
      setSearch('');
    }
  }, [getTagList, visible]);

  useEffect(() => {
    const fetchBriefList = async () => {
      if (!selectedTagId) {
        setCurrentDataSources([]);
        return;
      }

      try {
        setDataSourcesLoading(true);
        const response = await getDataSourceBriefList({
          tags: selectedTagId,
          search: search.trim() || undefined,
          page_size: -1,
        });
        setCurrentDataSources(Array.isArray(response) ? response : []);
      } catch (error) {
        console.error('获取数据源候选列表失败:', error);
        setCurrentDataSources([]);
      } finally {
        setDataSourcesLoading(false);
      }
    };

    if (visible && selectedTagId) {
      void fetchBriefList();
    }
  }, [getDataSourceBriefList, search, selectedTagId]);

  useEffect(() => {
    if (visible && tagList.length > 0 && !selectedTagId) {
      setSelectedTagId(tagList[0].id);
    }
  }, [visible, tagList, selectedTagId]);

  const handleTagSelect = (tagItemId: number) => {
    setSelectedTagId(tagItemId);
    setSearch('');
  };

  const handleConfig = (item: DatasourceItem) => {
    onOpenConfig?.(item);
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
      width={700}
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
                dataSource={currentDataSources}
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
                    className={`flex items-center gap-3 justify-between p-3 rounded mb-2 last:mb-0 transition-colors ${item.hasAuth === false ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
                    style={{
                      border: '1px solid var(--color-border-1)',
                      backgroundColor:
                        hoveredDatasourceId === item.id
                          ? 'var(--color-fill-2)'
                          : 'var(--color-fill-1)',
                    }}
                    onMouseEnter={() => {
                      if (item.hasAuth !== false) {
                        setHoveredDatasourceId(item.id);
                      }
                    }}
                    onMouseLeave={() => {
                      if (hoveredDatasourceId === item.id) {
                        setHoveredDatasourceId(null);
                      }
                    }}
                    onClick={() => item.hasAuth !== false && handleConfig(item)}
                  >
                    <div className="flex flex-col gap-1 leading-relaxed w-full">
                      <div className="flex items-center gap-2">
                        <span className="font-medium leading-5 text-(--color-text-1) break-all">
                          {item.name}
                          {item.rest_api && (
                            <span className="font-normal text-xs text-gray-400 ml-1">
                              ({item.rest_api})
                            </span>
                          )}
                        </span>
                        {item.hasAuth === false && (
                          <Tag icon={<LockOutlined />} color="warning">
                            {t('common.noAuth')}
                          </Tag>
                        )}
                      </div>
                      {item.desc ? (
                        <span className="text-xs text-(--color-text-2) leading-4">
                          {item.desc}
                        </span>
                      ) : null}
                      {getChartTags(item.chart_type)}
                    </div>
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
