'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import {
  Input,
  Button,
  message,
  Dropdown,
  Popconfirm,
  Space,
  Modal,
} from 'antd';
import useApiClient from '@/utils/request';
import useLogApi from '@/app/log/api/integration';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  ModalRef,
  Organization,
  Pagination,
  TableDataItem,
  TreeItem,
} from '@/app/log/types';
import { ObjectItem } from '@/app/log/types/event';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { DownOutlined } from '@ant-design/icons';
import { useCommon } from '@/app/log/context/common';
import { useAssetMenuItems } from '@/app/log/hooks/integration/common/other';
import { showGroupName } from '@/app/log/utils/common';
import EditConfig from './updateConfig';
import EditInstance from './editInstance';
import Permission from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { TableProps, MenuProps } from 'antd';
import TreeSelector from '@/app/log/components/tree-selector';
const { confirm } = Modal;

type TableRowSelection<T extends object = object> =
  TableProps<T>['rowSelection'];

const Asset = () => {
  const { isLoading } = useApiClient();
  const { getInstanceList, deleteLogInstance, getCollectTypes } = useLogApi();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const configRef = useRef<ModalRef>(null);
  const instanceRef = useRef<ModalRef>(null);
  const assetMenuItems = useAssetMenuItems();
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [frequence, setFrequence] = useState<number>(0);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [objectId, setObjectId] = useState<React.Key>('');
  const [treeLoading, setTreeLoading] = useState<boolean>(false);

  const handleAssetMenuClick: MenuProps['onClick'] = (e) => {
    openInstanceModal(
      {
        keys: selectedRowKeys,
      },
      e.key
    );
  };

  const assetMenuProps = {
    items: assetMenuItems,
    onClick: handleAssetMenuClick,
  };

  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      key: 'name',
      width: 100,
    },
    {
      title: t('common.belongingGroup'),
      dataIndex: 'organization',
      key: 'organization',
      width: 100,
      render: (_, { organization }) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={showGroupName(organization, organizationList)}
        />
      ),
    },
    {
      title: t('log.integration.collectionMethod'),
      dataIndex: 'collect_type__name',
      key: 'collect_type__name',
      width: 100,
    },
    {
      title: t('log.integration.collector'),
      dataIndex: 'collect_type__collector',
      key: 'collect_type__collector',
      width: 100,
    },
    {
      title: t('log.integration.collectionNode'),
      dataIndex: 'node_name',
      key: 'node_name',
      width: 100,
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 170,
      fixed: 'right',
      render: (_, record) => (
        <>
          <Permission requiredPermissions={['Edit']}>
            <Button
              type="link"
              onClick={() => openInstanceModal(record, 'edit')}
            >
              {t('common.edit')}
            </Button>
          </Permission>
          <Permission requiredPermissions={['Edit']}>
            <Button
              className="ml-[10px]"
              type="link"
              onClick={() => openConfigModal(record)}
            >
              {t('log.integration.updateConfigration')}
            </Button>
          </Permission>
          <Button
            className="ml-[10px]"
            type="link"
            onClick={() => viewLog(record)}
          >
            {t('log.integration.viewLogs')}
          </Button>
          <Permission requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('common.deleteTitle')}
              description={t('common.deleteContent')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              okButtonProps={{ loading: confirmLoading }}
              onConfirm={() => deleteInstConfirm(record)}
            >
              <Button type="link" className="ml-[10px]">
                {t('common.remove')}
              </Button>
            </Popconfirm>
          </Permission>
        </>
      ),
    },
  ];

  const enableOperateAsset = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    return false;
  }, [selectedRowKeys]);

  useEffect(() => {
    if (!isLoading) {
      getAssetInsts();
    }
  }, [pagination.current, pagination.pageSize, objectId]);

  useEffect(() => {
    if (!isLoading) {
      getObjects();
    }
  }, [isLoading]);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getAssetInsts('timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    pagination.current,
    pagination.pageSize,
    searchText,
    objectId,
  ]);

  const viewLog = (row: TableDataItem) => {
    const params = {
      query: `instance_id:"${row.id}"`,
    };
    const queryString = new URLSearchParams(params).toString();
    const url = `/log/search?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const getObjects = async () => {
    try {
      setTreeLoading(true);
      const data: ObjectItem[] = await getCollectTypes({
        add_instance_count: true,
      });
      setTreeData(getTreeData(data));
    } finally {
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObjectItem[]): TreeItem[] => {
    const groupedData = data.reduce((acc, item) => {
      if (!acc[item.collector]) {
        acc[item.collector] = {
          title: item.collector || '--',
          key: item.collector,
          children: [],
        };
      }
      acc[item.collector].children.push({
        title: `${item.name}(${item.instance_count || 0})`,
        label: item.name || '--',
        key: item.id,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    return [
      {
        title: t('common.all'),
        key: 'all',
        children: [],
      },
      ...Object.values(groupedData),
    ];
  };

  const onRefresh = () => {
    getObjects();
    getAssetInsts();
  };

  const showDeleteConfirm = () => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteLogInstance({
              clean_child_config: true,
              instance_ids: selectedRowKeys,
            });
            message.success(t('common.successfullyDeleted'));
            if (pagination?.current) {
              pagination.current > 1 &&
                tableData.length === 1 &&
                pagination.current--;
            }
            setSelectedRowKeys([]);
            getObjects();
            getAssetInsts();
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const openConfigModal = (row = {}) => {
    configRef.current?.showModal({
      title: t('log.integration.updateConfigration'),
      type: 'edit',
      form: {
        ...row,
        objName: '',
      },
    });
  };

  const openInstanceModal = (row = {}, type: string) => {
    if (type === 'batchDelete') {
      showDeleteConfirm();
      return;
    }
    instanceRef.current?.showModal({
      title: t(`common.${type}`),
      type,
      form: row,
    });
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getAssetInsts = async (type?: string) => {
    try {
      setTableLoading(type !== 'timer');
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
        collect_type_id: objectId === 'all' ? '' : objectId,
        name: type === 'clear' ? '' : searchText,
      };
      const data = await getInstanceList(params);
      setTableData(data?.items || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data?.count || 0,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const deleteInstConfirm = async (row: any) => {
    setConfirmLoading(true);
    try {
      const data = {
        instance_ids: [row.id],
        clean_child_config: true,
      };
      await deleteLogInstance(data);
      message.success(t('common.successfullyDeleted'));
      getAssetInsts();
      getObjects();
    } finally {
      setConfirmLoading(false);
    }
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts('clear');
  };

  //判断是否禁用按钮
  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys);
  };

  const rowSelection: TableRowSelection<TableDataItem> = {
    selectedRowKeys,
    onChange: onSelectChange,
  };

  const handleObjectChange = async (id: string) => {
    setTableData([]);
    setObjectId(id);
  };

  return (
    <div className="flex overflow-hidden">
      <TreeSelector
        data={treeData}
        loading={treeLoading}
        showAllMenu
        defaultSelectedKey="all"
        onNodeSelect={handleObjectChange}
      />
      <div className="w-[calc(100vw-240px)] min-w-[1040px] bg-[var(--color-bg-1)] p-[20px]">
        <div className="flex justify-between items-center mb-[10px]">
          <Input
            allowClear
            className="w-[320px]"
            placeholder={t('common.searchPlaceHolder')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={() => getAssetInsts()}
            onClear={clearText}
          ></Input>
          <div className="flex">
            <Dropdown
              className="mr-[8px]"
              overlayClassName="customMenu"
              menu={assetMenuProps}
              disabled={enableOperateAsset}
            >
              <Button>
                <Space>
                  {t('common.action')}
                  <DownOutlined />
                </Space>
              </Button>
            </Dropdown>
            <TimeSelector
              onlyRefresh
              onFrequenceChange={onFrequenceChange}
              onRefresh={onRefresh}
            />
          </div>
        </div>
        <CustomTable
          className="w-full"
          scroll={{ y: 'calc(100vh - 336px)', x: 'calc(100vw- 280x)' }}
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={tableLoading}
          rowKey="id"
          onChange={handleTableChange}
          rowSelection={rowSelection}
        ></CustomTable>
        <EditConfig ref={configRef} onSuccess={() => getAssetInsts()} />
        <EditInstance
          ref={instanceRef}
          organizationList={organizationList}
          onSuccess={() => getAssetInsts()}
        />
      </div>
    </div>
  );
};

export default Asset;
