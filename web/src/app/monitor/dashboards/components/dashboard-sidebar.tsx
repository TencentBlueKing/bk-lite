'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { getProfessionalDashboardKey, getProfessionalDashboardUrl } from '../registry';
import { normalizeDashboardKey } from '../shared/utils';
import { preserveDashboardDisplayMode } from '../shared/utils/display-mode-route';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import TreeSelector from '@/app/monitor/components/treeSelector';
import { ObjectItem, TreeItem } from '@/app/monitor/types';
import styles from './dashboard-sidebar.module.scss';

interface DashboardSidebarProps {
  currentObjectKey: string;
}

const buildMonitorObjectTree = (objects: ObjectItem[]): TreeItem[] => {
  const groupedData = objects.reduce((acc, item) => {
    if (!acc[item.type]) {
      acc[item.type] = {
        title: item.display_type || '--',
        key: item.type,
        children: []
      };
    }
    acc[item.type].children.push({
      title: item.display_name || '--',
      label: item.name || '--',
      key: item.id,
      icon: item.icon,
      count: item.instance_count || 0,
      children: []
    });
    return acc;
  }, {} as Record<string, TreeItem>);

  if (groupedData.Other) {
    groupedData.Other.children = groupedData.Other.children?.filter(
      (item) => item.label !== 'SNMP Trap'
    );
  }

  return Object.values(groupedData);
};

export const DashboardSidebar = ({ currentObjectKey }: DashboardSidebarProps) => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const normalizedCurrent = normalizeDashboardKey(currentObjectKey);
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);

  useEffect(() => {
    if (isLoading) return;
    const loadObjects = async () => {
      try {
        setTreeLoading(true);
        const data: ObjectItem[] = await getMonitorObject({
          add_instance_count: true
        });
        setObjects(data);
        setTreeData(buildMonitorObjectTree(data));
      } finally {
        setTreeLoading(false);
      }
    };

    loadObjects();
  }, [isLoading]);

  const selectedObjectId = useMemo(() => {
    const monitorObjId = searchParams.get('monitorObjId');
    if (monitorObjId) return monitorObjId;

    const matched = objects.find(
      (item) =>
        getProfessionalDashboardKey(item.name, item.display_name) ===
        normalizedCurrent
    );
    return matched?.id;
  }, [normalizedCurrent, objects, searchParams]);

  const handleSelect = (key: string) => {
    if (String(key) === String(selectedObjectId || '')) return;

    const monitorItem = objects.find((item) => String(item.id) === String(key));
    const params = preserveDashboardDisplayMode(new URLSearchParams({
      monitorObjId: String(monitorItem?.id || key),
      name: monitorItem?.name || '',
      monitorObjDisplayName: monitorItem?.display_name || '',
      icon: monitorItem?.icon || '',
      instance_id_keys: Array.isArray(monitorItem?.instance_id_keys)
        ? monitorItem.instance_id_keys.join(',')
        : 'instance_id'
    }), new URLSearchParams(searchParams.toString()));
    const dashboardUrl = getProfessionalDashboardUrl(
      monitorItem?.name,
      monitorItem?.display_name,
      params.toString()
    );

    router.push(dashboardUrl || '/monitor/view');
  };

  return (
    <ResizableSidebar collapseStorageKey="monitor.dashboard.sidebarCollapsed">
      <div className={styles.sidebarInner}>
        <TreeSelector
          data={treeData}
          defaultSelectedKey={selectedObjectId}
          loading={treeLoading}
          onNodeSelect={handleSelect}
        />
      </div>
    </ResizableSidebar>
  );
};
