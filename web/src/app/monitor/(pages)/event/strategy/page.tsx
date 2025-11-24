'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Spin, Input, Button, message, Switch, Popconfirm } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import assetStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  TreeItem,
  Pagination,
  ObjectItem,
  ModalRef,
  TableDataItem,
} from '@/app/monitor/types';
import { SourceFeild } from '@/app/monitor/types/event';
import CustomTable from '@/components/custom-table';
import SelectAssets from './selectAssets';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { getRandomColor, findLabelById } from '@/app/monitor/utils/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { PlusOutlined } from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import TreeSelector from '@/app/monitor/components/treeSelector';
import Permission from '@/components/permission';
import { cloneDeep } from 'lodash';

const Strategy: React.FC = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const { getMonitorPolicy, patchMonitorPolicy, deleteMonitorPolicy } =
    useEventApi();
  const searchParams = useSearchParams();
  const { convertToLocalizedTime } = useLocalizedTime();
  const objId = searchParams.get('objId');
  const router = useRouter();
  const instRef = useRef<ModalRef>(null);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [enableLoading, setEnableLoading] = useState<boolean>(false);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [objectId, setObjectId] = useState<React.Key>('');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name',
      width: 100,
    },
    {
      title: t('monitor.events.monitoringTarget'),
      dataIndex: 'source',
      key: 'source',
      width: 80,
      render: (_, record) => (
        <Permission
          requiredPermissions={['Edit']}
          instPermissions={record.permission}
        >
          <Button
            type="link"
            onClick={() => {
              openInstModal(record);
            }}
          >
            {record.source.values?.length || 0}
          </Button>
        </Permission>
      ),
    },
    {
      title: t('common.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 100,
      render: (_, { created_by }) => {
        return created_by ? (
          <div className="column-user" title={created_by}>
            <span
              className="user-avatar"
              style={{ background: getRandomColor() }}
            >
              {created_by.slice(0, 1).toLocaleUpperCase()}
            </span>
            <span className="user-name">
              <EllipsisWithTooltip
                className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
                text={created_by}
              />
            </span>
          </div>
        ) : (
          <>--</>
        );
      },
    },
    {
      title: t('common.createTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (_, { created_at }) => (
        <>{created_at ? convertToLocalizedTime(created_at) : '--'}</>
      ),
    },
    {
      title: t('monitor.events.executionTime'),
      dataIndex: 'last_run_time',
      key: 'last_run_time',
      width: 160,
      render: (_, { last_run_time }) => (
        <>{last_run_time ? convertToLocalizedTime(last_run_time) : '--'}</>
      ),
    },
    {
      title: t('monitor.events.effective'),
      dataIndex: 'effective',
      key: 'effective',
      width: 80,
      render: (_, record) => (
        <Permission
          requiredPermissions={['Edit']}
          instPermissions={record.permission}
        >
          <Switch
            size="small"
            loading={enableLoading}
            onChange={(val) => handleEffectiveChange(val, record.id as number)}
            checked={record.enable}
          />
        </Permission>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <>
          <Permission
            className="mr-[10px]"
            requiredPermissions={['Edit']}
            instPermissions={record.permission}
          >
            <Button
              type="link"
              onClick={() => linkToStrategyDetail('edit', record as any)}
            >
              {t('common.edit')}
            </Button>
          </Permission>
          <Permission
            requiredPermissions={['Delete']}
            instPermissions={record.permission}
          >
            <Popconfirm
              title={t('common.deleteTitle')}
              description={t('common.deleteContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => deleteConfirm(record.id as React.Key)}
            >
              <Button type="link">{t('common.delete')}</Button>
            </Popconfirm>
          </Permission>
        </>
      ),
    },
  ];

  useEffect(() => {
    if (isLoading) return;
    getObjects();
  }, [isLoading]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [pagination.current, pagination.pageSize, objectId]);

  const handleObjectChange = async (id: string) => {
    setObjectId(id);
  };

  const openInstModal = (row: TableDataItem) => {
    const title = t('monitor.events.monitoringTarget');
    instRef.current?.showModal({
      title,
      type: 'add',
      form: {
        ...row.source,
        id: row.id,
      },
    });
  };

  const onChooseAssets = async (assets: SourceFeild, id: number) => {
    setTableLoading(true);
    patchMonitorPolicy(id, {
      source: assets,
    })
      .then(() => {
        message.success(t('common.successfullyModified'));
        getAssetInsts(objectId);
      })
      .catch(() => {
        setTableLoading(false);
      });
  };

  const getParams = (text?: string) => {
    return {
      name: text ? '' : searchText,
      page: pagination.current,
      page_size: pagination.pageSize,
      monitor_object_id: objectId || '',
    };
  };

  const handleEffectiveChange = async (val: boolean, id: number) => {
    try {
      setEnableLoading(true);
      await patchMonitorPolicy(id, {
        enable: val,
      });
      message.success(t(val ? 'common.started' : 'common.closed'));
      getAssetInsts(objectId);
    } finally {
      setEnableLoading(false);
    }
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getAssetInsts = async (objectId: React.Key, text?: string) => {
    try {
      setTableLoading(true);
      const params = getParams(text);
      params.monitor_object_id = objectId;
      const data = await getMonitorPolicy('', params);
      setTableData(data.items || []);
      setPagination((pre) => ({
        ...pre,
        total: data.count,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const getObjects = async () => {
    try {
      setTreeLoading(true);
      const data: ObjectItem[] = await getMonitorObject({
        add_policy_count: true,
      });
      setObjects(data);
      const _treeData = getTreeData(cloneDeep(data));
      setDefaultSelectObj(objId ? +objId : data[0]?.id);
      setTreeData(_treeData);
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
        title: (item.display_name || '--') + `(${item.policy_count})`,
        label: item.name || '--',
        key: item.id,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    return Object.values(groupedData);
  };

  const deleteConfirm = async (id: React.Key) => {
    setConfirmLoading(true);
    try {
      await deleteMonitorPolicy(id);
      message.success(t('common.successfullyDeleted'));
      getAssetInsts(objectId);
    } finally {
      setConfirmLoading(false);
    }
  };

  const enterText = () => {
    getAssetInsts(objectId);
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts(objectId, 'clear');
  };

  const linkToStrategyDetail = (type: string, row = { id: '', name: '' }) => {
    const monitorObjId = objectId as string;
    const monitorName = findLabelById(treeData, monitorObjId) as string;
    const params = new URLSearchParams({
      monitorObjId,
      monitorName,
      type,
      id: row.id,
      name: row.name,
    });
    const targetUrl = `/monitor/event/strategy/detail?${params.toString()}`;
    router.push(targetUrl);
  };

  return (
    <Spin spinning={treeLoading}>
      <div className={assetStyle.asset}>
        <div className={assetStyle.assetTree}>
          <TreeSelector
            data={treeData}
            defaultSelectedKey={defaultSelectObj as string}
            loading={treeLoading}
            onNodeSelect={handleObjectChange}
          />
        </div>
        <div className={assetStyle.table}>
          <div className={assetStyle.search}>
            <div>
              <Input
                className="w-[320px]"
                placeholder={t('common.searchPlaceHolder')}
                allowClear
                onPressEnter={enterText}
                onClear={clearText}
                onChange={(e) => setSearchText(e.target.value)}
              ></Input>
            </div>
            <Permission requiredPermissions={['Add']}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => linkToStrategyDetail('add')}
              >
                {t('common.add')}
              </Button>
            </Permission>
          </div>
          <CustomTable
            scroll={{ y: 'calc(100vh - 336px)', x: 'calc(100vw - 500px)' }}
            columns={columns}
            dataSource={tableData}
            pagination={pagination}
            loading={tableLoading}
            rowKey="id"
            onChange={handleTableChange}
          ></CustomTable>
        </div>
        <SelectAssets
          ref={instRef}
          monitorObject={objectId}
          objects={objects}
          onSuccess={onChooseAssets}
        />
      </div>
    </Spin>
  );
};
export default Strategy;
