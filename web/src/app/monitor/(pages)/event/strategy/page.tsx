'use client';
import React, { useEffect, useState } from 'react';
import { Spin, Input, Button, Modal, message, Switch } from 'antd';
import useApiClient from '@/utils/request';
import assetStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import { ColumnItem, TreeItem, Pagination } from '@/app/monitor/types';
import {
  ObectItem,
  RuleInfo,
  TableDataItem,
} from '@/app/monitor/types/monitor';
import CustomTable from '@/components/custom-table';
import {
  deepClone,
  getRandomColor,
  findLabelById,
} from '@/app/monitor/utils/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { PlusOutlined } from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
const { confirm } = Modal;
import TreeSelector from '@/app/monitor/components/treeSelector';
import Permission from '@/components/permission';

const Strategy: React.FC = () => {
  const { t } = useTranslation();
  const { get, del, patch, isLoading } = useApiClient();
  const searchParams = useSearchParams();
  const { convertToLocalizedTime } = useLocalizedTime();
  const objId = searchParams.get('objId');
  const router = useRouter();
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
  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: t('common.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
      render: (_, { created_by }) => {
        return created_by ? (
          <div className="column-user" title={created_by}>
            <span
              className="user-avatar"
              style={{ background: getRandomColor() }}
            >
              {created_by.slice(0, 1).toLocaleUpperCase()}
            </span>
            <span className="user-name">{created_by}</span>
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
      render: (_, { created_at }) => (
        <>{created_at ? convertToLocalizedTime(created_at) : '--'}</>
      ),
    },
    {
      title: t('monitor.events.executionTime'),
      dataIndex: 'last_run_time',
      key: 'last_run_time',
      render: (_, { last_run_time }) => (
        <>{last_run_time ? convertToLocalizedTime(last_run_time) : '--'}</>
      ),
    },
    {
      title: t('monitor.events.effective'),
      dataIndex: 'effective',
      key: 'effective',
      render: (_, record) => (
        <Permission requiredPermissions={['Edit']}>
          <Switch
            size="small"
            loading={enableLoading}
            onChange={(val) => handleEffectiveChange(val, record.id)}
            checked={record.enable}
          />
        </Permission>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      fixed: 'right',
      render: (_, record) => (
        <>
          <Permission className="mr-[10px]" requiredPermissions={['Edit']}>
            <Button
              type="link"
              onClick={() => linkToStrategyDetail('edit', record)}
            >
              {t('common.edit')}
            </Button>
          </Permission>
          <Permission requiredPermissions={['Delete']}>
            <Button type="link" onClick={() => showDeleteConfirm(record)}>
              {t('common.delete')}
            </Button>
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
      await patch(`/monitor/api/monitor_policy/${id}/`, {
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
      const data = await get(`/monitor/api/monitor_policy/`, {
        params,
      });
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
      const data: ObectItem[] = await get('/monitor/api/monitor_object/', {
        params: {
          add_policy_count: true,
        },
      });
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
          title: (item.display_name || '--') + `(${item.policy_count})`,
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

  const showDeleteConfirm = (row: RuleInfo) => {
    confirm({
      title: t('common.deleteTitle'),
      content: t('common.deleteContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await del(`/monitor/api/monitor_policy/${row.id}/`);
            message.success(t('common.successfullyDeleted'));
            getAssetInsts(objectId);
          } finally {
            resolve(true);
          }
        });
      },
    });
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
      </div>
    </Spin>
  );
};
export default Strategy;
