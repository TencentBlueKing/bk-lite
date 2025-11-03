'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import {
  Spin,
  Input,
  Button,
  message,
  Tooltip,
  Dropdown,
  Tag,
  Popconfirm,
  Space,
} from 'antd';
import useApiClient from '@/utils/request';
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
import { RuleInfo, ObjectInstItem } from '@/app/monitor/types/integration';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { PlusOutlined, DownOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import RuleModal from './ruleModal';
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
import DeleteRule from './deleteRuleModal';
import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { NODE_STATUS_MAP } from '@/app/monitor/constants/integration';
import Permission from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { TableProps, MenuProps } from 'antd';
import { cloneDeep } from 'lodash';

type TableRowSelection<T extends object = object> =
  TableProps<T>['rowSelection'];

const Asset = () => {
  const { isLoading } = useApiClient();
  const { getInstanceList, getMonitorObject } = useMonitorApi();
  const {
    getInstanceGroupRule,
    getInstanceChildConfig,
    deleteMonitorInstance,
  } = useIntegrationApi();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getInstanceType } = useObjectConfigInfo();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const ruleRef = useRef<ModalRef>(null);
  const configRef = useRef<ModalRef>(null);
  const instanceRef = useRef<ModalRef>(null);
  const deleteModalRef = useRef<ModalRef>(null);
  const assetMenuItems = useAssetMenuItems();
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [ruleLoading, setRuleLoading] = useState<boolean>(false);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);
  const [ruleList, setRuleList] = useState<RuleInfo[]>([]);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [searchText, setSearchText] = useState<string>('');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
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

  const getChildColumns = (parentRecord: TableDataItem) => {
    const childColumns: ColumnItem[] = [
      {
        title: t('monitor.integrations.collectionMethod'),
        dataIndex: 'collect_type',
        key: 'collect_type',
        width: 150,
        render: (_, record) => <>{getCollectType(record)}</>,
      },
      {
        title: t('monitor.integrations.collectionNode'),
        dataIndex: 'agent_id',
        key: 'agent_id',
        width: 150,
      },
      {
        title: t('monitor.integrations.reportingStatus'),
        dataIndex: 'status',
        key: 'status',
        width: 150,
        render: (_, { time, status }) =>
          time ? (
            <Tag color={NODE_STATUS_MAP[status] || 'gray'}>
              {t(`monitor.integrations.${status}`)}
            </Tag>
          ) : (
            <>--</>
          ),
      },
      {
        title: t('monitor.integrations.lastReportTime'),
        dataIndex: 'time',
        key: 'time',
        width: 160,
        render: (_, { time }) => (
          <>
            {time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}
          </>
        ),
      },
      {
        title: t('monitor.integrations.installationMethod'),
        dataIndex: 'config_id',
        key: 'config_id',
        width: 170,
        render: (_, record) => (
          <>
            {record.config_ids?.length
              ? t('monitor.integrations.automatic')
              : t('monitor.integrations.manual')}
          </>
        ),
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        fixed: 'right',
        width: 100,
        render: (_, record) => (
          <>
            <Permission
              requiredPermissions={['Edit']}
              instPermissions={parentRecord.permission}
            >
              <Button
                type="link"
                disabled={!record.config_ids?.length}
                onClick={() => openConfigModal(record)}
              >
                {t('monitor.integrations.updateConfigration')}
              </Button>
            </Permission>
          </>
        ),
      },
    ];
    return childColumns;
  };

  const columns = useMemo(() => {
    const columnItems: ColumnItem[] = [
      {
        title: t('monitor.group'),
        dataIndex: 'organization',
        key: 'organization',
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
        width: 160,
        fixed: 'right',
        render: (_, record) => (
          <>
            <Button
              type="link"
              onClick={() => checkDetail(record as ObjectInstItem)}
            >
              {t('common.detail')}
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
  }, [objects, objectId, t]);

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
      getRuleList(objectId);
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
      getRuleList(objectId, 'timer');
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
    getRuleList(objectId);
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
    setRuleList([]);
    setObjectId(id);
  };

  const getCollectType = (row: Record<string, string>) => {
    if (row.collect_type === 'host') {
      return `${row.collect_type}(${row.config_type})`;
    }
    return row.collect_type || '--';
  };

  const openRuleModal = (type: string, row = {}) => {
    const title: string = t(
      type === 'add'
        ? 'monitor.integrations.addRule'
        : 'monitor.integrations.editRule'
    );
    ruleRef.current?.showModal({
      title,
      type,
      form: row,
    });
  };

  const openConfigModal = (row = {}) => {
    configRef.current?.showModal({
      title: t('monitor.integrations.updateConfigration'),
      type: 'edit',
      form: {
        ...row,
        objName: objects.find((item) => item.id === objectId)?.name || '',
      },
    });
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
      setExpandedRowKeys([]);
      const params = {
        page: pagination.current,
        page_size: pagination.pageSize,
        name: type === 'clear' ? '' : searchText,
      };
      const data = await getInstanceList(objectId, params);
      setTableData(data?.results || []);
      setPagination((prev: Pagination) => ({
        ...prev,
        total: data?.count || 0,
      }));
    } finally {
      setTableLoading(false);
    }
  };

  const getRuleList = async (objectId: React.Key, type?: string) => {
    try {
      setRuleLoading(type !== 'timer');
      const params = {
        monitor_object_id: objectId,
      };
      const data = await getInstanceGroupRule(params);
      setRuleList(data || []);
    } finally {
      setRuleLoading(false);
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
      const defaultKey = data[0]?.id || defaultSelectObj || '';
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
      acc[item.type].children.push({
        title: `${item.display_name || '--'}(${item.instance_count ?? 0})`,
        key: item.id,
        children: [],
      });
      return acc;
    }, {} as Record<string, TreeItem>);
    return Object.values(groupedData);
  };

  const operateRule = () => {
    getRuleList(objectId);
  };

  const showDeleteConfirm = (row: RuleInfo) => {
    deleteModalRef.current?.showModal({
      title: t('common.prompt'),
      form: row as Record<string, unknown>,
      type: 'delete',
    });
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

  const expandRow = async (expanded: boolean, row: any) => {
    const _dataSource = cloneDeep(tableData);
    const targetIndex = _dataSource.findIndex(
      (item: any) => item.instance_id === row.instance_id
    );
    try {
      if (targetIndex != -1 && expanded) {
        _dataSource[targetIndex].loading = true;
        setTableData(_dataSource);
        const data = {
          instance_id: row.instance_id,
          instance_type: getInstanceType(
            objects.find((item) => item.id === objectId)?.name || ''
          ),
        };
        const res = await getInstanceChildConfig(data);
        _dataSource[targetIndex].dataSource = res.map(
          (item: TableDataItem, index: number) => ({
            ...item,
            id: index,
          })
        );
        setTableData([..._dataSource]);
      }
    } finally {
      _dataSource[targetIndex].loading = false;
      setTableData([..._dataSource]);
    }
  };

  const getRowxpandable = () => {
    const monitorObjName =
      objects.find((item: ObjectItem) => item.id === objectId)?.name || '';
    return ![
      'Pod',
      'Node',
      'Docker Container',
      'ESXI',
      'VM',
      'DataStorage',
      'CVM',
    ].includes(monitorObjName);
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
          scroll={{ y: 'calc(100vh - 320px)' }}
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={tableLoading}
          expandable={{
            showExpandColumn: getRowxpandable(),
            columnWidth: 36,
            expandedRowRender: (record) => (
              <CustomTable
                scroll={{ x: 'calc(100vh - 480px)' }}
                loading={record.loading}
                rowKey="id"
                dataSource={record.dataSource || []}
                columns={getChildColumns(record)}
              />
            ),
            onExpand: (expanded, record) => {
              expandRow(expanded, record);
            },
            expandedRowKeys: expandedRowKeys,
            onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as any),
          }}
          rowKey="instance_id"
          onChange={handleTableChange}
          rowSelection={rowSelection}
        ></CustomTable>
      </div>
      <Spin spinning={ruleLoading}>
        <div className={assetStyle.rule}>
          <div className={`${assetStyle.ruleTips} relative`}>
            {t('monitor.integrations.rule')}
            <Tooltip placement="top" title={t('monitor.integrations.ruleTips')}>
              <div
                className="absolute cursor-pointer"
                style={{
                  top: '-3px',
                  right: '4px',
                }}
              >
                <Icon
                  type="a-shuoming2"
                  className="text-[14px] text-[var(--color-text-3)]"
                />
              </div>
            </Tooltip>
          </div>
          <ul className={assetStyle.ruleList}>
            <li onClick={() => openRuleModal('add')}>
              <Permission
                requiredPermissions={['Edit']}
                className={`${assetStyle.ruleItem} ${assetStyle.add} shadow-sm rounded-sm`}
              >
                <PlusOutlined />
              </Permission>
            </li>
            {ruleList.map((item) => (
              <li
                key={item.id}
                className={`${assetStyle.ruleItem} shadow-sm rounded-sm`}
              >
                <div className={assetStyle.editItem}>
                  <Icon
                    className={assetStyle.icon}
                    type={
                      item.type === 'condition' ? 'shaixuantiaojian' : 'xuanze'
                    }
                  />
                  <span title={item.name} className={assetStyle.ruleName}>
                    {item.name}
                  </span>
                  <div className={assetStyle.operate}>
                    <Dropdown
                      menu={{
                        items: [
                          {
                            key: 'edit',
                            label: (
                              <Permission requiredPermissions={['Edit']}>
                                <a
                                  className="text-[12px]"
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  onClick={() => openRuleModal('edit', item)}
                                >
                                  {t('common.edit')}
                                </a>
                              </Permission>
                            ),
                          },
                          {
                            key: 'delete',
                            label: (
                              <Permission requiredPermissions={['Delete']}>
                                <a
                                  className="text-[12px]"
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  onClick={() => showDeleteConfirm(item)}
                                >
                                  {t('common.delete')}
                                </a>
                              </Permission>
                            ),
                          },
                        ],
                      }}
                    >
                      <div>
                        <Icon
                          className={assetStyle.moreIcon}
                          type="sangedian-copy"
                        />
                      </div>
                    </Dropdown>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </Spin>
      <RuleModal
        ref={ruleRef}
        monitorObject={objectId}
        groupList={organizationList}
        objects={objects}
        onSuccess={operateRule}
      />
      <EditConfig ref={configRef} onSuccess={() => getAssetInsts(objectId)} />
      <DeleteRule ref={deleteModalRef} onSuccess={operateRule} />
      <EditInstance
        ref={instanceRef}
        organizationList={organizationList}
        onSuccess={() => getAssetInsts(objectId)}
      />
    </div>
  );
};

export default Asset;
