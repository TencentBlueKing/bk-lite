'use client';

import React, { useState, useRef, useMemo } from 'react';
import Dashboard, { DashboardRef } from './dashBoard';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { useBuildInDashBoards } from '../../hooks/analysis';
import TreeSelector from '@/app/log/components/tree-selector';
import { TreeItem } from '@/app/log/types';

const Analysis: React.FC = () => {
  const menuItems = useBuildInDashBoards();
  const [collapsed, setCollapsed] = useState(false);
  const dashboardRef = useRef<DashboardRef>(null);
  const [dashboardId, setDashboardId] = useState<string>(
    menuItems[0]?.id || ''
  );

  const selectedDashboard = useMemo(() => {
    return menuItems.find((item) => item.id === dashboardId) || menuItems[0];
  }, [dashboardId, menuItems]);

  // 将菜单项转换为树结构
  const treeData = useMemo(() => {
    const treeItems: TreeItem[] = [
      {
        title: 'Packbeat',
        key: 'packbeat',
        children: menuItems.map((item) => ({
          title: item.name,
          key: item.id,
          label: item.name,
          children: [],
        })),
      },
    ];
    return treeItems;
  }, [menuItems]);

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
          flexShrink: 0,
        }}
      >
        {!collapsed && (
          <TreeSelector
            data={treeData}
            loading={false}
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
          editable={false}
        />
      </div>
    </div>
  );
};

export default Analysis;
