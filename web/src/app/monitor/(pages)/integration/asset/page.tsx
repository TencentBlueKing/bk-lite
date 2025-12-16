'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import {
  Input,
  Button,
  message,
  Dropdown,
  Tag,
  Popconfirm,
  Space,
  Tooltip,
} from 'antd';
import useApiClient from '@/utils/request';
import { useSearchParams } from 'next/navigation';
import useMonitorApi from '@/app/monitor/api';
import useIntegrationApi from '@/app/monitor/api/integration';
import assetStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  TreeItem,
  ModalRef,
  Organization,
  Pagination,
  TableDataItem,
  ObjectItem,
} from '@/app/monitor/types';
import {
  ObjectInstItem,
  TemplateDrawerRef,
} from '@/app/monitor/types/integration';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { DownOutlined } from '@ant-design/icons';
import { useCommon } from '@/app/monitor/context/common';
import { useAssetMenuItems } from '@/app/monitor/hooks/integration/common/assetMenuItems';
import {
  showGroupName,
  getBaseInstanceColumn,
} from '@/app/monitor/utils/common';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import TreeSelector from '@/app/monitor/components/treeSelector';
import EditConfig from './updateConfig';
import EditInstance from './editInstance';
import TemplateConfigDrawer from './templateConfigDrawer';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { EXCLUDED_CHILD_OBJECTS } from '@/app/monitor/constants/integration';
import Permission from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { TableProps, MenuProps } from 'antd';
import { cloneDeep } from 'lodash';

type TableRowSelection<T extends object = object> =
  TableProps<T>['rowSelection'];

