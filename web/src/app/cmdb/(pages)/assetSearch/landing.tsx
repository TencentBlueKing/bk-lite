'use client';

import React from 'react';
import {
  AppstoreOutlined,
  ArrowRightOutlined,
  ClearOutlined,
  MoreOutlined,
  ReloadOutlined,
  SearchOutlined,
  StarFilled,
  StarOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Checkbox,
  Dropdown,
  Empty,
  Input,
  List,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { MenuProps } from 'antd';

import { useTranslation } from '@/utils/i18n';
import {
  getStableTypeStyle,
  type ChangeOperationTone,
} from '@/app/cmdb/utils/assetSearchDisplay';
import type { RecentChangeFilter } from '@/app/cmdb/utils/assetSearchLandingData';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import assetSearchStyle from './index.module.scss';

export interface QuickTagItem {
  key: string;
  label: string;
  keyword?: string;
  type?: 'search' | 'followed';
}

export interface RecentChangeItem {
  id: string | number;
  operationLabelKey: string;
  operationTone: ChangeOperationTone;
  target: string;
  message?: string;
  typeLabel: string;
  operator: string;
  time: string;
}

export interface FollowedAssetViewItem {
  key: string;
  inst_id: string | number;
  model_id: string;
  model_name: string;
  inst_name: string;
  classification_id?: string;
  icn?: string;
  organization?: string;
  icon?: string;
  followed?: boolean;
}

export interface CategoryEntryItem {
  key: string;
  classification_id: string;
  title: string;
  count: number;
  target_model_id?: string;
  target_classification_id?: string;
  icon?: string;
}

export interface AssetSearchLandingProps {
  searchText: string;
  historyList: string[];
  quickTags: QuickTagItem[];
  recentChanges: RecentChangeItem[];
  followedAssets: FollowedAssetViewItem[];
  categoryEntries: CategoryEntryItem[];
  loading?: boolean;
  followedLoading?: boolean;
  changesLoading?: boolean;
  recentChangeHasMore: boolean;
  recentChangeLoadingMore: boolean;
  recentChangeResetKey: number;
  caseSensitive: boolean;
  recentChangeFilter: RecentChangeFilter;
  onSearchTextChange: (value: string) => void;
  onCaseSensitiveChange: (value: boolean) => void;
  onSearch: () => void;
  onHistoryClick: (value: string) => void;
  onClearHistories: () => void;
  onClearHistoryItem: (index: number) => void;
  onQuickTagClick: (item: QuickTagItem) => void;
  onOpenAsset: (item: FollowedAssetViewItem) => void;
  onToggleFollow: (item: FollowedAssetViewItem) => void;
  onRefreshFollowedAssets: () => void;
  onOpenCategory: (item: CategoryEntryItem) => void;
  onViewAllChanges?: () => void;
  onRefreshRecentChanges: () => void;
  onLoadMoreRecentChanges: () => void;
  onRecentChangeFilterChange: (filter: RecentChangeFilter) => void;
}

const operationToneClassMap: Record<ChangeOperationTone, string> = {
  create: assetSearchStyle.operationCreate,
  update: assetSearchStyle.operationUpdate,
  delete: assetSearchStyle.operationDelete,
  execute: assetSearchStyle.operationExecute,
  relation: assetSearchStyle.operationRelation,
  unknown: assetSearchStyle.operationUnknown,
};

const renderChangeTarget = (_: string, record: RecentChangeItem) => {
  const shouldShowMessage = !!record.message && record.message !== record.target;
  return (
    <div className={assetSearchStyle.changeObject}>
      <EllipsisWithTooltip text={record.target} className={assetSearchStyle.changeTarget} />
      {shouldShowMessage && (
        <EllipsisWithTooltip text={record.message || ''} className={assetSearchStyle.changeMessage} />
      )}
    </div>
  );
};

const AssetSearchLanding: React.FC<AssetSearchLandingProps> = ({
  searchText,
  historyList,
  quickTags,
  recentChanges,
  followedAssets,
  categoryEntries,
  loading,
  followedLoading,
  changesLoading,
  recentChangeHasMore,
  recentChangeLoadingMore,
  recentChangeResetKey,
  caseSensitive,
  recentChangeFilter,
  onSearchTextChange,
  onCaseSensitiveChange,
  onSearch,
  onHistoryClick,
  onClearHistories,
  onClearHistoryItem,
  onQuickTagClick,
  onOpenAsset,
  onToggleFollow,
  onRefreshFollowedAssets,
  onOpenCategory,
  onViewAllChanges,
  onRefreshRecentChanges,
  onLoadMoreRecentChanges,
  onRecentChangeFilterChange,
}) => {
  const { t } = useTranslation();
  const recentChangeListRef = React.useRef<HTMLDivElement | null>(null);
  const historyStartIndex = Math.max(historyList.length - 6, 0);
  const visibleHistoryList = historyList.slice(historyStartIndex);
  const recentChangeFilterOptions = [
    { label: t('AssetSearch.changeFilters.all'), value: 'all' },
    { label: t('AssetSearch.changeFilters.mine'), value: 'mine' },
    { label: t('AssetSearch.changeFilters.highRisk'), value: 'highRisk' },
  ];

  const getFollowedAssetMenu = (item: FollowedAssetViewItem): MenuProps => ({
    items: [
      {
        key: 'detail',
        label: t('AssetSearch.viewDetail'),
      },
      {
        key: 'toggleFollow',
        label: item.followed === false ? t('AssetSearch.follow') : t('AssetSearch.unfollow'),
      },
    ],
    onClick: ({ key, domEvent }) => {
      domEvent.stopPropagation();
      if (key === 'detail') {
        onOpenAsset(item);
        return;
      }
      onToggleFollow(item);
    },
  });

  React.useEffect(() => {
    if (recentChangeListRef.current) {
      recentChangeListRef.current.scrollTop = 0;
    }
  }, [recentChangeResetKey]);

  const handleRecentChangeScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    const distanceToBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    if (distanceToBottom <= 48 && recentChangeHasMore && !recentChangeLoadingMore && !changesLoading) {
      onLoadMoreRecentChanges();
    }
  };

  const changeColumns: ColumnsType<RecentChangeItem> = [
    {
      title: t('AssetSearch.operationType'),
      dataIndex: 'operationLabelKey',
      key: 'operationLabelKey',
      width: 92,
      render: (_: string, record) => (
        <span className={`${assetSearchStyle.operationBadge} ${operationToneClassMap[record.operationTone]}`}>
          <i />
          {t(record.operationLabelKey)}
        </span>
      ),
    },
    {
      title: t('AssetSearch.object'),
      dataIndex: 'target',
      key: 'target',
      width: '48%',
      ellipsis: true,
      render: renderChangeTarget,
    },
    {
      title: t('AssetSearch.type'),
      dataIndex: 'typeLabel',
      key: 'typeLabel',
      width: 114,
      render: (value: string) => (
        <span className={assetSearchStyle.typePill} style={getStableTypeStyle(value)}>
          {value}
        </span>
      ),
    },
    {
      title: t('AssetSearch.operator'),
      dataIndex: 'operator',
      key: 'operator',
      width: 76,
      ellipsis: true,
    },
    {
      title: t('AssetSearch.time'),
      dataIndex: 'time',
      key: 'time',
      width: 132,
    },
  ];

  return (
    <div className={assetSearchStyle.landing}>
      <section className={assetSearchStyle.hero}>
        <div className={assetSearchStyle.heroContent}>
          <h1>{t('AssetSearch.heroTitle')}</h1>
          <div className={assetSearchStyle.heroSearchRow}>
            <Input.Search
              size="large"
              allowClear
              value={searchText}
              placeholder={t('AssetSearch.heroPlaceholder')}
              enterButton={(
                <span className={assetSearchStyle.searchButtonLabel}>
                  <SearchOutlined />
                  {t('common.search')}
                </span>
              )}
              onChange={(event) => onSearchTextChange(event.target.value)}
              onSearch={onSearch}
            />
            <Checkbox
              checked={caseSensitive}
              className={assetSearchStyle.exactMatch}
              onChange={(event) => onCaseSensitiveChange(event.target.checked)}
            >
              {t('FilterBar.exactMatch')}
            </Checkbox>
          </div>
          <div className={assetSearchStyle.tagRows}>
            {historyList.length > 0 && (
              <div className={assetSearchStyle.tagRow}>
                <span>{t('AssetSearch.recentSearch')}:</span>
                <Space size={[8, 8]} wrap>
                  {visibleHistoryList.map((item, index) => (
                    <Tag
                      key={`${item}-${index}`}
                      closable
                      onClose={(event) => {
                        event.preventDefault();
                        onClearHistoryItem(historyStartIndex + index);
                      }}
                      onClick={() => onHistoryClick(item)}
                    >
                      {item}
                    </Tag>
                  ))}
                  <Button
                    type="link"
                    size="small"
                    icon={<ClearOutlined />}
                    onClick={onClearHistories}
                  >
                    {t('AssetSearch.clearHistory')}
                  </Button>
                </Space>
              </div>
            )}
            <div className={assetSearchStyle.tagRow}>
              <span>{t('AssetSearch.commonTags')}:</span>
              <Space size={[8, 8]} wrap>
                {quickTags.map((item) => (
                  <Tag key={item.key} onClick={() => onQuickTagClick(item)}>
                    {item.label}
                  </Tag>
                ))}
              </Space>
            </div>
          </div>
        </div>
      </section>

      <div className={assetSearchStyle.contentGrid}>
        <Card
          title={(
            <div className={assetSearchStyle.panelTitleWithTabs}>
              <span>{t('AssetSearch.recentChanges')}</span>
              <div className={assetSearchStyle.changeFilterTabs} role="group">
                {recentChangeFilterOptions.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={recentChangeFilter === item.value ? assetSearchStyle.activeChangeFilter : ''}
                    aria-pressed={recentChangeFilter === item.value}
                    onClick={() => onRecentChangeFilterChange(item.value as RecentChangeFilter)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          className={`${assetSearchStyle.panel} ${assetSearchStyle.changesPanel}`}
          extra={(
            <Space size={10}>
              <Tooltip title={t('AssetSearch.refresh')}>
                <Button
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  className={assetSearchStyle.refreshButton}
                  onClick={onRefreshRecentChanges}
                />
              </Tooltip>
              <Button
                type="link"
                size="small"
                icon={<ArrowRightOutlined />}
                iconPosition="end"
                onClick={onViewAllChanges}
              >
                {t('AssetSearch.viewAll')}
              </Button>
            </Space>
          )}
        >
          <div
            ref={recentChangeListRef}
            className={assetSearchStyle.changeList}
            onScroll={handleRecentChangeScroll}
          >
            <Table
              className={assetSearchStyle.changeTable}
              size="small"
              rowKey="id"
              loading={changesLoading || loading}
              columns={changeColumns}
              dataSource={recentChanges}
              tableLayout="fixed"
              pagination={false}
              locale={{
                emptyText: (
                  <Empty
                    className={assetSearchStyle.tableEmptyState}
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('common.noData')}
                  />
                ),
              }}
            />
            {recentChangeLoadingMore && (
              <div className={assetSearchStyle.lazyLoadingIndicator}>
                <Spin size="small" />
                <span>{t('AssetSearch.loadingMore')}</span>
              </div>
            )}
          </div>
        </Card>

        <Card
          title={t('AssetSearch.myFollowedAssets')}
          className={`${assetSearchStyle.panel} ${assetSearchStyle.followedPanel}`}
          extra={(
            <Tooltip title={t('AssetSearch.refresh')}>
              <Button
                type="text"
                size="small"
                icon={<ReloadOutlined />}
                loading={followedLoading}
                className={assetSearchStyle.refreshButton}
                onClick={onRefreshFollowedAssets}
              />
            </Tooltip>
          )}
        >
          <List
            className={assetSearchStyle.followedList}
            loading={followedLoading || loading}
            dataSource={followedAssets}
            locale={{
              emptyText: (
                <Empty
                  className={assetSearchStyle.followedEmptyState}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('common.noData')}
                />
              ),
            }}
            renderItem={(item) => (
              <List.Item
                className={assetSearchStyle.followedItem}
                actions={[
                  <Tooltip
                    key="followed"
                    title={item.followed === false ? t('AssetSearch.follow') : t('AssetSearch.unfollow')}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={item.followed === false ? <StarOutlined /> : <StarFilled />}
                      className={`${assetSearchStyle.followedStarButton} ${
                        item.followed === false ? assetSearchStyle.unfollowedStarButton : ''
                      }`}
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggleFollow(item);
                      }}
                    />
                  </Tooltip>,
                  <Dropdown
                    key="more"
                    trigger={['click']}
                    menu={getFollowedAssetMenu(item)}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<MoreOutlined />}
                      onClick={(event) => event.stopPropagation()}
                    />
                  </Dropdown>,
                ]}
                onClick={() => onOpenAsset(item)}
              >
                <div className={assetSearchStyle.followedAssetRow}>
                  <span className={assetSearchStyle.assetIcon}>
                    {item.icon ? <img src={item.icon} alt="" /> : <AppstoreOutlined />}
                  </span>
                  <span className={assetSearchStyle.followedAssetIdentity}>
                    <span className={assetSearchStyle.followedAssetName}>
                      {item.inst_name}
                    </span>
                    <span
                      className={assetSearchStyle.assetModelPill}
                      style={getStableTypeStyle(item.model_name)}
                    >
                      {item.model_name}
                    </span>
                    <span className={assetSearchStyle.followedAssetOrg}>
                      {item.organization || '--'}
                    </span>
                  </span>
                </div>
              </List.Item>
            )}
          />
        </Card>
      </div>

      <Card
        title={t('AssetSearch.assetCategories')}
        className={`${assetSearchStyle.panel} ${assetSearchStyle.categoryPanel}`}
      >
        {categoryEntries.length > 0 ? (
          <div className={assetSearchStyle.categoryGrid}>
            {categoryEntries.map((item) => (
              <button
                key={item.key}
                type="button"
                className={assetSearchStyle.categoryTile}
                onClick={() => onOpenCategory(item)}
              >
                <span className={assetSearchStyle.categoryIcon}>
                  {item.icon ? <img src={item.icon} alt="" /> : <AppstoreOutlined />}
                </span>
                <span>
                  <strong>{item.title}</strong>
                  <em>{item.count.toLocaleString()}</em>
                </span>
                <ArrowRightOutlined />
              </button>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
    </div>
  );
};

export default AssetSearchLanding;
