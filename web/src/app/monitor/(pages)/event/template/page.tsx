'use client';
import React, { useEffect, useState } from 'react';
import useApiClient from '@/utils/request';
import templateStyle from './index.module.scss';
import { TreeItem, TableDataItem } from '@/app/monitor/types';
import { ObectItem } from '@/app/monitor/types/monitor';
import { OBJECT_ICON_MAP } from '@/app/monitor/constants/monitor';
import { deepClone, findLabelById } from '@/app/monitor/utils/common';
import { useRouter, useSearchParams } from 'next/navigation';
import TreeSelector from '@/app/monitor/components/treeSelector';
import EntityList from '@/components/entity-list';

const Template: React.FC = () => {
  const { get, post, isLoading } = useApiClient();
  const searchParams = useSearchParams();
  const objId = searchParams.get('objId');
  const router = useRouter();
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [objectId, setObjectId] = useState<React.Key>('');

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [objectId]);

  const handleObjectChange = async (id: string) => {
    setObjectId(id);
  };

  const getAssetInsts = async (objectId: React.Key) => {
    try {
      setTableLoading(true);
      const monitorName = findLabelById(treeData, objectId as string);
      const params = {
        monitor_object_name: monitorName,
      };
      const data = await post(`/monitor/api/monitor_policy/template/`, params);
      const list = data.map((item: TableDataItem, index: number) => ({
        ...item,
        id: index,
        description: item.description || '--',
        icon: OBJECT_ICON_MAP[monitorName as string] || 'Host',
      }));
      setTableData(list);
    } finally {
      setTableLoading(false);
    }
  };

  const getObjects = async () => {
    try {
      setTreeLoading(true);
      const data: ObectItem[] = await get('/monitor/api/monitor_object/');
      const _treeData = getTreeData(deepClone(data));
      setDefaultSelectObj(objId ? +objId : data[0]?.id);
      setTreeData(_treeData);
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
          title: item.display_name || '--',
          label: item.name || '--',
          key: item.id,
          children: [],
        });
        return acc;
      },
      {} as Record<string, TreeItem>
    );
    return Object.values(groupedData);
  };

  const handleCardClick = (type: string, row: TableDataItem) => {
    const monitorObjId = objectId as string;
    const monitorName = findLabelById(treeData, monitorObjId) as string;
    const params = new URLSearchParams({
      monitorObjId,
      monitorName,
      type,
      name: row?.name || '',
    });
    sessionStorage.setItem('strategyInfo', JSON.stringify(row));
    const targetUrl = `/monitor/event/strategy/detail?${params.toString()}`;
    router.push(targetUrl);
  };

  return (
    <div className={templateStyle.container}>
      <div className={templateStyle.containerTree}>
        <TreeSelector
          data={treeData}
          defaultSelectedKey={defaultSelectObj as string}
          loading={treeLoading}
          onNodeSelect={handleObjectChange}
        />
      </div>

      <div className={templateStyle.table}>
        <EntityList
          searchSize="middle"
          loading={tableLoading}
          data={tableData}
          onCardClick={(item) => {
            handleCardClick('builtIn', item);
          }}
        />
      </div>
    </div>
  );
};

export default Template;
