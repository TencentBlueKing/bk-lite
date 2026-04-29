'use client';

import React, {
  useState,
  useRef,
  useMemo,
  useEffect,
  useCallback
} from 'react';
import Dashboard, { DashboardRef } from './dashBoard';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useBuildInDashBoards } from '../../hooks/analysis';
import useApiClient from '@/utils/request';
import useLogApi from '@/app/log/api/integration';
import TreeSelector from '@/app/log/components/tree-selector';
import { TreeItem } from '@/app/log/types';
import { ObjectItem } from '@/app/log/types/event';

const Analysis: React.FC = () => {
  const menuItems = useBuildInDashBoards();
  const { isLoading } = useApiClient();
  const { getCollectTypes, getDisplayCategoryEnum } = useLogApi();
  const [collapsed, setCollapsed] = useState(false);
  const dashboardRef = useRef<DashboardRef>(null);
  const [dashboardId, setDashboardId] = useState<string>(
    menuItems[0]?.id || ''
  );
  const [dashboardCollectTypeIdMap, setDashboardCollectTypeIdMap] = useState<
    Record<string, React.Key>
  >({});
  const [selectedCollectTypeId, setSelectedCollectTypeId] =
    useState<React.Key | null>(null);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [treeLoading, setTreeLoading] = useState<boolean>(true);

  const selectedDashboard = useMemo(() => {
    return menuItems.find((item) => item.id === dashboardId) || menuItems[0];
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

      // 按 display_category 分组，仅包含有对应仪表盘的 collectType
      const groupedData = collectTypes.reduce(
        (acc, item) => {
          const category = item.display_category || 'other';
          const dashboard = dashboardMap[item.name];
          // 没有仪表盘的节点隐藏
          if (!dashboard) return acc;
          collectTypeIdMap[dashboard.id] = item.id;
          if (!acc[category]) {
            acc[category] = {
              title: categoryMap[category] || category,
              key: `category-${category}`,
              children: []
            };
          }
          acc[category].children.push({
            title: item.display_name || item.name,
            label: item.display_name || item.name || '--',
            key: dashboard.id,
            children: []
          });
          return acc;
        },
        {} as Record<string, TreeItem>
      );

      setDashboardCollectTypeIdMap(collectTypeIdMap);

      // 按 categoryEnum 顺序排列，仅展示有子节点的分类
      return categoryEnum
        .filter((cat) => groupedData[cat.id])
        .map((cat) => groupedData[cat.id]);
    },
    [dashboardMap]
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

  const handleNodeSelect = (key: string) => {
    setDashboardId(key);
  };

  return (
    <div className="flex w-full h-[calc(100vh-90px)] relative rounded-lg">
      <div
        className={`h-full  relative transition-all duration-300 ${
          collapsed ? 'w-0 min-w-0' : 'w-[220px] min-w-[220px]'
        }`}
        style={{
          width: collapsed ? 0 : 220,
          minWidth: collapsed ? 0 : 220,
          maxWidth: collapsed ? 0 : 220,
          flexShrink: 0
        }}
      >
        {!collapsed && (
          <TreeSelector
            data={treeData}
            loading={treeLoading}
            defaultSelectedKey={dashboardId}
            onNodeSelect={handleNodeSelect}
            style={{ width: 220, height: 'calc(100vh - 90px)' }}
            inputStyle={{ width: 190 }}
          />
        )}
        <Button
          type="text"
          onClick={() => setCollapsed(!collapsed)}
          className={`absolute z-10 w-6 h-6 top-4 p-0 border border-[var(--color-border-3)] bg-[var(--color-bg-1)] flex items-center justify-center cursor-pointer rounded-full transition-all duration-300 ${
            collapsed
              ? 'left-0 border-l-0 rounded-tl-none rounded-bl-none'
              : 'left-[100%] -translate-x-1/2'
          }`}
        >
          {collapsed ? <RightOutlined /> : <LeftOutlined />}
        </Button>
      </div>
      <div
        className="h-full flex-1 flex border-l border-[var(--color-border-1)]"
        style={{ minWidth: 0 }}
      >
        <Dashboard
          ref={dashboardRef}
          selectedDashboard={selectedDashboard}
          selectedCollectTypeId={selectedCollectTypeId}
          editable={false}
        />
      </div>
    </div>
  );
};

export default Analysis;
