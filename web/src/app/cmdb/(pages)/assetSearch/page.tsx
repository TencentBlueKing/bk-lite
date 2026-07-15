'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import assetSearchStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
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
  Empty,
  Pagination,
  Checkbox,
  message,
} from 'antd';
import useApiClient from '@/utils/request';
import { useCommon } from '@/app/cmdb/context/common';
import { deepClone, getFieldItem, getIconUrl } from '@/app/cmdb/utils/common';
import {
  useChangeRecordApi,
  useClassificationApi,
  useModelApi,
  useInstanceApi,
} from '@/app/cmdb/api';
import TagCapsuleGroup from '@/app/cmdb/components/tag-capsule-group';
import { normalizeTagValues } from '@/app/cmdb/utils/tag';
import { useRouter } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import dayjs from 'dayjs';
import AssetSearchLanding, {
  CategoryEntryItem,
  FollowedAssetViewItem,
  QuickTagItem,
  RecentChangeItem,
} from './landing';
import { useFollowedAssets } from '@/app/cmdb/hooks/useFollowedAssets';
import { resolveVisibleFollowedAssets } from '@/app/cmdb/utils/followedAssets';
import { getChangeOperationTone } from '@/app/cmdb/utils/assetSearchDisplay';
import {
  buildCategoryEntries,
  buildRecentChangeQuery,
  canLazyLoadRecentChanges,
  getRecentChangeMessage,
  getRecentChangeTarget,
  HIGH_RISK_CHANGE_TYPES,
  mergeRecentChangeRecords,
  type ChangeRecordSummary,
  type HighRiskChangeType,
  type RecentChangeFilter,
} from '@/app/cmdb/utils/assetSearchLandingData';
const { Search } = Input;

const RECENT_CHANGE_LIMIT = 10;
const FOLLOWED_ASSET_LIMIT = 12;

interface ChangeRecordListResponse {
  items: ChangeRecordSummary[];
  count: number;
}

interface FollowedAssetDetailResponse extends AssetListItem {
  model_name?: string;
  inst_name?: string;
  ip_addr?: string;
  classification_id?: string;
  icn?: string;
  organization_display?: string;
}

