'use client';
import React, { useEffect, useState, useMemo } from 'react';
import { Spin, Input, Button, Tag, Empty } from 'antd';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import { useCollectTypeInfo } from '@/app/log/hooks/integration/common/getCollectTypeConfig';
import { useRouter } from 'next/navigation';
import { CollectTypeItem } from '@/app/log/types/integration';
import { TableDataItem, TreeItem } from '@/app/log/types';
import Permission from '@/components/permission';
import TreeSelector from '@/app/log/components/tree-selector';
import { ObjectItem } from '@/app/log/types/event';
const { Search } = Input;

const Integration = () => {
  const { isLoading } = useApiClient();
  const { getCollectTypes, getDisplayCategoryEnum } = useIntegrationApi();
  const { t } = useTranslation();
  const router = useRouter();
  const { getIcon } = useCollectTypeInfo();
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [searchText, setSearchText] = useState<string>('');
  const [collectTypeList, setCollectTypeList] = useState<CollectTypeItem[]>([]);
  const [activeGroup, setActiveGroup] = useState<React.Key>('all');
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [categoryMap, setCategoryMap] = useState<Record<string, string>>({});

  const collectTypes = useMemo(() => {
    if (activeGroup === 'all')
      return collectTypeList.filter((item) => item.name.includes(searchText));
    return collectTypeList.filter(
      (item) =>
        item.display_category === activeGroup && item.name.includes(searchText)
    );
  }, [collectTypeList, activeGroup, searchText]);

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
      display_name: app.name,
      description: app.description || '--'
    };
    const params = new URLSearchParams(row);
    const targetUrl = `/log/integration/list/detail/configure?${params.toString()}`;
    router.push(targetUrl);
  };

  const handleObjectChange = async (id: string) => {
    setActiveGroup(id);
  };

  return (
    <div className="flex">
      <TreeSelector
        showAllMenu
        data={treeData}
        defaultSelectedKey={defaultSelectObj as string}
        loading={treeLoading}
        onNodeSelect={handleObjectChange}
      />
      <div className="w-full p-5 bg-[var(--color-bg-1)]">
        <div className="flex justify-end">
          <Search
            className="mb-[20px] w-60"
            allowClear
            enterButton
            placeholder={`${t('common.search')}...`}
            onSearch={onTxtPressEnter}
          />
        </div>
        <Spin spinning={pageLoading}>
          {collectTypes.length ? (
            <div
              className="grid gap-4 w-full h-[calc(100vh-236px)] overflow-y-auto"
              style={{
                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                alignContent: 'start'
              }}
            >
              {collectTypes.map((app) => (
                <div key={app.id} className="p-2">
                  <div className="bg-[var(--color-bg-1)] shadow-sm hover:shadow-md transition-shadow duration-300 ease-in-out rounded-lg p-4 relative cursor-pointer group border">
                    <div className="flex items-center space-x-4 my-2">
                      <Icon
                        type={app.icon || getIcon(app.name, app.collector)}
                        className="text-[48px] min-w-[48px]"
                      />
                      <div
                        style={{
                          width: 'calc(100% - 60px)'
                        }}
                      >
                        <h2
                          title={`${app.name} (${app.collector})`}
                          className="text-xl font-bold m-0 hide-text"
                        >
                          {app.name || '--'} ({app.collector})
                        </h2>
                        <Tag className="mt-[4px]">
                          {categoryMap[app.display_category] ||
                            app.display_category}
                        </Tag>
                      </div>
                    </div>
                    <p
                      className="mb-[15px] text-[var(--color-text-3)] text-[13px] h-[54px] overflow-hidden line-clamp-3"
                      title={app.description || '--'}
                    >
                      {app.description || '--'}
                    </p>
                    <div className="w-full h-[32px] flex justify-center items-end">
                      <Permission
                        requiredPermissions={['Setting']}
                        className="w-full"
                      >
                        <Button
                          icon={<PlusOutlined />}
                          type="primary"
                          className="w-full rounded-md transition-opacity duration-300"
                          onClick={(e) => {
                            e.stopPropagation();
                            linkToDetial(app);
                          }}
                        >
                          {t('log.integration.connect')}
                        </Button>
                      </Permission>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Spin>
      </div>
    </div>
  );
};

export default Integration;
