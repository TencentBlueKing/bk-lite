'use client';
import React, { useEffect, useMemo, useState } from 'react';
import { Empty, Segmented, Spin } from 'antd';
import { useSearchParams } from 'next/navigation';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { TreeItem, ObjectItem } from '@/app/monitor/types';
import { useTableOptions } from '@/app/monitor/hooks/view';
import viewStyle from './index.module.scss';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ViewList from './viewList';
import ViewHive from './viewHive';
import ResizableSidebar from '@/app/monitor/components/resizableSidebar';
import { cloneDeep } from 'lodash';
import { getProfessionalObjectDisplayName } from '@/app/monitor/dashboards/registry';
import { findByMonitorId, toMonitorIdString } from '@/app/monitor/utils/monitorIds';
import { useMonitorObjectQuery } from '@/app/monitor/hooks/useMonitorObjectQuery';
import {
  VIEW_OBJECT_QUERY_PARAM,
  resolveMonitorObjectQueryId
} from '@/app/monitor/utils/monitorObjectQuery';

const Integration = () => {
  const { isLoading } = useApiClient();
  const searchParams = useSearchParams();
  const { syncObjectId } = useMonitorObjectQuery(VIEW_OBJECT_QUERY_PARAM);
  const { getMonitorObject } = useMonitorApi();
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [objectId, setObjectId] = useState<React.Key>('');
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [displayType, setDisplayType] = useState<string>('list');
  const tableOptions = useTableOptions();

  const activeObject = useMemo(
    () => findByMonitorId(objects, objectId),
    [objects, objectId]
  );

  const showTab = useMemo(() => {
    const objectName = activeObject?.name || '';
    return ['Pod', 'Node'].includes(objectName);
  }, [activeObject]);

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  const handleObjectChange = async (id: string) => {
    setObjectId(id);
    setDisplayType('list');
    syncObjectId(id);
  };

  const onDisplayTypeChange = async (value: string) => {
    setDisplayType(value);
  };

  const getObjects = async (type?: string) => {
    try {
      setTreeLoading(true);
      const data: ObjectItem[] = await getMonitorObject({
        add_instance_count: true,
      });
      const _treeData = getTreeData(cloneDeep(data));
      setTreeData(_treeData);
      if (type === 'update') return;
      setObjects(data);
    } finally {
      setTreeLoading(false);
    }
  };

  useEffect(() => {
    if (!objects.length) return;
    const selectedId = resolveMonitorObjectQueryId({
      searchParams,
      objects,
      fallback: objects[0]?.id
    });
    setObjectId(selectedId);
    setDefaultSelectObj(selectedId);
    if (selectedId) {
      syncObjectId(selectedId);
    }
  }, [objects, searchParams, syncObjectId]);

  useEffect(() => {
    if (!objects.length || !objectId || activeObject) return;
    const fallbackId = resolveMonitorObjectQueryId({
      searchParams,
      objects,
      fallback: objects[0]?.id
    });
    if (!fallbackId || String(fallbackId) === String(objectId)) return;
    setObjectId(fallbackId);
    setDefaultSelectObj(fallbackId);
    syncObjectId(fallbackId);
  }, [activeObject, objectId, objects, searchParams, syncObjectId]);

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce((acc, item) => {
      if (!acc[item.type]) {
        acc[item.type] = {
          title: item.display_type || '--',
          key: item.type,
          children: [],
        };
      }
      acc[item.type].children.push({
        title: getProfessionalObjectDisplayName(item.name, item.display_name) || '--',
        label: item.name || '--',
        key: toMonitorIdString(item.id),
        icon: item.icon,
        count: item.instance_count || 0,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    if (groupedData.Other) {
      groupedData.Other.children = groupedData.Other.children.filter(
        (item) => item.label !== 'SNMP Trap'
      );
    }
    return Object.values(groupedData);
  };

  const updateTree = () => {
    getObjects('update');
  };

  return (
    <div className={`${viewStyle.view} w-full`}>
      <ResizableSidebar collapseStorageKey="monitor.view.sidebarCollapsed">
        <div className={viewStyle.tree}>
          <TreeSelector
            data={treeData}
            defaultSelectedKey={defaultSelectObj as string}
            loading={treeLoading}
            onNodeSelect={handleObjectChange}
          />
        </div>
      </ResizableSidebar>
      <div className={viewStyle.table}>
        {showTab && (
          <Segmented
            className="mb-[16px]"
            options={tableOptions}
            value={displayType}
            onChange={onDisplayTypeChange}
          />
        )}
        {treeLoading ? (
          <div className="flex h-full min-h-[240px] items-center justify-center">
            <Spin />
          </div>
        ) : !objects.length ? (
          <Empty description="暂无监控对象" className="mt-[80px]" />
        ) : !activeObject ? (
          <Empty description="请选择左侧监控对象" className="mt-[80px]" />
        ) : displayType === 'list' ? (
          <ViewList
            key={objectId}
            objects={objects}
            objectId={objectId}
            showTab={showTab}
            updateTree={updateTree}
          />
        ) : (
          <ViewHive
            objects={objects}
            objectId={objectId}
            showTab={showTab}
          ></ViewHive>
        )}
      </div>
    </div>
  );
};
export default Integration;
