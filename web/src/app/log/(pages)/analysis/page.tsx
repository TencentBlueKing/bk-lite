'use client';

import React, {
  useState,
  useRef,
  useMemo,
  useEffect,
  useCallback
} from 'react';
import Dashboard, { DashboardRef } from './dashBoard';
import { Input, Spin } from 'antd';
import { useBuildInDashBoards } from '../../hooks/analysis';
import useApiClient from '@/utils/request';
import useLogApi from '@/app/log/api/integration';
import { useCollectTypeInfo } from '@/app/log/hooks/integration/common/getCollectTypeConfig';
import ResizableSidebar from '@/components/resizable-sidebar';
import { TreeItem } from '@/app/log/types';
import { ObjectItem } from '@/app/log/types/event';

const { Search } = Input;

/** 扁平列表项 */
interface FlatItem {
  key: string;
  title: string;
  icon: string;
}

const findFirstLeafKey = (nodes: TreeItem[]): string => {
  for (const node of nodes) {
    if (!node.children?.length) {
      return String(node.key);
    }
    const childKey = findFirstLeafKey(node.children);
    if (childKey) return childKey;
  }
  return '';
};

const Analysis: React.FC = () => {
  const menuItems = useBuildInDashBoards();
  const { isLoading } = useApiClient();
  const { getCollectTypes, getDisplayCategoryEnum } = useLogApi();
  const { getIcon } = useCollectTypeInfo();
  const dashboardRef = useRef<DashboardRef>(null);
  const [dashboardId, setDashboardId] = useState<string>('');
  const [dashboardCollectTypeIdMap, setDashboardCollectTypeIdMap] = useState<
    Record<string, React.Key>
  >({});
  const [dashboardTitleMap, setDashboardTitleMap] = useState<
    Record<string, string>
  >({});
  const [selectedCollectTypeId, setSelectedCollectTypeId] =
    useState<React.Key | null>(null);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [flatList, setFlatList] = useState<FlatItem[]>([]);
  const [searchValue, setSearchValue] = useState('');
  const [treeLoading, setTreeLoading] = useState<boolean>(true);

  const selectedDashboard = useMemo(() => {
    return menuItems.find((item) => item.id === dashboardId) || null;
  }, [dashboardId, menuItems]);

  // 构建 collectTypeName 到仪表盘的映射
  const dashboardMap = useMemo(() => {
    const map: Record<string, (typeof menuItems)[0]> = {};
    menuItems.forEach((item) => {
      if (item.collectTypeName) {
        map[item.collectTypeName] = item;
      }
    });
    return map;
  }, [menuItems]);

  const buildTreeData = useCallback(
    (
      collectTypes: ObjectItem[],
      categoryEnum: { id: string; name: string }[]
    ): TreeItem[] => {
      const categoryMap = categoryEnum.reduce(
        (acc: Record<string, string>, item) => {
          acc[item.id] = item.name;
          return acc;
        },
        {}
      );

      const collectTypeIdMap: Record<string, React.Key> = {};
      const titleMap: Record<string, string> = {};
      const flat: FlatItem[] = [];

      // 按 display_category 分组，仅包含有对应仪表盘的 collectType
      const groupedData = collectTypes.reduce(
        (acc, item) => {
          const category = item.display_category || 'other';
          const dashboard = dashboardMap[item.name];
          const nodeLabel = item.display_name || item.name || '--';
          // 没有仪表盘的节点隐藏
          if (!dashboard) return acc;
          collectTypeIdMap[dashboard.id] = item.id;
          titleMap[dashboard.id] = nodeLabel;
          // 构建扁平列表（按 categoryEnum 排序，后面再排）
          flat.push({
            key: String(dashboard.id),
            title: nodeLabel,
            icon: getIcon(item.name, item.collector)
          });
          if (!acc[category]) {
            acc[category] = {
              title: categoryMap[category] || category,
              key: `category-${category}`,
              children: []
            };
          }
          acc[category].children.push({
            title: nodeLabel,
            label: nodeLabel,
            key: dashboard.id,
            children: []
          });
          return acc;
        },
        {} as Record<string, TreeItem>
      );

      setDashboardCollectTypeIdMap(collectTypeIdMap);
      setDashboardTitleMap(titleMap);

      // 按 categoryEnum 顺序排列扁平列表
      const orderedKeys: string[] = [];
      categoryEnum.forEach((cat) => {
        if (groupedData[cat.id]) {
          groupedData[cat.id].children.forEach((child) => {
            orderedKeys.push(String(child.key));
          });
        }
      });
      const orderedFlat = orderedKeys
        .map((k) => flat.find((f) => f.key === k))
        .filter(Boolean) as FlatItem[];
      setFlatList(orderedFlat);

      // 按 categoryEnum 顺序排列，仅展示有子节点的分类
      return categoryEnum
        .filter((cat) => groupedData[cat.id])
        .map((cat) => groupedData[cat.id]);
    },
    [dashboardMap, getIcon]
  );

  useEffect(() => {
    if (isLoading) return;
    const fetchTreeData = async () => {
      try {
        setTreeLoading(true);
        const [collectTypes, categoryEnum] = await Promise.all([
          getCollectTypes(),
          getDisplayCategoryEnum()
        ]);
        setTreeData(buildTreeData(collectTypes || [], categoryEnum || []));
      } finally {
        setTreeLoading(false);
      }
    };
    fetchTreeData();
  }, [isLoading]);

  useEffect(() => {
    setSelectedCollectTypeId(dashboardCollectTypeIdMap[dashboardId] || null);
  }, [dashboardCollectTypeIdMap, dashboardId]);

  useEffect(() => {
    if (!treeData.length) {
      return;
    }

    const selectedNodeExists = dashboardId
      ? menuItems.some((item) => item.id === dashboardId)
      : false;

    if (selectedNodeExists) {
      return;
    }

    const firstLeafKey = findFirstLeafKey(treeData);
    if (firstLeafKey) {
      setDashboardId(firstLeafKey);
    }
  }, [treeData, dashboardId, menuItems]);

  const handleNodeSelect = (key: string) => {
    setDashboardId(key);
  };

  return (
    <div className="flex w-full h-[calc(100vh-90px)] relative rounded-lg">
      <ResizableSidebar
        storageKey="log.analysis.sidebar.width"
        collapseStorageKey="log.analysis.sidebarCollapsed"
        defaultWidth={160}
        minWidth={140}
        maxWidth={320}
      >
        <div className="flex h-full flex-col overflow-hidden bg-[var(--color-bg-1)]">
          <div className="flex-shrink-0 px-2 pb-2 pt-4">
            <Search
              placeholder="搜索..."
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              allowClear
            />
          </div>
          <div className="flex-1 overflow-x-hidden overflow-y-auto px-1 pb-2">
            <Spin spinning={treeLoading}>
              {flatList
                .filter((item) =>
                  searchValue
                    ? item.title
                      .toLowerCase()
                      .includes(searchValue.toLowerCase())
                    : true
                )
                .map((item) => {
                  const isSelected = item.key === dashboardId;
                  return (
                    <div
                      key={item.key}
                      onClick={() => handleNodeSelect(item.key)}
                      className={`
                          flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer
                          transition-colors duration-150 mb-0.5
                          ${
                            isSelected
                              ? 'bg-[var(--color-fill-2)] text-[var(--color-primary-6)]'
                              : 'text-[var(--color-text-1)] hover:bg-[var(--color-fill-1)]'
                          }
                        `}
                    >
                      <span
                        className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md"
                        style={{ backgroundColor: 'var(--color-fill-2)' }}
                      >
                        <img
                          src={`/assets/icons/${item.icon}.svg`}
                          alt={item.title}
                          className="flex-shrink-0"
                          style={{ width: 14, height: 14 }}
                          onError={(e) => {
                            (e.target as HTMLImageElement).src =
                              '/assets/icons/cc-default_默认.svg';
                          }}
                        />
                      </span>
                      <span
                        className="min-w-0 break-words text-xs leading-tight"
                        style={{ wordBreak: 'break-all' }}
                      >
                        {item.title}
                      </span>
                    </div>
                  );
                })}
            </Spin>
          </div>
        </div>
      </ResizableSidebar>
      <div
        className="flex h-full flex-1 border-l border-[var(--color-border-1)]"
        style={{ minWidth: 0 }}
      >
        <Dashboard
          ref={dashboardRef}
          selectedDashboard={selectedDashboard}
          selectedDashboardTitle={dashboardTitleMap[dashboardId] || ''}
          selectedCollectTypeId={selectedCollectTypeId}
          editable={false}
        />
      </div>
    </div>
  );
};

export default Analysis;
