'use client';
import React, { useEffect, useMemo, useState } from 'react';
import { Segmented } from 'antd';
import { ApartmentOutlined, BarsOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { deepClone } from '@/app/monitor/utils/common';
import { ObectItem } from '@/app/monitor/types/monitor';
import { TreeItem } from '@/app/monitor/types';
import viewStyle from './index.module.scss';
import TreeSelector from '@/app/monitor/components/treeSelector';
import ViewList from './viewList';
import ViewHive from './viewHive';

const Intergration = () => {
  const { get, isLoading } = useApiClient();
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [objects, setObjects] = useState<ObectItem[]>([]);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [objectId, setObjectId] = useState<React.Key>('');
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [displayType, setDisplayType] = useState<string>('list');

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

  const getObjects = async () => {
    try {
      setTreeLoading(true);
      const data: ObectItem[] = await get('/monitor/api/monitor_object/', {
        params: {
          add_instance_count: true,
        },
      });
      const _treeData = getTreeData(deepClone(data));
      setTreeData(_treeData);
      setObjects(data);
      setDefaultSelectObj(data[0]?.id);
    } finally {
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObectItem[]): TreeItem[] => {
    const groupedData = data.reduce(
      (acc, item) => {
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
      },
      {} as Record<string, TreeItem>
    );
    return Object.values(groupedData).filter((item) => item.key !== 'Other');
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
            options={[
              { value: 'list', icon: <BarsOutlined /> },
              { value: 'view', icon: <ApartmentOutlined /> },
            ]}
            value={displayType}
            onChange={onDisplayTypeChange}
          />
        )}
        {displayType === 'list' ? (
          <ViewList objects={objects} objectId={objectId} showTab={showTab} />
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
export default Intergration;
