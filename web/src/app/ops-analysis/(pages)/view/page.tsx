'use client';

import './register-dashboard-pilot';
import React, { useCallback, useEffect, useState, useRef } from 'react';
import Sidebar from '../../components/sidebar';
import ViewEmptyState from '../../components/viewEmptyState';
import Dashboard, { DashboardRef } from './dashBoard/index';
import Topology from './topology/index';
import Architecture, { ArchitectureRef } from './architecture/index';
import Screen, { ScreenRef } from './screen/index';
import Report, { ReportRef } from './report/index';
import NetworkTopology, { NetworkTopologyRef } from './networkTopology/index';
import { TopologyRef } from '@/app/ops-analysis/types/topology';
import { useTranslation } from '@/utils/i18n';
import { DirectoryType, SidebarRef } from '@/app/ops-analysis/types';
import {
  CANVAS_TYPES,
  CanvasType,
  isCanvasType,
} from '@/app/ops-analysis/constants/canvasTypes';
import {
  LeftOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { Modal, Tooltip } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { applyDirectoryEditCollapse } from './directoryEditCollapse';
import { DirItem } from '@/app/ops-analysis/types';
import {
  getDisplayRecentCanvases,
  readRecentCanvases,
  recordRecentCanvas,
  type RecentCanvasRecord,
} from '@/app/ops-analysis/utils/recentCanvasStorage';
import { isScreenModeEnabled } from '@/console-layout';
import { buildOpsAnalysisViewHref } from '@/app/ops-analysis/utils/viewHref';

type SelectedCanvasItems = Record<CanvasType, DirItem | null>;

const createEmptySelectedItems = (): SelectedCanvasItems =>
  CANVAS_TYPES.reduce((acc, type) => {
    acc[type] = null;
    return acc;
  }, {} as SelectedCanvasItems);

const ViewPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const screenMode = isScreenModeEnabled(searchParams);
  const [collapsed, setCollapsed] = useState(false);
  const collapsedRef = useRef(collapsed);
  const directoryCollapsedBeforeEditRef = useRef<boolean | null>(null);
  collapsedRef.current = collapsed;

  const handleScreenEditingChange = useCallback((editing: boolean) => {
    const next = applyDirectoryEditCollapse(
      {
        collapsed: collapsedRef.current,
        savedCollapsed: directoryCollapsedBeforeEditRef.current,
      },
      editing,
    );
    directoryCollapsedBeforeEditRef.current = next.savedCollapsed;
    collapsedRef.current = next.collapsed;
    setCollapsed(next.collapsed);
  }, []);
  const [selectedType, setSelectedType] = useState<DirectoryType>('directory');
  const [selectedItem, setSelectedItem] = useState<SelectedCanvasItems>(
    createEmptySelectedItems
  );
  const [recentCanvases, setRecentCanvases] = useState<RecentCanvasRecord[]>([]);
  const dashboardRef = useRef<DashboardRef>(null);
  const architectureRef = useRef<ArchitectureRef>(null);
  const topologyRef = useRef<TopologyRef>(null);
  const screenRef = useRef<ScreenRef>(null);
  const reportRef = useRef<ReportRef>(null);
  const networkTopologyRef = useRef<NetworkTopologyRef>(null);
  const sidebarRef = useRef<SidebarRef>(null);
  const previousSelectionRef = useRef<{
    type: DirectoryType;
    item: DirItem | null;
  } | null>(null);

  const handleSidebarDataUpdate = (updatedItem: DirItem) => {
    if (!isCanvasType(updatedItem.type)) {
      return;
    }
    setSelectedItem((prev) =>
      prev[updatedItem.type]?.id === updatedItem.id
        ? { ...prev, [updatedItem.type]: updatedItem }
        : prev
    );
  };

  useEffect(() => {
    setRecentCanvases(readRecentCanvases(window.localStorage));
  }, []);

  // 检查是否需要显示未保存更改提示
  const checkUnsavedChanges = () => {
    if (selectedType === 'dashboard' && dashboardRef.current) {
      return dashboardRef.current.hasUnsavedChanges();
    }
    if (selectedType === 'topology' && topologyRef.current) {
      return topologyRef.current.hasUnsavedChanges();
    }
    if (selectedType === 'architecture' && architectureRef.current) {
      return architectureRef.current.hasUnsavedChanges();
    }
    if (selectedType === 'screen' && screenRef.current) {
      return screenRef.current.hasUnsavedChanges();
    }
    if (selectedType === 'report' && reportRef.current) {
      return reportRef.current.hasUnsavedChanges();
    }
    if (selectedType === 'networkTopology' && networkTopologyRef.current) {
      return networkTopologyRef.current.hasUnsavedChanges();
    }
    return false;
  };

  // 处理导航
  const handleNavigation = (type: DirectoryType, itemInfo?: DirItem) => {
    const isLeavingContentPage =
      isCanvasType(selectedType) &&
      (type !== selectedType ||
        (type === selectedType &&
          itemInfo?.id !==
            selectedItem[selectedType]?.id));

    if (isLeavingContentPage && checkUnsavedChanges()) {
      // 记录当前选中状态
      previousSelectionRef.current = {
        type: selectedType,
        item: isCanvasType(selectedType) ? selectedItem[selectedType] : null,
      };

      Modal.confirm({
        title: t('opsAnalysisSidebar.unsavedChanges'),
        content: t('opsAnalysisSidebar.unsavedChangesWarning'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        okButtonProps: { danger: true },
        centered: true,
        onOk: () => {
          performNavigation(type, itemInfo);
        },
        onCancel: () => {
          if (previousSelectionRef.current && sidebarRef.current) {
            const { item: prevItem } = previousSelectionRef.current;
            if (prevItem) {
              setTimeout(() => {
                sidebarRef.current?.setSelectedKeys([prevItem.id]);
              }, 0);
            }
          }
        },
      });
    } else {
      performNavigation(type, itemInfo);
    }
  };

  // 执行导航
  const performNavigation = (type: DirectoryType, itemInfo?: DirItem) => {
    setSelectedType(type);
    setSelectedItem({
      ...createEmptySelectedItems(),
      ...(isCanvasType(type) ? { [type]: itemInfo || null } : {}),
    });
    if (isCanvasType(type) && itemInfo) {
      setRecentCanvases(
        recordRecentCanvas(window.localStorage, {
          id: itemInfo.id,
          dataId: itemInfo.data_id,
          type,
          name: itemInfo.name,
        }),
      );
    }
    router.push(buildOpsAnalysisViewHref(
      itemInfo?.type || '',
      itemInfo?.id || '',
      searchParams,
    ));
  };

  const directoryToggleLabel = collapsed
    ? t('opsAnalysisSidebar.expandDirectory')
    : t('opsAnalysisSidebar.collapseDirectory');

  const handleOpenRecent = (item: RecentCanvasRecord) => {
    const canvasItem: DirItem = {
      id: item.id,
      data_id: item.dataId,
      name: item.name,
      type: item.type,
    };
    sidebarRef.current?.setSelectedKeys([item.id]);
    handleNavigation(item.type, canvasItem);
  };

  return (
    <div
      className="flex w-full h-full relative rounded-lg"
      style={{ minWidth: screenMode || collapsed ? 0 : 280 }}
    >
      <div
        hidden={screenMode}
        className={`relative z-30 h-full border-r border-[var(--color-border-1)] transition-all duration-300 ${
          collapsed ? 'w-0 min-w-0 overflow-visible' : 'w-[280px] min-w-[280px]'
        }`}
        style={{
          width: collapsed ? 0 : 280,
          minWidth: collapsed ? 0 : 280,
          maxWidth: collapsed ? 0 : 280,
          flexShrink: 0,
        }}
      >
        <div
          id="ops-analysis-sidebar"
          className="w-full h-full overflow-hidden bg-[var(--color-bg-1)]"
        >
          <Sidebar
            ref={sidebarRef}
            onSelect={handleNavigation}
            onDataUpdate={handleSidebarDataUpdate}
          />
        </div>
        {!screenMode && (
          <Tooltip title={directoryToggleLabel} placement="right">
            <button
              type="button"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={directoryToggleLabel}
              aria-controls="ops-analysis-sidebar"
              aria-expanded={!collapsed}
              className="absolute bottom-6 z-30 flex h-6 w-6 cursor-pointer items-center justify-center border border-[var(--color-border-1)] bg-[var(--color-bg-1)] text-[var(--color-text-2)] shadow-sm hover:bg-[var(--color-fill-2)]"
              style={{
                right: collapsed ? -24 : -12,
                borderRadius: collapsed ? '0 50% 50% 0' : '50%',
              }}
            >
              {collapsed ? <RightOutlined aria-hidden /> : <LeftOutlined aria-hidden />}
            </button>
          </Tooltip>
        )}
      </div>
      <div className="h-full flex-1 flex" style={{ minWidth: 0 }}>
        {selectedType === 'screen' ? (
          <Screen
            ref={screenRef}
            key={selectedItem.screen?.data_id ?? 'screen-empty'}
            selectedScreen={selectedItem.screen}
            onEditingChange={handleScreenEditingChange}
          />
        ) : selectedType === 'report' ? (
          <Report
            ref={reportRef}
            key={selectedItem.report?.data_id ?? 'report-empty'}
            selectedReport={selectedItem.report}
          />
        ) : selectedType === 'architecture' ? (
          <Architecture
            ref={architectureRef}
            selectedArchitecture={selectedItem.architecture}
          />
        ) : selectedType === 'topology' ? (
          <Topology
            ref={topologyRef}
            key={selectedItem.topology?.data_id ?? 'topology-empty'}
            selectedTopology={selectedItem.topology}
          />
        ) : selectedType === 'dashboard' ? (
          <Dashboard
            ref={dashboardRef}
            key={selectedItem.dashboard?.data_id ?? 'dashboard-empty'}
            selectedDashboard={selectedItem.dashboard}
          />
        ) : selectedType === 'networkTopology' ? (
          <NetworkTopology
            ref={networkTopologyRef}
            key={selectedItem.networkTopology?.data_id ?? 'networkTopology-empty'}
            selectedNetworkTopology={selectedItem.networkTopology}
          />
        ) : (
          <ViewEmptyState
            recents={getDisplayRecentCanvases(recentCanvases)}
            onOpenRecent={handleOpenRecent}
          />
        )}
      </div>
    </div>
  );
};

export default ViewPage;