const Asset = () => {
  const { isLoading } = useApiClient();
  const { getMonitorObject } = useMonitorApi();
  const { deleteMonitorInstance, getInstanceListByPrimaryObject } =
    useIntegrationApi();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getInstanceType } = useObjectConfigInfo();
  const searchparams = useSearchParams();
  const urlObjId = searchparams.get('objId');
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const configRef = useRef<ModalRef>(null);
  const instanceRef = useRef<ModalRef>(null);
  const templateDrawerRef = useRef<TemplateDrawerRef>(null);
  const assetMenuItems = useAssetMenuItems();
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
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>(
    urlObjId ? Number(urlObjId) : ''
  );
  const [objectId, setObjectId] = useState<React.Key>('');
  const [frequence, setFrequence] = useState<number>(0);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

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

  const openTemplateDrawer = (
    record: any,
    options?: { selectedConfigId?: string; showTemplateList?: boolean }
  ) => {
    const instanceType = getInstanceType(
      objects.find((item) => item.id === objectId)?.name || ''
    );

    templateDrawerRef.current?.showModal({
      instanceName: record.instance_name,
      instanceId: record.instance_id,
      instanceType: instanceType,
      selectedConfigId: options?.selectedConfigId,
      objName: objects.find((item) => item.id === objectId)?.name || '',
      plugins: record.plugins || [],
      showTemplateList: options?.showTemplateList ?? true,
    });
  };

  const columns = useMemo(() => {
    const columnItems: ColumnItem[] = [
      {
        title: t('monitor.integrations.collectionTemplate'),
        dataIndex: 'plugins',
        key: 'plugins',
        onCell: () => ({
          style: {
            minWidth: 150,
          },
        }),
        render: (_, record: any) => {
          const plugins = record.plugins || [];
          if (!plugins.length) return <>--</>;

          return (
            <div className="flex flex-wrap gap-1">
              {plugins.map((plugin: any, index: number) => {
                const isAuto = plugin.collect_mode === 'auto';
                const statusInfo = {
                  color: isAuto
                    ? plugin.status === 'normal' || plugin.status === 'online'
                      ? 'success'
                      : 'error'
                    : 'default',
                  text: isAuto
                    ? t('monitor.integrations.automatic')
                    : t('monitor.integrations.manual'),
                };

                const statusText =
                  plugin.status === 'normal' || plugin.status === 'online'
                    ? t('monitor.integrations.normal')
                    : t('monitor.integrations.unavailable');
                const timeText = plugin.time
                  ? convertToLocalizedTime(plugin.time)
                  : '--';
                const tooltipTitle = `${statusText} - ${t(
                  'monitor.integrations.lastReportTime'
                )}：${timeText}`;

                return (
                  <Tooltip
                    key={`${plugin.name}-${index}`}
                    title={tooltipTitle}
                    color="#000"
                  >
                    <Tag
                      color={statusInfo.color}
                      className="cursor-pointer"
                      onClick={() =>
                        openTemplateDrawer(record, {
                          selectedConfigId: isAuto ? plugin.name : undefined,
                          showTemplateList: false,
                        })
                      }
                    >
                      {plugin.collector
                        ? `${plugin.name}（${plugin.collector}）`
                        : plugin.name}
                    </Tag>
                  </Tooltip>
                );
              })}
            </div>
          );
        },
      },
      {
        title: t('monitor.group'),
        dataIndex: 'organization',
        key: 'organization',
        onCell: () => ({
          style: {
            minWidth: 120,
          },
        }),
        render: (_, { organization }) => (
          <EllipsisWithTooltip
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
            text={showGroupName(organization, organizationList)}
          />
        ),
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        width: 220,
        fixed: 'right',
        render: (_, record) => (
          <>
            <Button
              type="link"
              onClick={() => checkDetail(record as ObjectInstItem)}
            >
              {t('monitor.view')}
            </Button>
            <Permission
              requiredPermissions={['Edit']}
              instPermissions={record.permission}
            >
              <Button
                type="link"
                className="ml-[10px]"
                onClick={() => openInstanceModal(record, 'edit')}
              >
                {t('common.edit')}
              </Button>
            </Permission>
            <Permission
              requiredPermissions={['Edit']}
              instPermissions={record.permission}
            >
              <Button
                type="link"
                className="ml-[10px]"
                onClick={() =>
                  openTemplateDrawer(record, { showTemplateList: true })
                }
              >
                {t('monitor.integrations.configure')}
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
    const row = objects.find((item) => item.id === objectId) || {};
    return [
      ...getBaseInstanceColumn({
        objects,
        row: row as ObjectItem,
        t,
      }),
      ...columnItems,
    ];
  }, [objects, objectId, t, convertToLocalizedTime]);

  const enableOperateAsset = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    return false;
  }, [selectedRowKeys]);

  useEffect(() => {
    if (!isLoading) {
      getObjects();
    }
  }, [isLoading]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [objectId]);

  useEffect(() => {
    if (objectId) {
      getAssetInsts(objectId);
    }
  }, [pagination.current, pagination.pageSize]);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getObjects('timer');
      getAssetInsts(objectId, 'timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [
    frequence,
    objectId,
    pagination.current,
    pagination.pageSize,
    searchText,
  ]);

  const onRefresh = () => {
    getObjects();
    getAssetInsts(objectId);
  };

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const handleObjectChange = (id: string) => {
    setTableData([]);
    setObjectId(id);
  };

  const openInstanceModal = (row = {}, type: string) => {
    instanceRef.current?.showModal({
      title: t(`common.${type}`),
      type,
      form: row,
    });
  };

  const checkDetail = (row: ObjectInstItem) => {
    const monitorItem = objects.find(
      (item: ObjectItem) => item.id === objectId
    );
    const params: any = {
      monitorObjId: objectId || '',
      name: monitorItem?.name || '',
      monitorObjDisplayName: monitorItem?.display_name || '',
      instance_id: row.instance_id,
      icon: monitorItem?.icon || OBJECT_DEFAULT_ICON,
      instance_name: row.instance_name,
      instance_id_values: row.instance_id_values,
    };
    const queryString = new URLSearchParams(params).toString();
    const url = `/monitor/view/detail?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  const getAssetInsts = async (objectId: React.Key, type?: string) => {
    try {
      setTableLoading(type !== 'timer');
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
        name: type === 'clear' ? '' : searchText,
        id: objectId,
      };
      const data = await getInstanceListByPrimaryObject(params);

      setTableData(data?.results || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data?.count || 0,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const getObjects = async (type?: string) => {
    try {
      setTreeLoading(type !== 'timer');
      const params = {
        name: '',
        add_instance_count: true,
      };
      const data = await getMonitorObject(params);
      setObjects(data);
      const _treeData = getTreeData(cloneDeep(data));
      setTreeData(_treeData);
      const defaultKey = defaultSelectObj || data[0]?.id || '';
      if (defaultKey) {
        setDefaultSelectObj(defaultKey);
      }
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
      if (!EXCLUDED_CHILD_OBJECTS.includes(item.name)) {
        acc[item.type].children.push({
          title: `${item.display_name || '--'}(${item.instance_count ?? 0})`,
          key: item.id,
          children: [],
        });
      }
      return acc;
    }, {} as Record<string, TreeItem>);
    return Object.values(groupedData);
  };

  const deleteInstConfirm = async (row: any) => {
    setConfirmLoading(true);
    try {
      const data = {
        instance_ids: [row.instance_id],
        clean_child_config: true,
      };
      await deleteMonitorInstance(data);
      message.success(t('common.successfullyDeleted'));
      getObjects();
      getAssetInsts(objectId);
    } finally {
      setConfirmLoading(false);
    }
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts(objectId, 'clear');
  };

  //判断是否禁用按钮
  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys);
  };

  const rowSelection: TableRowSelection<TableDataItem> = {
    selectedRowKeys,
    onChange: onSelectChange,
    getCheckboxProps: (record: any) => {
      return {
        disabled: Array.isArray(record.permission)
          ? !record.permission.includes('Operate')
          : false,
      };
    },
  };

  return (
    <div className={assetStyle.asset}>
      <div className={assetStyle.tree}>
        <TreeSelector
          data={treeData}
          defaultSelectedKey={defaultSelectObj as string}
          onNodeSelect={handleObjectChange}
          loading={treeLoading}
        />
      </div>
      <div className={assetStyle.table}>
        <div className={assetStyle.search}>
          <Input
            allowClear
            className="w-[320px]"
            placeholder={t('common.searchPlaceHolder')}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={() => getAssetInsts(objectId)}
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
          scroll={{ y: 'calc(100vh - 330px)', x: 'max-content' }}
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={tableLoading}
          rowKey="instance_id"
          onChange={handleTableChange}
          rowSelection={rowSelection}
        ></CustomTable>
      </div>
      <EditConfig ref={configRef} onSuccess={() => getAssetInsts(objectId)} />
      <EditInstance
        ref={instanceRef}
        organizationList={organizationList}
        onSuccess={() => getAssetInsts(objectId)}
      />
      <TemplateConfigDrawer ref={templateDrawerRef} onSuccess={() => {}} />
    </div>
  );
};

export default Asset;
