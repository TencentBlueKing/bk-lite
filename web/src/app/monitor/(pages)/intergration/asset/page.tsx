'use client';
import React, { useEffect, useState, useRef } from 'react';
import {
  Spin,
  Input,
  Button,
  Modal,
  message,
  Tooltip,
  Dropdown,
  Tag,
} from 'antd';
import useApiClient from '@/utils/request';
import assetStyle from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import {
  ColumnItem,
  TreeItem,
  ModalRef,
  Organization,
  Pagination,
  TableDataItem,
} from '@/app/monitor/types';
import {
  ObectItem,
  RuleInfo,
  ObjectInstItem,
} from '@/app/monitor/types/monitor';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';
import { PlusOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import RuleModal from './ruleModal';
import { useCommon } from '@/app/monitor/context/common';
import { deepClone, showGroupName } from '@/app/monitor/utils/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import TreeSelector from '@/app/monitor/components/treeSelector';
import EditConfig from './updateConfig';
import {
  OBJECT_INSTANCE_TYPE_MAP,
  NODE_STATUS_MAP,
} from '@/app/monitor/constants/monitor';
const { confirm } = Modal;
import Permission from '@/components/permission';

const Asset = () => {
  const { get, post, del, isLoading } = useApiClient();
  const { t } = useTranslation();
  const commonContext = useCommon();
  const { convertToLocalizedTime } = useLocalizedTime();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const ruleRef = useRef<ModalRef>(null);
  const configRef = useRef<ModalRef>(null);
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
  const [objects, setObjects] = useState<ObectItem[]>([]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);
  const [defaultSelectObj, setDefaultSelectObj] = useState<React.Key>('');
  const [objectId, setObjectId] = useState<React.Key>('');
  const [frequence, setFrequence] = useState<number>(0);

  const columns: ColumnItem[] = [
    {
      title: t('common.name'),
      dataIndex: 'instance_name',
      key: 'instance_name',
      ellipsis: true,
      width: 200,
    },
    {
      title: t('monitor.group'),
      dataIndex: 'organization',
      key: 'organization',
      width: 200,
      render: (_, { organization }) => (
        <>{showGroupName(organization, organizationList)}</>
      ),
    },
    {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <>
          <Button type="link" onClick={() => checkDetail(record)}>
            {t('common.detail')}
          </Button>
          <Permission requiredPermissions={['Delete']}>
            <Button
              type="link"
              onClick={() => showDeleteInstConfirm(record)}
              className="ml-[10px]"
            >
              {t('common.remove')}
            </Button>
          </Permission>
        </>
      ),
    },
  ];

  const childColumns: ColumnItem[] = [
    {
      title: t('monitor.intergrations.collectionMethod'),
      dataIndex: 'collect_type',
      key: 'collect_type',
      width: 150,
      render: (_, record) => <>{getCollectType(record)}</>,
    },
    {
      title: t('monitor.intergrations.collectionNode'),
      dataIndex: 'agent_id',
      key: 'agent_id',
      width: 150,
    },
    {
      title: t('monitor.intergrations.reportingStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (_, { time, status }) =>
        time ? (
          <Tag color={NODE_STATUS_MAP[status] || 'gray'}>
            {t(`monitor.intergrations.${status}`)}
          </Tag>
        ) : (
          <>--</>
        ),
    },
    {
      title: t('monitor.intergrations.lastReportTime'),
      dataIndex: 'time',
      key: 'time',
      width: 160,
      render: (_, { time }) => (
        <>{time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}</>
      ),
    },
    {
      title: t('monitor.intergrations.installationMethod'),
      dataIndex: 'config_id',
      key: 'config_id',
      width: 170,
      render: (_, record) => (
        <>
          {record.config_id
            ? t('monitor.intergrations.automatic')
            : t('monitor.intergrations.manual')}
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
          <Permission requiredPermissions={['Edit']}>
            <Button
              type="link"
              disabled={!record.config_id}
              onClick={() => openConfigModal(record)}
            >
              {t('monitor.intergrations.updateConfigration')}
            </Button>
          </Permission>
        </>
      ),
    },
  ];

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
        ? 'monitor.intergrations.addRule'
        : 'monitor.intergrations.editRule'
    );
    ruleRef.current?.showModal({
      title,
      type,
      form: row,
    });
  };

  const openConfigModal = (row = {}) => {
    configRef.current?.showModal({
      title: t('monitor.intergrations.updateConfigration'),
      type: 'edit',
      form: row,
    });
  };

  const checkDetail = (row: ObjectInstItem) => {
    const monitorItem = objects.find((item: ObectItem) => item.id === objectId);
    const params: any = {
      monitorObjId: objectId || '',
      name: monitorItem?.name || '',
      monitorObjDisplayName: monitorItem?.display_name || '',
      instance_id: row.instance_id,
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
      const data = await get(
        `/monitor/api/monitor_instance/${objectId}/list/`,
        {
          params: {
            page: pagination.current,
            page_size: pagination.pageSize,
            name: type === 'clear' ? '' : searchText,
          },
        }
      );
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
      const data = await get(`/monitor/api/monitor_instance_group_rule/`, {
        params: {
          monitor_object_id: objectId,
        },
      });
      setRuleList(data || []);
    } finally {
      setRuleLoading(false);
    }
  };

  const getObjects = async (type?: string) => {
    try {
      setTreeLoading(type !== 'timer');
      const data = await get(`/monitor/api/monitor_object/`, {
        params: {
          name: '',
          add_instance_count: true,
        },
      });
      setObjects(data);
      const _treeData = getTreeData(deepClone(data));
      setTreeData(_treeData);
      const defaultKey = data[0]?.id || defaultSelectObj || '';
      if (defaultKey) {
        setDefaultSelectObj(defaultKey);
      }
    } finally {
      setTreeLoading(false);
    }
  };

  const getTreeData = (data: ObectItem[]): TreeItem[] => {
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
    confirm({
      title: t('common.deleteTitle'),
      content: t('common.deleteContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await del(`/monitor/api/monitor_instance_group_rule/${row.id}/`);
            message.success(t('common.successfullyDeleted'));
            getRuleList(objectId);
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const showDeleteInstConfirm = (row: any) => {
    confirm({
      title: t('common.deleteTitle'),
      content: t('common.deleteContent'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await post(
              `/monitor/api/monitor_instance/remove_monitor_instance/`,
              {
                instance_ids: [row.instance_id],
                clean_child_config: true,
              }
            );
            message.success(t('common.successfullyDeleted'));
            getObjects();
            getAssetInsts(objectId);
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const clearText = () => {
    setSearchText('');
    getAssetInsts(objectId, 'clear');
  };

  const expandRow = async (expanded: boolean, row: any) => {
    const _dataSource = deepClone(tableData);
    const targetIndex = _dataSource.findIndex(
      (item: any) => item.instance_id === row.instance_id
    );
    try {
      if (targetIndex != -1 && expanded) {
        _dataSource[targetIndex].loading = true;
        setTableData(_dataSource);
        const res = await post(
          `/monitor/api/node_mgmt/get_instance_child_config/`,
          {
            instance_id: row.instance_id,
            instance_type:
              OBJECT_INSTANCE_TYPE_MAP[
                objects.find((item) => item.id === objectId)?.name || ''
              ],
          }
        );
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
      objects.find((item: ObectItem) => item.id === objectId)?.name || '';
    return ![
      'Pod',
      'Node',
      'Docker Container',
      'ESXI',
      'VM',
      'DataStorage',
    ].includes(monitorObjName);
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
          <TimeSelector
            onlyRefresh
            onFrequenceChange={onFrequenceChange}
            onRefresh={onRefresh}
          />
        </div>
        <CustomTable
          scroll={{ y: 'calc(100vh - 320px)', x: 'calc(100vh - 480px)' }}
          columns={columns}
          dataSource={tableData}
          pagination={pagination}
          loading={tableLoading}
          expandable={{
            showExpandColumn: getRowxpandable(),
            expandedRowRender: (record) => (
              <CustomTable
                scroll={{ x: 'calc(100vh - 480px)' }}
                loading={record.loading}
                rowKey="id"
                dataSource={record.dataSource || []}
                columns={childColumns}
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
        ></CustomTable>
      </div>
      <Spin spinning={ruleLoading}>
        <div className={assetStyle.rule}>
          <div className={`${assetStyle.ruleTips} relative`}>
            {t('monitor.intergrations.rule')}
            <Tooltip
              placement="top"
              title={t('monitor.intergrations.ruleTips')}
            >
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
            <Permission
              requiredPermissions={['Edit']}
              className={`${assetStyle.ruleItem} ${assetStyle.add} shadow-sm rounded-sm`}
            >
              <li onClick={() => openRuleModal('add')}>
                <PlusOutlined />
              </li>
            </Permission>
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
        onSuccess={operateRule}
      />
      <EditConfig ref={configRef} onSuccess={() => getAssetInsts(objectId)} />
    </div>
  );
};

export default Asset;
