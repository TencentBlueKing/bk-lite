import React, { useState, useEffect, useMemo } from 'react';
import { Modal, Menu, List, Input, Spin, Empty, Tag } from 'antd';
import { ApartmentOutlined, DatabaseOutlined, LockOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ComponentSelectorProps } from '@/app/ops-analysis/types/dashBoard';
import { TagItem } from '@/app/ops-analysis/types/namespace';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import { SCENE_WIDGETS } from '@/app/ops-analysis/constants/sceneWidgets';
import styles from './viewSelector.module.scss';
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
  const [selectorMode, setSelectorMode] = useState<'dataSource' | 'sceneWidget'>('dataSource');
  const [selectedSceneCategory, setSelectedSceneCategory] = useState<string>(
    SCENE_WIDGETS[0]?.category || '',
  );

  const { getDataSourceBriefList } = useDataSourceApi();
  const { getTagList } = useNamespaceApi();

  const chartTypeLabels: Record<string, string> = {
    line: t('dataSource.lineChart'),
    bar: t('dataSource.barChart'),
    pie: t('dataSource.pieChart'),
    single: t('dataSource.singleValue'),
    gauge: t('dataSource.gauge'),
    table: t('dataSource.table'),
    eventTable: t('dataSource.eventTable'),
    message: t('dataSource.eventTable'),
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

  const handleModeChange = (mode: 'dataSource' | 'sceneWidget') => {
    setSelectorMode(mode);
    setSearch('');
    setHoveredDatasourceId(null);
  };

  const handleConfig = (item: DatasourceItem) => {
    onOpenConfig?.({
      ...item,
      dataSource: item.id,
      chartType: '',
      defaultWidth: 4,
      defaultHeight: 3,
    });
  };

  const sceneCategories = useMemo(
    () =>
      Array.from(
        new Map(
          SCENE_WIDGETS.map((item) => [
            item.category,
            {
              key: item.category,
              label: t(item.categoryNameKey),
              icon: <ApartmentOutlined />,
            },
          ]),
        ).values(),
      ),
    [t],
  );

  const filteredSceneWidgets = useMemo(
    () =>
      SCENE_WIDGETS.filter((item) => item.category === selectedSceneCategory),
    [selectedSceneCategory],
  );

  const menuItems = selectorMode === 'sceneWidget'
    ? sceneCategories
    : tagList.map((tag) => ({
      key: tag.id,
      label: tag.name,
    }));

  return (
    <Modal
      title={t('dashboard.title')}
      open={visible}
      onCancel={onCancel}
      footer={null}
      width={760}
      style={{ top: '14%' }}
      styles={{ body: { height: '56vh', overflow: 'hidden' } }}
    >
      <div className={styles.selector}>
        <div className={styles.modeBar}>
          <button
            type="button"
            className={`${styles.modeButton} ${selectorMode === 'dataSource' ? styles.activeModeButton : ''}`}
            onClick={() => handleModeChange('dataSource')}
          >
            <DatabaseOutlined />
            {t('dashboard.dataComponents')}
          </button>
          <button
            type="button"
            className={`${styles.modeButton} ${selectorMode === 'sceneWidget' ? styles.activeModeButton : ''}`}
            onClick={() => handleModeChange('sceneWidget')}
          >
            <ApartmentOutlined />
            {t('dashboard.sceneComponents')}
          </button>
        </div>

        <div className={styles.content}>
          <div className={styles.categoryPane}>
            <div className={styles.categoryTitle}>
              {selectorMode === 'sceneWidget'
                ? t('dashboard.sceneComponents')
                : t('dashboard.dataComponents')}
            </div>
            {tagsLoading && selectorMode === 'dataSource' ? (
              <div className={styles.loadingBox}>
                <Spin size="small" />
              </div>
            ) : (
              <Menu
                mode="vertical"
                selectedKeys={
                  selectorMode === 'sceneWidget'
                    ? [selectedSceneCategory]
                    : selectedTagId ? [selectedTagId.toString()] : []
                }
                items={menuItems}
                onSelect={({ key }) => {
                  if (selectorMode === 'sceneWidget') {
                    setSelectedSceneCategory(String(key));
                    return;
                  }
                  handleTagSelect(Number(key));
                }}
                className="border-none [&_.ant-menu-item]:h-8 [&_.ant-menu-item]:leading-8 [&_.ant-menu-item]:mb-1 [&.ant-menu]:border-r-0"
                style={{
                  backgroundColor: 'transparent',
                  borderRight: 'none',
                }}
                theme="light"
              />
            )}
          </div>

          <div className={styles.listPane}>
            {selectorMode === 'dataSource' && (
              <Input.Search
                placeholder={t('common.search')}
                allowClear
                className={styles.search}
                onSearch={(value) => setSearch(value)}
                onClear={() => setSearch('')}
              />
            )}

            {selectorMode === 'sceneWidget' ? (
              <List
                size="small"
                className={styles.cardList}
                dataSource={filteredSceneWidgets}
                renderItem={(item) => (
                  <List.Item
                    className={styles.sceneCard}
                    onClick={() =>
                      onOpenConfig?.({
                        id: `scene:${item.type}`,
                        name: t(item.nameKey),
                        desc: t(item.descriptionKey),
                        chart_type: [],
                        chartType: item.type,
                        sceneWidgetType: item.type,
                        defaultWidth: item.defaultWidth,
                        defaultHeight: item.defaultHeight,
                      } as any)
                    }
                  >
                    <div className={styles.cardIcon}>
                      <ApartmentOutlined />
                    </div>
                    <div className={styles.cardBody}>
                      <span className={styles.cardTitle}>{t(item.nameKey)}</span>
                      <span className={styles.cardDesc}>{t(item.descriptionKey)}</span>
                    </div>
                  </List.Item>
                )}
              />
            ) : dataSourcesLoading ? (
              <div className={styles.loadingBox}>
                <Spin size="default" />
              </div>
            ) : (
              <div className={styles.cardList}>
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
                      className={`${styles.dataCard} ${item.hasAuth === false ? styles.disabledCard : ''}`}
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
                      data-active={hoveredDatasourceId === item.id}
                    >
                      <div className={styles.cardBody}>
                        <div className={styles.dataTitleRow}>
                          <span className={styles.cardTitle}>
                            {item.name}
                            {item.rest_api && (
                              <span className={styles.apiText}>
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
                          <span className={styles.cardDesc}>{item.desc}</span>
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
      </div>
    </Modal>
  );
};

export default ComponentSelector;
