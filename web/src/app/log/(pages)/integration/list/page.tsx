'use client';
import React, { useEffect, useState, useMemo } from 'react';
import { Spin, Input, Button, Tag, Empty } from 'antd';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/log/api/integration';
import integrationStyle from './index.module.scss';
import { SettingOutlined } from '@ant-design/icons';
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
  const { getCollectTypes } = useIntegrationApi();
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

  const collectTypes = useMemo(() => {
    if (activeGroup === 'all')
      return collectTypeList.filter((item) => item.name.includes(searchText));
    return collectTypeList.filter(
      (item) => item.collector === activeGroup && item.name.includes(searchText)
    );
  }, [collectTypeList, activeGroup, searchText]);

  useEffect(() => {
    if (isLoading) return;
    getCollectTypeList({
      type: 'init',
    });
  }, [isLoading]);

  const getCollectTypeList = async (params: Record<string, string> = {}) => {
    const { type, ...rest } = params;
    const isInit = type === 'init';
    setPageLoading(true);
    setTreeLoading(isInit);
    try {
      const data = (await getCollectTypes(rest)) || [];
      setCollectTypeList(data);
      if (isInit) {
        setTreeData(getTreeData(data));
        setDefaultSelectObj('all');
      }
    } finally {
      setPageLoading(false);
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce((acc, item) => {
      if (!acc[item.collector]) {
        acc[item.collector] = {
          title: item.collector || '--',
          key: item.collector,
          children: [],
        };
      }
      acc[item.collector].children.push({
        title: item.name || '--',
        label: item.name || '--',
        key: item.id,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    return [
      {
        title: `${t('common.all')}(${data.length})`,
        key: 'all',
        children: [],
      },
      ...Object.values(groupedData).map((item) => {
        item.title = `${item.title}(${item.children.length})`;
        item.children = [];
        return item;
      }),
    ];
  };

  const onTxtPressEnter = (val: string) => {
    setSearchText(val);
  };

  const linkToDetial = (app: CollectTypeItem) => {
    const row: TableDataItem = {
      icon: getIcon(app.name, app.collector),
      name: app.name,
      collector: app.collector,
      id: app.id,
      display_name: app.name,
      description: app.description || '--',
    };
    const params = new URLSearchParams(row);
    const targetUrl = `/log/integration/list/detail/configure?${params.toString()}`;
    router.push(targetUrl);
  };

  const handleObjectChange = async (id: string) => {
    setActiveGroup(id);
  };

  return (
    <div className={integrationStyle.integration}>
      <TreeSelector
        showAllMenu
        data={treeData}
        defaultSelectedKey={defaultSelectObj as string}
        loading={treeLoading}
        onNodeSelect={handleObjectChange}
      />
      <div className={integrationStyle.cards}>
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
              className={`flex flex-wrap w-full ${integrationStyle.integrationList}`}
            >
              {collectTypes.map((app) => (
                <div key={app.id} className="w-full sm:w-1/4 p-2">
                  <div
                    className={`bg-[var(--color-bg-1)] shadow-sm hover:shadow-md transition-shadow duration-300 ease-in-out rounded-lg p-4 relative cursor-pointer group ${integrationStyle.cardItem}`}
                  >
                    <div className="flex items-center space-x-4 my-2">
                      <Icon
                        type={getIcon(app.name, app.collector)}
                        className="text-[48px] min-w-[48px]"
                      />
                      <div
                        style={{
                          width: 'calc(100% - 60px)',
                        }}
                      >
                        <h2
                          title={app.name}
                          className="text-xl font-bold m-0 hide-text"
                        >
                          {app.name || '--'}
                        </h2>
                        <Tag className="mt-[4px]">{app.collector}</Tag>
                      </div>
                    </div>
                    <p
                      className={`mb-[15px] text-[var(--color-text-3)] text-[13px] ${integrationStyle.lineClamp3}`}
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
                          icon={<SettingOutlined />}
                          type="primary"
                          className="w-full rounded-md transition-opacity duration-300"
                          onClick={(e) => {
                            e.stopPropagation();
                            linkToDetial(app);
                          }}
                        >
                          {t('common.setting')}
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
