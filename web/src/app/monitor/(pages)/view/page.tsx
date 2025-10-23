'use client';
import React, { useEffect, useMemo, useState } from 'react';
import { Segmented } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import { TreeItem, ObjectItem } from '@/app/monitor/types';
import { useTableOptions } from '@/app/monitor/hooks/view';
import viewStyle from './index.module.scss';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ViewList from './viewList';
import ViewHive from './viewHive';
import { cloneDeep } from 'lodash';

const Integration = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [objectId, setObjectId] = useState<React.Key>('');
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [displayType, setDisplayType] = useState<string>('list');
  const tableOptions = useTableOptions();

  const showTab = useMemo(() => {
    const objectName = objects.find((item) => item.id === objectId)?.name || '';
    return ['Pod', 'Node'].includes(objectName);
  }, [objects, objectId]);

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  const handleObjectChange = async (id: string) => {
    setObjectId(id);
    setDisplayType('list');
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
      setDefaultSelectObj(data[0]?.id);
    } finally {
      setTreeLoading(false);
    }
  };

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
        title: (item.display_name || '--') + `(${item.instance_count || 0})`,
        label: item.name || '--',
        key: item.id,
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
      <div className={viewStyle.tree}>
        <TreeSelector
          data={treeData}
          defaultSelectedKey={defaultSelectObj as string}
          loading={treeLoading}
          onNodeSelect={handleObjectChange}
        />
      </div>
      <div className={viewStyle.table}>
        {showTab && (
          <Segmented
            className="mb-[16px]"
            options={tableOptions}
            value={displayType}
            onChange={onDisplayTypeChange}
          />
        )}
        {displayType === 'list' ? (
          <ViewList
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
