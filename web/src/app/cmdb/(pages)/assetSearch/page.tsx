'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import assetSearchStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import { SearchOutlined } from '@ant-design/icons';
import { ArrowRightOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { AttrFieldType, UserItem } from '@/app/cmdb/types/assetManage';
import {
  AssetListItem,
  SearchStatsResponse,
  SearchByModelResponse,
  TabJsxItem,
  ModelStat,
  InstDetailItem,
} from '@/app/cmdb/types/assetSearch';
import {
  Spin,
  Input,
  Tabs,
  Button,
  Tag,
  Empty,
  Pagination,
  Checkbox,
} from 'antd';
import useApiClient from '@/utils/request';
import { useCommon } from '@/app/cmdb/context/common';
import { deepClone, getFieldItem } from '@/app/cmdb/utils/common';
import { useModelApi, useInstanceApi } from '@/app/cmdb/api';
const { Search } = Input;

const AssetSearch = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const commonContext = useCommon();

  const { getModelAttrList } = useModelApi();
  const { fulltextSearchStats, fulltextSearchByModel } = useInstanceApi();

  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const modelList = commonContext?.modelList || [];
  const [propertyList, setPropertyList] = useState<AttrFieldType[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [activeTab, setActiveTab] = useState<string>('');
  const [items, setItems] = useState<TabJsxItem[]>([]);
  const [showSearch, setShowSearch] = useState<boolean>(true);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [activeInstItem, setActiveInstItem] = useState<number>(-1);
  const [historyList, setHistoryList] = useState<string[]>([]);
  const [modelStats, setModelStats] = useState<ModelStat[]>([]);
  const [currentModelData, setCurrentModelData] = useState<AssetListItem[]>([]);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [caseSensitive, setCaseSensitive] = useState<boolean>(false);

  useEffect(() => {
    if (isLoading || !modelList.length) return;
  }, [isLoading, modelList]);

  useEffect(() => {
    const histories = localStorage.getItem('assetSearchHistory');
    if (histories) setHistoryList(JSON.parse(histories));
  }, []);

  useEffect(() => {
    if (propertyList.length && currentModelData.length) {
      const tabJsx = getInstDetial(currentModelData, propertyList);
      setItems(tabJsx);
    }
  }, [propertyList, currentModelData, activeInstItem, activeTab]);

  const handleTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const handleSearch = async () => {
    setShowSearch(!searchText);
    if (!searchText) return;

    const histories = deepClone(historyList);
    if (
      !histories.length ||
      (histories.length && !histories.includes(searchText))
    ) {
      histories.push(searchText);
    }
    localStorage.setItem('assetSearchHistory', JSON.stringify(histories));
    setHistoryList(histories);

    setPageLoading(true);
    try {
      const stats: SearchStatsResponse = await fulltextSearchStats({
        search: searchText,
        case_sensitive: caseSensitive,
      });

      if (!stats.model_stats || stats.model_stats.length === 0) {
        setModelStats([]);
        setCurrentModelData([]);
        setItems([]);
        setPropertyList([]);
        setActiveTab('');
        setActiveInstItem(-1);
        setTotalCount(0);
        setCurrentPage(1);
        setPageLoading(false);
        return;
      }

      setModelStats(stats.model_stats);

      const firstModelId = stats.model_stats[0].model_id;
      setActiveTab(firstModelId);
      setCurrentPage(1);

      await loadModelData(firstModelId, 1, pageSize);
    } catch (error) {
      console.error('Search failed:', error);
      setModelStats([]);
      setCurrentModelData([]);
      setItems([]);
      setPropertyList([]);
      setActiveTab('');
      setActiveInstItem(-1);
      setTotalCount(0);
      setCurrentPage(1);
      setPageLoading(false);
    }
  };

  const loadModelData = async (modelId: string, page: number, size: number) => {
    setPageLoading(true);
    try {
      const result: SearchByModelResponse = await fulltextSearchByModel({
        search: searchText,
        model_id: modelId,
        page: page,
        page_size: size,
        case_sensitive: caseSensitive,
      });

      setCurrentModelData(result.data || []);
      setTotalCount(result.total);

      const attrList = await getModelAttrList(modelId);
      setPropertyList(attrList);

      setActiveInstItem(result.data && result.data.length > 0 ? 0 : -1);
    } catch (error) {
      console.error('Load model data failed:', error);
      setCurrentModelData([]);
      setTotalCount(0);
      setActiveInstItem(-1);
    } finally {
      setPageLoading(false);
    }
  };

  const getInstDetial = (
    data: AssetListItem[],
    properties: AttrFieldType[]
  ) => {
    if (!data || data.length === 0) return [];

    const descItems: InstDetailItem[][] = data.map((desc: AssetListItem) => {
      const arr = Object.entries(desc)
        .map(([key, value]) => {
          return {
            key: key,
            label: properties.find((item) => item.attr_id === key)?.attr_name,
            children: value,
            id: desc._id,
          };
        })
        .filter((desc) => !!desc.label);
      return arr;
    });

    // 计算当前要显示的详情索引
    const detailIndex =
      activeInstItem >= 0 && activeInstItem < descItems.length
        ? activeInstItem
        : 0;
    const currentDetail =
      descItems.length > 0 ? descItems[detailIndex] || [] : [];

    const modelName =
      modelList.find((model) => model.model_id === activeTab)?.model_name ||
      activeTab;

    const result: TabJsxItem[] = [
      {
        key: activeTab,
        label: `${modelName}(${totalCount})`,
        children: (
          <div className={assetSearchStyle.searchResult}>
            <div
              className={assetSearchStyle.list}
              style={{
                display: 'flex',
                flexDirection: 'column',
                maxHeight: 'calc(100vh - 184px)',
                minHeight: 'calc(100vh - 184px)',
              }}
            >
              <div style={{ flex: 1, overflow: 'auto' }}>
                {descItems.map((target: InstDetailItem[], index: number) => (
                  <div
                    key={index}
                    className={`${assetSearchStyle.listItem} ${
                      index === activeInstItem ? assetSearchStyle.active : ''
                    }`}
                    onClick={() => checkInstDetail(index)}
                  >
                    <div className={assetSearchStyle.title}>{`${modelName} - ${
                      target.find(
                        (title: InstDetailItem) => title.key === 'inst_name'
                      )?.children || '--'
                    }`}</div>
                    <ul>
                      {target.map((list: InstDetailItem) => {
                        const fieldItem: any =
                          propertyList.find(
                            (property) => property.attr_id === list.key
                          ) || {};
                        const fieldVal: string =
                          getFieldItem({
                            fieldItem,
                            userList,
                            isEdit: false,
                            value: list.children,
                            hideUserAvatar: true,
                          }) || '--';
                        const isStrField =
                          typeof fieldVal === 'string' &&
                          fieldVal.includes(searchText);
                        return isStrField ||
                          ['inst_name', 'organization'].includes(list.key) ? (
                          <li key={list.key}>
                            <span>{list.label}</span>：
                            <span
                              className={
                                isStrField ? 'text-[var(--color-primary)]' : ''
                              }
                            >
                              {fieldVal}
                            </span>
                          </li>
                          ) : null;
                      })}
                    </ul>
                  </div>
                ))}
              </div>
              {totalCount > 0 && (
                <div
                  style={{
                    padding: '12px 16px',
                    borderTop: '1px solid var(--color-border-2)',
                    flexShrink: 0,
                    display: 'flex',
                    justifyContent: 'flex-end',
                  }}
                >
                  <Pagination
                    current={currentPage}
                    pageSize={pageSize}
                    total={totalCount}
                    onChange={handlePageChange}
                    showSizeChanger
                    showTotal={(total) =>
                      `${t('common.total')} ${total} ${t('common.items')}`
                    }
                    pageSizeOptions={[10, 20, 50, 100]}
                  />
                </div>
              )}
            </div>
            <div className={assetSearchStyle.detail}>
              <div className={assetSearchStyle.detailTile}>
                <div className={assetSearchStyle.title}>{`${modelName} - ${
                  currentDetail.find(
                    (title: InstDetailItem) => title.key === 'inst_name'
                  )?.children || '--'
                }`}</div>
                <Button
                  type="link"
                  iconPosition="end"
                  icon={<ArrowRightOutlined />}
                  onClick={linkToDetail}
                >
                  {t('seeMore')}
                </Button>
              </div>
              <ul>
                {currentDetail.map((list: InstDetailItem) => {
                  const fieldItem: any =
                    propertyList.find(
                      (property) => property.attr_id === list.key
                    ) || {};
                  const fieldVal: string =
                    getFieldItem({
                      fieldItem,
                      userList,
                      isEdit: false,
                      value: list.children,
                      hideUserAvatar: true,
                    }) || '--';
                  const isStrField =
                    typeof fieldVal === 'string' &&
                    fieldVal.includes(searchText);
                  return (
                    <li
                      key={list.key}
                      className={assetSearchStyle.detailListItem}
                    >
                      <span className={assetSearchStyle.listItemLabel}>
                        <span
                          className={assetSearchStyle.label}
                          title={list.label}
                        >
                          {list.label}
                        </span>
                        <span className={assetSearchStyle.labelColon}>：</span>
                      </span>
                      <span
                        title={fieldVal}
                        className={`${
                          isStrField ? 'text-[var(--color-primary)]' : ''
                        } ${assetSearchStyle.listItemValue}`}
                      >
                        {fieldVal}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        ),
      },
    ];

    return result;
  };

  const getModelTabs = () => {
    return modelStats.map((stat) => {
      const modelName =
        modelList.find((model) => model.model_id === stat.model_id)
          ?.model_name || stat.model_id;

      const isActive = stat.model_id === activeTab;
      const content = isActive && items.length > 0 ? items[0].children : null;

      return {
        key: stat.model_id,
        label: `${modelName}(${stat.count})`,
        children: content,
      };
    });
  };

  const currentInstDetail = useMemo(() => {
    if (activeInstItem < 0 || !currentModelData[activeInstItem]) return [];
    const currentInst = currentModelData[activeInstItem];
    return Object.entries(currentInst)
      .map(([key, value]) => ({
        key: key,
        label: propertyList.find((item) => item.attr_id === key)?.attr_name,
        children: value,
        id: currentInst._id,
      }))
      .filter((desc) => !!desc.label);
  }, [activeInstItem, currentModelData, propertyList]);

  const linkToDetail = () => {
    if (currentInstDetail.length === 0) return;
    const params: any = {
      icn: '',
      model_name:
        modelList.find((model) => model.model_id === activeTab)?.model_name ||
        '--',
      model_id: activeTab,
      classification_id: '',
      inst_id: currentInstDetail[0]?.id || '',
      inst_name: currentInstDetail.find(
        (title: InstDetailItem) => title.key === 'inst_name'
      )?.children,
    };
    const queryString = new URLSearchParams(params).toString();
    const url = `/cmdb/assetData/detail/baseInfo?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const onTabChange = async (key: string) => {
    setActiveTab(key);
    setCurrentPage(1);
    setActiveInstItem(-1);
    await loadModelData(key, 1, pageSize);
  };

  const checkInstDetail = (index: number) => {
    setActiveInstItem(index);
  };

  const handlePageChange = (page: number, size: number) => {
    setCurrentPage(page);
    setPageSize(size);
    setActiveInstItem(-1);
    loadModelData(activeTab, page, size);
  };

  const clearHistoryItem = (
    e: React.MouseEvent<HTMLElement>,
    index: number
  ) => {
    e.preventDefault();
    const histories = deepClone(historyList);
    histories.splice(index, 1);
    setHistoryList(histories);
    localStorage.setItem('assetSearchHistory', JSON.stringify(histories));
  };

  const clearHistories = () => {
    localStorage.removeItem('assetSearchHistory');
    setHistoryList([]);
  };

  return (
    <div className={assetSearchStyle.assetSearch}>
      <Spin spinning={pageLoading}>
        {showSearch ? (
          <div className={assetSearchStyle.searchInput}>
            <h1 className={assetSearchStyle.searchTitle}>{`${t(
              'searchTitle'
            )}`}</h1>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <Search
                className={assetSearchStyle.inputBtn}
                value={searchText}
                allowClear
                size="large"
                placeholder={t('assetSearchTxt')}
                enterButton={
                  <div
                    className={assetSearchStyle.searchBtn}
                    onClick={handleSearch}
                  >
                    <SearchOutlined className="pr-[8px]" />
                    {t('common.search')}
                  </div>
                }
                onChange={handleTextChange}
                onPressEnter={handleSearch}
              />
              <div
                style={{
                  border: '1px solid var(--color-border-2)',
                  borderRadius: '2px',
                  padding: '4px 12px',
                  background: 'var(--color-bg-1)',
                  whiteSpace: 'nowrap',
                }}
              >
                <Checkbox
                  checked={caseSensitive}
                  onChange={(e) => setCaseSensitive(e.target.checked)}
                >
                  {t('FilterBar.exactMatch')}
                </Checkbox>
              </div>
            </div>
            {!!historyList.length && (
              <div className={assetSearchStyle.history}>
                <div className={assetSearchStyle.description}>
                  <span className={assetSearchStyle.historyName}>
                    {t('Model.searchHistory')}
                  </span>
                  <Button type="link" onClick={clearHistories}>
                    {`${t('clear')} ${t('all')}`}
                  </Button>
                </div>
                <ul>
                  {historyList.map((item, index) => (
                    <li key={index} onClick={() => setSearchText(item)}>
                      <Tag
                        color="var(--color-bg-1)"
                        closeIcon={<CloseCircleOutlined />}
                        onClose={(e) => clearHistoryItem(e, index)}
                      >
                        {item}
                      </Tag>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className={assetSearchStyle.searchDetail}>
            <div
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'center',
                marginBottom: '12px',
              }}
            >
              <Search
                className={assetSearchStyle.input}
                value={searchText}
                allowClear
                placeholder={t('assetSearchTxt')}
                enterButton={
                  <div
                    className={assetSearchStyle.searchBtn}
                    onClick={handleSearch}
                  >
                    <SearchOutlined className="pr-[8px]" />
                    {t('common.search')}
                  </div>
                }
                onChange={handleTextChange}
                onPressEnter={handleSearch}
              />
              <div
                style={{
                  border: '1px solid var(--color-border-2)',
                  borderRadius: '2px',
                  padding: '4px 12px',
                  background: 'var(--color-bg-1)',
                  whiteSpace: 'nowrap',
                }}
              >
                <Checkbox
                  checked={caseSensitive}
                  onChange={(e) => setCaseSensitive(e.target.checked)}
                >
                  {t('FilterBar.exactMatch')}
                </Checkbox>
              </div>
            </div>
            <div
              style={{
                height: 'calc(100vh - 136px)',
              }}
            >
              {modelStats.length ? (
                <Tabs
                  activeKey={activeTab}
                  items={getModelTabs()}
                  onChange={onTabChange}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </div>
          </div>
        )}
      </Spin>
    </div>
  );
};
export default AssetSearch;
