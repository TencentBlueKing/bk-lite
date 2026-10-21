'use client';
import React, { useEffect, useState, useMemo } from 'react';
import { Button } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import SearchActionBar from '@/components/search-action-bar';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import GridEntityCard from '@/components/grid-entity-card';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

import { useCollectTypeInfo } from '@/app/log/hooks/integration/common/getCollectTypeConfig';
import { useScreenAwareRouter } from '@/console-layout';
import { CollectTypeItem } from '@/app/log/types/integration';
import { TableDataItem, TreeItem } from '@/app/log/types';
import Permission from '@/components/permission';
import TreeSelector from '@/app/log/components/tree-selector';
import { ObjectItem } from '@/app/log/types/event';

const Integration = () => {
  const { isLoading } = useApiClient();
  const { getCollectTypes, getDisplayCategoryEnum } = useIntegrationApi();
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const { getIcon } = useCollectTypeInfo();
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');
  const [collectTypeList, setCollectTypeList] = useState<CollectTypeItem[]>([]);
  const [activeGroup, setActiveGroup] = useState<React.Key>('all');
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [categoryMap, setCategoryMap] = useState<Record<string, string>>({});
  const [categoryOrder, setCategoryOrder] = useState<string[]>([]);

  const collectTypes = useMemo(() => {
    const searchLower = searchText.toLowerCase();
    if (activeGroup === 'all') {
      const filtered = collectTypeList.filter((item) =>
        (item.display_name || item.name).toLowerCase().includes(searchLower)
      );
      // Sort by category order from left tree
      if (categoryOrder.length > 0) {
        const orderMap = categoryOrder.reduce(
          (acc, category, index) => {
            acc[category] = index;
            return acc;
          },
          {} as Record<string, number>
        );
        return filtered.sort((a, b) => {
          const orderA =
            orderMap[a.display_category] ?? Number.MAX_SAFE_INTEGER;
          const orderB =
            orderMap[b.display_category] ?? Number.MAX_SAFE_INTEGER;
          return orderA - orderB;
        });
      }
      return filtered;
    }
    return collectTypeList.filter(
      (item) =>
        item.display_category === activeGroup &&
        (item.display_name || item.name).toLowerCase().includes(searchLower)
    );
  }, [collectTypeList, activeGroup, searchText, categoryOrder]);

  useEffect(() => {
    if (isLoading) return;
    getCollectTypeList({
      type: 'init'
    });
  }, [isLoading]);

  const getCollectTypeList = async (params: Record<string, string> = {}) => {
    const { type, ...rest } = params;
    const isInit = type === 'init';
    setPageLoading(true);
    setTreeLoading(isInit);
    try {
      const [data, categoryEnum] = await Promise.all([
        getCollectTypes(rest),
        isInit ? getDisplayCategoryEnum() : Promise.resolve(null)
      ]);
      setCollectTypeList(data || []);
      if (isInit && categoryEnum) {
        // Build category id to name map
        const map = categoryEnum.reduce(
          (acc: Record<string, string>, item: { id: string; name: string }) => {
            acc[item.id] = item.name;
            return acc;
          },
          {}
        );
        setCategoryMap(map);
        // Save category order for sorting
        setCategoryOrder(categoryEnum.map((item: { id: string }) => item.id));
        setTreeData(getTreeData(data || [], categoryEnum));
        setDefaultSelectObj('all');
      }
    } finally {
      setPageLoading(false);
      setTreeLoading(false);
    }
  };

  const getTreeData = (
    data: ObjectItem[],
    categoryEnum: { id: string; name: string }[]
  ): TreeItem[] => {
    // Count items per category
    const categoryCounts = data.reduce(
      (acc, item) => {
        const category = item.display_category || 'other';
        acc[category] = (acc[category] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>
    );

    // Build tree from API category enum
    const categoryNodes: TreeItem[] = categoryEnum.map((item) => ({
      title: `${item.name}(${categoryCounts[item.id] || 0})`,
      key: item.id,
      children: []
    }));

    return [
      {
        title: `${t('common.all')}(${data.length})`,
        key: 'all',
        children: []
      },
      ...categoryNodes
    ];
  };

  const onTxtPressEnter = (val: string) => {
    setSearchText(val);
  };

  const linkToDetial = (app: CollectTypeItem) => {
    const row: TableDataItem = {
      icon: app.icon || getIcon(app.name, app.collector),
      name: app.name,
      collector: app.collector,
      id: app.id,
      display_name: app.display_name || app.name,
      description: app.display_description || app.description || '--'
    };
    const params = new URLSearchParams(row);
    const targetUrl = `/log/integration/list/detail/configure?${params.toString()}`;
    router.push(targetUrl);
  };

  const handleObjectChange = async (id: string) => {
    setActiveGroup(id);
  };

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 overflow-hidden">
      <TreeSelector
        showAllMenu
        data={treeData}
        defaultSelectedKey={defaultSelectObj as string}
        loading={treeLoading}
        searchPlaceholder={t('log.integration.searchCategory')}
        onNodeSelect={handleObjectChange}
      />
      <div className="min-w-0 flex-1 bg-[var(--color-bg)] p-5">
        <SearchActionBar
          searchProps={{
            allowClear: true,
            enterButton: true,
            placeholder: t('log.integration.searchCollectType'),
            onSearch: onTxtPressEnter,
          }}
        />
        {pageLoading ? (
          <CardGridSkeleton className="grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" />
        ) : collectTypes.length ? (
          <div className="grid h-[calc(100vh-236px)] w-full auto-rows-max grid-cols-1 content-start gap-4 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {collectTypes.map((app) => {
              const categoryLabel =
                categoryMap[app.display_category] || app.display_category;
              return (
                <GridEntityCard
                  key={app.id}
                  name={`${app.display_name || app.name || '--'} (${app.collector})`}
                  description={app.display_description || app.description}
                  icon={
                    <img
                      src={`/assets/icons/${app.icon || getIcon(app.name, app.collector)}.svg`}
                      alt=""
                      className="h-8 w-8 object-contain"
                      onError={(e) => {
                        (e.target as HTMLImageElement).src =
                          '/assets/icons/cc-default_默认.svg';
                      }}
                    />
                  }
                  metaLabels={categoryLabel ? [categoryLabel] : []}
                  footerClassName="w-full"
                  footer={(
                    <Permission
                      requiredPermissions={['Setting']}
                      className="w-full"
                    >
                      <Button
                        icon={<PlusOutlined />}
                        type="primary"
                        className="w-full"
                        onClick={(e) => {
                          e.stopPropagation();
                          linkToDetial(app);
                        }}
                      >
                        {t('log.integration.connect')}
                      </Button>
                    </Permission>
                  )}
                />
              );
            })}
          </div>
        ) : (
          <CompactEmptyState description={t('common.noData')} />
        )}
      </div>
    </div>
  );
};

export default Integration;
