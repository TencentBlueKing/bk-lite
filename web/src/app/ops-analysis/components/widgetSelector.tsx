import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Modal, Menu, List, Input, Spin, Empty, Tag, message } from 'antd';
import { ApartmentOutlined, DatabaseOutlined, LockOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  ComponentSelectorProps,
  type ComponentSelectorConfigItem,
} from '@/app/ops-analysis/types/dashBoard';
import { TagItem } from '@/app/ops-analysis/types/namespace';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import { SCENE_WIDGETS } from '@/app/ops-analysis/constants/sceneWidgets';
import { isSceneWidgetAllowedOnSurface } from '@/app/ops-analysis/types/sceneWidgetCapability';
import {
  filterChartTypesForSurface,
  hasSupportedChartTypeForSurface,
} from '@/app/ops-analysis/utils/chartTypeSurface';
import styles from './widgetSelector.module.scss';
import type {
  DatasourceItem,
  ChartType,
} from '@/app/ops-analysis/types/dataSource';

/** 左侧目录的全量项。不是标签 id，请求时不传 tags。 */
const ALL_DATA_SOURCE_TAG = 'all';

type SelectedDataSourceTag = number | typeof ALL_DATA_SOURCE_TAG;

const ComponentSelector: React.FC<ComponentSelectorProps> = ({
  visible,
  onCancel,
  onOpenConfig,
  onPickSource,
  surface = 'dashboard',
  hideSceneWidgets = false,
}) => {
  const { t } = useTranslation();
  const [searchValue, setSearchValue] = useState('');
  const [searchKey, setSearchKey] = useState('');
  const [selectedTagId, setSelectedTagId] = useState<SelectedDataSourceTag>(ALL_DATA_SOURCE_TAG);
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
  // 当前列表对应的目录和已生效关键字。关闭弹窗只清输入，不会自动重取。
  const loadedListQueryRef = useRef<{
    tagId: SelectedDataSourceTag;
    searchKey: string;
  } | null>(null);

  const { getDataSourceBriefList } = useDataSourceApi();
  const { getTagList } = useNamespaceApi();

  const chartTypeLabels: Record<string, string> = {
    line: t('dataSource.lineChart'),
    bar: t('dataSource.barChart'),
    pie: t('dataSource.pieChart'),
    single: t('dataSource.singleValue'),
    multiValue: t('dataSource.multiValue'),
    gauge: t('dataSource.gauge'),
    table: t('dataSource.table'),
    eventTable: t('dataSource.eventTable'),
    eventTimeline: t('dashboard.eventTimeline'),
    cardList: t('dataSource.cardList'),
    message: t('dataSource.eventTable'),
    topN: t('dataSource.topN'),
    radar: t('dashboard.radar'),
    topologyMap: t('dataSource.topologyMap'),
    nodeGraph: t('dataSource.nodeGraph'),
    room3D: t('dataSource.room3D'),
  };

  const getChartTags = (chartTypes: ChartType[]) => {
    const visibleChartTypes = filterChartTypesForSurface(chartTypes, surface) as ChartType[];
    if (!visibleChartTypes?.length) return null;
    return (
      <div className="flex gap-1.5 flex-wrap pt-0.5">
        {visibleChartTypes.map((type, index) => (
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
    if (surface === 'report' && selectorMode !== 'dataSource') {
      setSelectorMode('dataSource');
    }
  }, [selectorMode, surface]);

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
      return;
    }

    setHoveredDatasourceId(null);
    setSearchValue('');
    setSearchKey('');
    if (loadedListQueryRef.current?.searchKey) {
      loadedListQueryRef.current = null;
      setCurrentDataSources([]);
      setDataSourcesLoading(true);
      return;
    }
    // 搜索还没回来时，列表仍是未搜索结果。丢掉这次请求后要把加载态收回。
    setDataSourcesLoading(false);
  }, [getTagList, visible]);

  useEffect(() => {
    if (!visible) {
      return;
    }

    const search = searchKey.trim();
    const loaded = loadedListQueryRef.current;
    if (loaded?.tagId === selectedTagId && loaded.searchKey === search) {
      return;
    }

    let ignore = false;
    const fetchBriefList = async () => {
      try {
        setDataSourcesLoading(true);
        const response = await getDataSourceBriefList({
          ...(selectedTagId === ALL_DATA_SOURCE_TAG ? {} : { tags: selectedTagId }),
          search: search || undefined,
          page_size: -1,
        });
        if (ignore) return;
        setCurrentDataSources(Array.isArray(response) ? response : []);
        loadedListQueryRef.current = { tagId: selectedTagId, searchKey: search };
      } catch (error) {
        if (ignore) return;
        console.error('获取数据源候选列表失败:', error);
        setCurrentDataSources([]);
        loadedListQueryRef.current = null;
      } finally {
        if (!ignore) setDataSourcesLoading(false);
      }
    };

    void fetchBriefList();
    return () => {
      ignore = true;
    };
  }, [getDataSourceBriefList, searchKey, selectedTagId, visible]);

  const applySearch = (value: string) => {
    setSearchValue(value);
    setSearchKey(value.trim());
  };

  const handleTagSelect = (tagItemId: SelectedDataSourceTag) => {
    setSelectedTagId(tagItemId);
    applySearch('');
  };

  const handleModeChange = (mode: 'dataSource' | 'sceneWidget') => {
    setSelectorMode(mode);
    applySearch('');
    setHoveredDatasourceId(null);
  };

  const handleConfig = (item: DatasourceItem) => {
    if (onPickSource) {
      onPickSource(item);
      return;
    }
    if (!hasSupportedChartTypeForSurface(item.chart_type || [], surface)) {
      message.warning(t('dashboard.sourceHasNoChart'));
      return;
    }
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
          SCENE_WIDGETS.filter((item) =>
            isSceneWidgetAllowedOnSurface(item.type, surface),
          ).map((item) => [
            item.category,
            {
              key: item.category,
              label: t(item.categoryNameKey),
              icon: <ApartmentOutlined />,
            },
          ]),
        ).values(),
      ),
    [surface, t],
  );

  const filteredSceneWidgets = useMemo(
    () =>
      SCENE_WIDGETS.filter(
        (item) =>
          item.category === selectedSceneCategory &&
          isSceneWidgetAllowedOnSurface(item.type, surface),
      ),
    [selectedSceneCategory, surface],
  );

  // 加载态和列表是同一个位置的 div。复用节点时浏览器会把上一次的 scrollTop 恢复回来，所以分类一变就换新节点。
  const listScrollKey = selectorMode === 'sceneWidget'
    ? `scene:${selectedSceneCategory}`
    : `source:${selectedTagId}`;

  const menuItems = selectorMode === 'sceneWidget'
    ? sceneCategories
    : [
      { key: ALL_DATA_SOURCE_TAG, label: t('dashboard.allDataSources') },
      ...tagList.map((tag) => ({
        key: tag.id,
        label: tag.name,
      })),
    ];

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
        {surface !== 'report' && !hideSceneWidgets && (
          <div className={styles.modeBar}>
            <button
              type="button"
              className={`${styles.modeButton} ${selectorMode === 'dataSource' ? styles.activeModeButton : ''}`}
              onClick={() => handleModeChange('dataSource')}
            >
              <DatabaseOutlined />
              {t('dashboard.dataSource')}
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
        )}

        <div className={styles.content}>
          <div className={styles.categoryPane} key={selectorMode}>
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
                    : [String(selectedTagId)]
                }
                items={menuItems}
                onSelect={({ key }) => {
                  if (selectorMode === 'sceneWidget') {
                    setSelectedSceneCategory(String(key));
                    return;
                  }
                  handleTagSelect(
                    String(key) === ALL_DATA_SOURCE_TAG
                      ? ALL_DATA_SOURCE_TAG
                      : Number(key),
                  );
                }}
                className="border-none [&_.ant-menu-item]:h-8 [&_.ant-menu-item]:leading-8 [&_.ant-menu-item]:mb-1 [&.ant-menu]:border-r-0"
                style={{
                  backgroundColor: 'transparent',
                  borderRight: 'none',
                }}
              />
            )}
          </div>

          <div className={styles.listPane}>
            {selectorMode === 'dataSource' && (
              <Input.Search
                allowClear
                value={searchValue}
                placeholder={t('common.search')}
                className={styles.search}
                onChange={(event) => {
                  const nextValue = event.target.value;
                  setSearchValue(nextValue);
                  if (!nextValue.trim()) {
                    setSearchKey('');
                  }
                }}
                onSearch={(value) => applySearch(value)}
                onClear={() => applySearch('')}
              />
            )}

            {selectorMode === 'sceneWidget' ? (
              <List
                key={listScrollKey}
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
                      } as unknown as ComponentSelectorConfigItem)
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
              <div key={listScrollKey} className={styles.loadingBox}>
                <Spin size="default" />
              </div>
            ) : (
              <div key={listScrollKey} className={styles.cardList}>
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