const AssetSearch = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const router = useRouter();
  const commonContext = useCommon();
  const { username } = useUserInfoContext();

  const { getModelAttrList } = useModelApi();
  const {
    searchInstances,
    fulltextSearchStats,
    fulltextSearchByModel,
    getModelInstanceCount,
  } = useInstanceApi();
  const { getClassificationList } = useClassificationApi();
  const { getChangeRecords } = useChangeRecordApi();
  const {
    items: followedItems,
    loading: followedConfigLoading,
    refresh: refreshFollowedConfig,
    followAsset,
    unfollowAsset,
  } = useFollowedAssets();

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
  const [landingLoading, setLandingLoading] = useState<boolean>(false);
  const [changesLoading, setChangesLoading] = useState<boolean>(false);
  const [changesLoadingMore, setChangesLoadingMore] = useState<boolean>(false);
  const [recentChangePage, setRecentChangePage] = useState<number>(1);
  const [recentChangeHasMore, setRecentChangeHasMore] = useState<boolean>(true);
  const [recentChangeResetKey, setRecentChangeResetKey] = useState<number>(0);
  const [followedLoading, setFollowedLoading] = useState<boolean>(false);
  const [recentChanges, setRecentChanges] = useState<RecentChangeItem[]>([]);
  const [recentChangeFilter, setRecentChangeFilter] = useState<RecentChangeFilter>('all');
  const [followedAssets, setFollowedAssets] = useState<FollowedAssetViewItem[]>([]);
  const [categoryEntries, setCategoryEntries] = useState<CategoryEntryItem[]>([]);
  const recentChangesFetchingRef = useRef(false);
  const followedAssetsLoadedRef = useRef(false);

  useEffect(() => {
    if (isLoading || !modelList.length) return;
  }, [isLoading, modelList]);

  useEffect(() => {
    const histories = localStorage.getItem('assetSearchHistory');
    if (histories) setHistoryList(JSON.parse(histories));
  }, []);

  const quickTags: QuickTagItem[] = useMemo(() => [
    { key: 'prod', label: t('AssetSearch.quickTags.prod'), keyword: t('AssetSearch.quickTags.prod') },
    { key: 'core', label: t('AssetSearch.quickTags.core'), keyword: t('AssetSearch.quickTags.core') },
    { key: 'database', label: t('AssetSearch.quickTags.database'), keyword: t('AssetSearch.quickTags.database') },
    { key: 'middleware', label: t('AssetSearch.quickTags.middleware'), keyword: t('AssetSearch.quickTags.middleware') },
    { key: 'webApp', label: t('AssetSearch.quickTags.webApp'), keyword: t('AssetSearch.quickTags.webApp') },
    { key: 'network', label: t('AssetSearch.quickTags.network'), keyword: t('AssetSearch.quickTags.network') },
  ], [t]);

  useEffect(() => {
    if (isLoading || !modelList.length) return;
    void loadLandingData();
  }, [isLoading, modelList.length]);

  useEffect(() => {
    if (
      isLoading ||
      followedConfigLoading ||
      !modelList.length ||
      followedAssetsLoadedRef.current
    ) return;
    followedAssetsLoadedRef.current = true;
    void loadFollowedAssets(followedItems);
  }, [followedItems, followedConfigLoading, isLoading, modelList.length]);

  useEffect(() => {
    if (propertyList.length && currentModelData.length) {
      const tabJsx = getInstDetial(currentModelData, propertyList);
      setItems(tabJsx);
    }
  }, [propertyList, currentModelData, activeInstItem, activeTab]);

  const loadLandingData = async () => {
    setLandingLoading(true);
    await Promise.allSettled([
      loadRecentChanges({ filter: recentChangeFilter, page: 1, append: false }),
      loadCategoryEntries(),
    ]);
    setLandingLoading(false);
  };

  const mapRecentChangeRecord = (record: ChangeRecordSummary): RecentChangeItem => {
    const modelName =
      modelList.find((model) => model.model_id === record.model_id)?.model_name ||
      record.model_id ||
      '--';
    const operation = getChangeOperationTone(record.type);
    return {
      id: record.id ?? `${record.created_at || ''}-${getRecentChangeTarget(record)}`,
      operationLabelKey: operation.labelKey,
      operationTone: operation.tone,
      target: getRecentChangeTarget(record),
      message: getRecentChangeMessage(record),
      typeLabel: modelName,
      operator: record.operator || '--',
      time: record.created_at ? dayjs(record.created_at).format('YYYY-MM-DD HH:mm') : '--',
    };
  };

  const appendRecentChanges = (nextList: RecentChangeItem[], append: boolean) => {
    if (!append) {
      setRecentChanges(nextList);
      return;
    }
    setRecentChanges((prev) => {
      const seen = new Set(prev.map((item) => item.id));
      return [
        ...prev,
        ...nextList.filter((item) => {
          if (seen.has(item.id)) return false;
          seen.add(item.id);
          return true;
        }),
      ];
    });
  };

  const loadRecentChanges = async ({
    filter = recentChangeFilter,
    page = 1,
    append = false,
  }: {
    filter?: RecentChangeFilter;
    page?: number;
    append?: boolean;
  } = {}) => {
    if (recentChangesFetchingRef.current) return;
    recentChangesFetchingRef.current = true;
    if (append) {
      setChangesLoadingMore(true);
    } else {
      setChangesLoading(true);
    }
    try {
      const operator = username || '';
      const { records, hasMore } = filter === 'highRisk'
        ? await (async () => {
          const responses = await Promise.all(
            HIGH_RISK_CHANGE_TYPES.map((type: HighRiskChangeType) =>
              getChangeRecords(
                buildRecentChangeQuery(filter, operator, type, RECENT_CHANGE_LIMIT, 1)
              ) as Promise<ChangeRecordListResponse>
            )
          );
          return {
            records: mergeRecentChangeRecords(
              responses.flatMap((response) => response.items),
              RECENT_CHANGE_LIMIT
            ),
            hasMore: false,
          };
        })()
        : await (async () => {
          const response = await getChangeRecords(
            buildRecentChangeQuery(filter, operator, undefined, RECENT_CHANGE_LIMIT, page)
          ) as ChangeRecordListResponse;
          const records = response.items.slice(0, RECENT_CHANGE_LIMIT);
          return {
            records,
            hasMore: page * RECENT_CHANGE_LIMIT < response.count,
          };
        })();
      const list: RecentChangeItem[] = records.map(mapRecentChangeRecord);
      appendRecentChanges(list, append);
      setRecentChangePage(page);
      setRecentChangeHasMore(canLazyLoadRecentChanges(filter) && hasMore);
    } catch {
      if (!append) {
        setRecentChanges([]);
      }
      setRecentChangeHasMore(false);
    } finally {
      setChangesLoading(false);
      setChangesLoadingMore(false);
      recentChangesFetchingRef.current = false;
    }
  };

  const loadFollowedAssets = async (sourceItems = followedItems) => {
    setFollowedLoading(true);
    try {
      const resolvedAssets = await resolveVisibleFollowedAssets<FollowedAssetDetailResponse>(
        sourceItems,
        async (modelId, instanceIds) => {
          const response = await searchInstances({
            model_id: modelId,
            query_list: [{ field: 'id', type: 'id[]', value: instanceIds }],
            page: 1,
            page_size: instanceIds.length,
          }) as { insts?: FollowedAssetDetailResponse[] };
          return response.insts || [];
        },
        FOLLOWED_ASSET_LIMIT
      );
      const modelById = new Map(
        modelList.map((modelItem) => [modelItem.model_id, modelItem])
      );
      setFollowedAssets(
        resolvedAssets.map(({ item, detail }) => {
          const model = modelById.get(item.model_id) || modelById.get(detail.model_id);
          const modelId = item.model_id;
          return {
            key: `${modelId}-${item.inst_id}`,
            inst_id: item.inst_id,
            model_id: modelId,
            model_name: model?.model_name || detail.model_name || modelId,
            inst_name: detail.inst_name || detail.ip_addr || String(item.inst_id),
            classification_id: model?.classification_id || detail.classification_id || '',
            icn: model?.icn || detail.icn || '',
            organization: detail.organization_display || (Array.isArray(detail.organization) ? detail.organization.join(' / ') : ''),
            icon: getIconUrl({ icn: model?.icn || detail.icn || '', model_id: modelId }),
            followed: true,
          } as FollowedAssetViewItem;
        })
      );
    } catch {
      setFollowedAssets([]);
    } finally {
      setFollowedLoading(false);
    }
  };

  const loadCategoryEntries = async () => {
    try {
      const [groups, instCount] = await Promise.all([
        getClassificationList(),
        getModelInstanceCount(),
      ]);
      const entries = buildCategoryEntries({
        groups,
        modelList,
        instanceCount: instCount,
        limit: 6,
      }).map((entry) => ({
        ...entry,
        icon: entry.target_model_id
          ? getIconUrl({ icn: entry.target_icn || '', model_id: entry.target_model_id })
          : '',
      }));
      setCategoryEntries(entries);
    } catch {
      setCategoryEntries([]);
    }
  };

  const resetToLanding = () => {
    setSearchText('');
    setShowSearch(true);
    setModelStats([]);
    setCurrentModelData([]);
    setItems([]);
    setPropertyList([]);
    setActiveTab('');
    setActiveInstItem(-1);
    setCurrentPage(1);
    setTotalCount(0);
    setPageLoading(false);
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextSearchText = e.target.value;
    setSearchText(nextSearchText);
    if (!nextSearchText) {
      resetToLanding();
    }
  };

  const handleSearch = async (keyword?: string) => {
    const nextSearchText = typeof keyword === 'string' ? keyword : searchText;
    if (!nextSearchText) {
      resetToLanding();
      return;
    }
    setSearchText(nextSearchText);
    setShowSearch(false);

    const histories = deepClone(historyList);
    if (
      !histories.length ||
      (histories.length && !histories.includes(nextSearchText))
    ) {
      histories.push(nextSearchText);
    }
    localStorage.setItem('assetSearchHistory', JSON.stringify(histories));
    setHistoryList(histories);

    setPageLoading(true);
    try {
      const stats: SearchStatsResponse = await fulltextSearchStats({
        search: nextSearchText,
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

      await loadModelData(firstModelId, 1, pageSize, nextSearchText);
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

  const loadModelData = async (
    modelId: string,
    page: number,
    size: number,
    keyword = searchText
  ) => {
    setPageLoading(true);
    try {
      const result: SearchByModelResponse = await fulltextSearchByModel({
        search: keyword,
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
                        const isTagField = fieldItem.attr_type === 'tag';
                        const tagValues = isTagField ? normalizeTagValues(list.children) : [];
                        const isTagMatch = isTagField
                          ? tagValues.some((tag) => tag.includes(searchText))
                          : false;
                        const isStrField =
                          typeof fieldVal === 'string' &&
                          fieldVal.includes(searchText);
                        return isStrField ||
                          isTagMatch ||
                          ['inst_name', 'organization'].includes(list.key) ? (
                          <li key={list.key}>
                            <span>{list.label}</span>：
                            <span
                              className={
                                isStrField ? 'text-[var(--color-primary)]' : ''
                              }
                            >
                              {isTagField ? <TagCapsuleGroup value={tagValues} maxVisible={2} compact /> : fieldVal}
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
                  const isTagField = fieldItem.attr_type === 'tag';
                  const tagValues = isTagField ? normalizeTagValues(list.children) : [];
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
                      {isTagField ? (
                        <span className={assetSearchStyle.listItemTagValue}>
                          <TagCapsuleGroup value={tagValues} maxVisible={2} compact />
                        </span>
                      ) : (
                        <span
                          title={fieldVal}
                          className={`${
                            isStrField ? 'text-[var(--color-primary)]' : ''
                          } ${assetSearchStyle.listItemValue}`}
                        >
                          {fieldVal}
                        </span>
                      )}
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

  const clearHistories = () => {
    localStorage.removeItem('assetSearchHistory');
    setHistoryList([]);
  };

  const handleQuickTagClick = (item: QuickTagItem) => {
    setSearchText(item.keyword || item.label);
  };

  const openFollowedAsset = (item: FollowedAssetViewItem) => {
    const params: any = {
      icn: item.icn || '',
      model_name: item.model_name || '',
      model_id: item.model_id,
      classification_id: item.classification_id || '',
      inst_id: item.inst_id,
      inst_name: item.inst_name,
    };
    router.push(`/cmdb/assetData/detail/baseInfo?${new URLSearchParams(params).toString()}`);
  };

  const toggleFollowedAsset = async (item: FollowedAssetViewItem) => {
    if (item.followed === false) {
      await followAsset({ model_id: item.model_id, inst_id: item.inst_id });
      message.success(t('AssetSearch.followSuccess'));
      setFollowedAssets((prev) =>
        prev.map((asset) =>
          asset.key === item.key ? { ...asset, followed: true } : asset
        )
      );
      return;
    }

    await unfollowAsset(item.model_id, item.inst_id);
    message.success(t('AssetSearch.unfollowSuccess'));
    setFollowedAssets((prev) =>
      prev.map((asset) =>
        asset.key === item.key ? { ...asset, followed: false } : asset
      )
    );
  };

  const refreshFollowedAssets = async () => {
    const nextConfig = await refreshFollowedConfig();
    await loadFollowedAssets(nextConfig.items);
  };

  const handleRecentChangeFilterChange = (filter: RecentChangeFilter) => {
    setRecentChangeFilter(filter);
    setRecentChangePage(1);
    setRecentChangeHasMore(true);
    setRecentChangeResetKey((prev) => prev + 1);
    void loadRecentChanges({ filter, page: 1, append: false });
  };

  const refreshRecentChanges = () => {
    setRecentChangePage(1);
    setRecentChangeHasMore(true);
    setRecentChangeResetKey((prev) => prev + 1);
    void loadRecentChanges({ filter: recentChangeFilter, page: 1, append: false });
  };

  const loadMoreRecentChanges = () => {
    if (
      !canLazyLoadRecentChanges(recentChangeFilter) ||
      !recentChangeHasMore ||
      changesLoading ||
      changesLoadingMore
    ) return;
    void loadRecentChanges({
      filter: recentChangeFilter,
      page: recentChangePage + 1,
      append: true,
    });
  };

  const openCategory = (item: CategoryEntryItem) => {
    if (!item.target_model_id) {
      return;
    }
    const params = new URLSearchParams({
      modelId: item.target_model_id,
      classificationId: item.target_classification_id || item.classification_id || '',
    });
    router.push(`/cmdb/assetData?${params.toString()}`);
  };

  return (
    <div className={assetSearchStyle.assetSearch}>
      <Spin spinning={pageLoading}>
        {showSearch ? (
          <AssetSearchLanding
            searchText={searchText}
            historyList={historyList}
            quickTags={quickTags}
            recentChanges={recentChanges}
            followedAssets={followedAssets}
            categoryEntries={categoryEntries}
            loading={landingLoading}
            changesLoading={changesLoading}
            followedLoading={followedLoading}
            caseSensitive={caseSensitive}
            recentChangeFilter={recentChangeFilter}
            recentChangeHasMore={recentChangeHasMore}
            recentChangeLoadingMore={changesLoadingMore}
            recentChangeResetKey={recentChangeResetKey}
            onSearchTextChange={setSearchText}
            onCaseSensitiveChange={setCaseSensitive}
            onSearch={() => void handleSearch()}
            onHistoryClick={(value) => void handleSearch(value)}
            onClearHistories={clearHistories}
            onClearHistoryItem={(index) => {
              const histories = deepClone(historyList);
              histories.splice(index, 1);
              setHistoryList(histories);
              localStorage.setItem('assetSearchHistory', JSON.stringify(histories));
            }}
            onQuickTagClick={handleQuickTagClick}
            onOpenAsset={openFollowedAsset}
            onToggleFollow={(item) => void toggleFollowedAsset(item)}
            onRefreshFollowedAssets={() => void refreshFollowedAssets()}
            onOpenCategory={openCategory}
            onViewAllChanges={() => router.push('/cmdb/assetManage/operationLog')}
            onRefreshRecentChanges={refreshRecentChanges}
            onLoadMoreRecentChanges={loadMoreRecentChanges}
            onRecentChangeFilterChange={handleRecentChangeFilterChange}
          />
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
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={resetToLanding}
              >
                {t('common.backToHome')}
              </Button>
              <Search
                className={assetSearchStyle.input}
                value={searchText}
                allowClear
                placeholder={t('assetSearchTxt')}
                enterButton={
                  <div
                    className={assetSearchStyle.searchBtn}
                    onClick={() => void handleSearch()}
                  >
                    <SearchOutlined className="pr-[8px]" />
                    {t('common.search')}
                  </div>
                }
                onChange={handleTextChange}
                onPressEnter={() => void handleSearch()}
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
