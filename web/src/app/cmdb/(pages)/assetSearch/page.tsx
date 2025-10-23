'use client';
import React, { useEffect, useState, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { SearchOutlined } from '@ant-design/icons';
import assetSearchStyle from './index.module.scss';
import { ArrowRightOutlined, CloseCircleOutlined } from '@ant-design/icons';
import {
  AttrFieldType,
  UserItem,
} from '@/app/cmdb/types/assetManage';
import { Spin, Input, Tabs, Button, Tag, Empty } from 'antd';
import useApiClient from '@/utils/request';
import { useCommon } from '@/app/cmdb/context/common';
import { deepClone, getFieldItem } from '@/app/cmdb/utils/common';
import { useModelApi, useInstanceApi } from '@/app/cmdb/api';
const { Search } = Input;
interface AssetListItem {
  model_id: string;
  _id: string;
  [key: string]: unknown;
}
interface TabItem {
  key: string;
  label: string;
  children: Array<AssetListItem>;
}

interface TabJsxItem {
  key: string;
  label: string;
  children: JSX.Element;
}

const AssetSearch = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const commonContext = useCommon();

  const { getModelAttrList } = useModelApi();
  const { fulltextSearchInstances } = useInstanceApi();

  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const modelList = commonContext?.modelList || [];
  const [propertyList, setPropertyList] = useState<AttrFieldType[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [activeTab, setActiveTab] = useState<string>('');
  const [items, setItems] = useState<TabJsxItem[]>([]);
  const [showSearch, setShowSearch] = useState<boolean>(true);
  const [instDetail, setInstDetail] = useState<TabJsxItem[]>([]);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [activeInstItem, setActiveInstItem] = useState<number>(-1);
  const [instData, setInstData] = useState<TabItem[]>([]);
  const [historyList, setHistoryList] = useState<string[]>([]);

  useEffect(() => {
    if (isLoading || !modelList.length) return;
  }, [isLoading, modelList]);

  useEffect(() => {
    const histories = localStorage.getItem('assetSearchHistory');
    if (histories) setHistoryList(JSON.parse(histories));
  }, []);

  useEffect(() => {
    if (propertyList.length) {
      const tabJsx = getInstDetial(instData, propertyList);
      setItems(tabJsx);
    }
  }, [propertyList, instData, activeInstItem, activeTab]);

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
      const data: AssetListItem[] = await fulltextSearchInstances({
        search: searchText,
      });
      const tabItems: TabItem[] = getAssetList(data);
      const defaultTab = tabItems[0]?.key || '';

      if (!defaultTab || !data.length) {
        // 清空所有相关数据
        setInstData([]);
        setItems([]);
        setPropertyList([]);
        setActiveTab('');
        setInstDetail([]);
        setActiveInstItem(-1);
        setPageLoading(false);
        return;
      }
      const attrList = await getModelAttrList(defaultTab);
      setPropertyList(attrList);
      setInstData(tabItems);
      setActiveTab(defaultTab);
      setActiveInstItem(-1); 
      setPageLoading(false);
    } catch {
      // 搜索失败时也要清空数据
      setInstData([]);
      setItems([]);
      setPropertyList([]);
      setActiveTab('');
      setInstDetail([]);
      setActiveInstItem(-1);
      setPageLoading(false);
    }
  };

  const getAssetList = (data: AssetListItem[]) => {
    const result = data.reduce((acc: any, item) => {
      const { model_id: modelId } = item;
      if (acc[modelId]) {
        acc[modelId].children.push(item);
      } else {
        acc[modelId] = { key: modelId, children: [item] };
      }
      return acc;
    }, {});
    return Object.values(result).map((item: any) => ({
      ...item,
      label: getModelName(item),
    }));
  };

  const getInstDetial = (tabItems: TabItem[], properties: AttrFieldType[]) => {
    const lists = deepClone(tabItems);
    lists.forEach((item: any) => {
      const descItems = item.children.map((desc: AssetListItem) => {
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
      if (item.key === activeTab) {
        setInstDetail(descItems[0] || []);
        if (activeInstItem < 0) {
          setActiveInstItem(0);
        }
      }
      item.children = (
        <div className={assetSearchStyle.searchResult}>
          <div className={assetSearchStyle.list}>
            {descItems.map((target: TabJsxItem[], index: number) => (
              <div
                key={index}
                className={`${assetSearchStyle.listItem} ${
                  index === activeInstItem ? assetSearchStyle.active : ''
                }`}
                onClick={() => checkInstDetail(index, target)}
              >
                <div className={assetSearchStyle.title}>{`${item.key} - ${
                  target.find((title: TabJsxItem) => title.key === 'inst_name')
                    ?.children || '--'
                }`}</div>
                <ul>
                  {target.map((list: TabJsxItem) => {
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
          <div className={assetSearchStyle.detail}>
            <div className={assetSearchStyle.detailTile}>
              <div className={assetSearchStyle.title}>{`${item.key} - ${
                instDetail.find(
                  (title: TabJsxItem) => title.key === 'inst_name'
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
              {instDetail.map((list: TabJsxItem) => {
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
                  typeof fieldVal === 'string' && fieldVal.includes(searchText);
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
      );
    });
    return lists;
  };

  const getModelName = (item: TabItem) => {
    return (
      (modelList.find((model) => model.model_id === item.key)?.model_name ||
        '--') + `(${item.children.length})`
    );
  };

  const linkToDetail = () => {
    const _instDetail = deepClone(instDetail);
    const params: any = {
      icn: '',
      model_name:
        modelList.find((model) => model.model_id === activeTab)?.model_name ||
        '--',
      model_id: activeTab,
      classification_id: '',
      inst_id: _instDetail[0]?.id || '',
      inst_name: _instDetail.find(
        (title: TabJsxItem) => title.key === 'inst_name'
      )?.children,
    };
    const queryString = new URLSearchParams(params).toString();
    const url = `/cmdb/assetData/detail/baseInfo?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const onTabChange = async (key: string) => {
    setActiveTab(key);
    setPageLoading(true);
    try {
      const attrList = await getModelAttrList(key);
      setPropertyList(attrList);
      setActiveInstItem(-1);
    } finally {
      setPageLoading(false);
    }
  };

  const checkInstDetail = (index: number, row: TabJsxItem[]) => {
    setActiveInstItem(index);
    setInstDetail(row);
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
            <div>
              {items.length ? (
                <Tabs
                  activeKey={activeTab}
                  items={items}
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
