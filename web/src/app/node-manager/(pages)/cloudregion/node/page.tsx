'use client';
import React, {
  useEffect,
  useRef,
  useState,
  useMemo,
  useCallback,
} from 'react';
import { Button, message, Space, Modal, Tooltip, Tag, Dropdown } from 'antd';
import {
  DownOutlined,
  ReloadOutlined,
  AppleFilled,
  WindowsFilled,
  HddFilled,
  ContainerFilled,
  CloudServerOutlined,
  ThunderboltFilled,
} from '@ant-design/icons';
import type { MenuProps, TableProps } from 'antd';
import nodeStyle from './index.module.scss';
import CollectorModal from './collectorModal';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem, Pagination } from '@/app/node-manager/types';
import { SearchFilters } from '@/app/node-manager/types/node';
import CustomTable from '@/components/custom-table';
import SearchCombination from './searchCombination';
import {
  useColumns,
  useTelegrafMap,
  useSidecarItems,
  useCollectorItems,
  useFieldConfigs,
} from '@/app/node-manager/hooks/node';
import MainLayout from '../mainlayout/layout';
import useApiClient from '@/utils/request';
import useNodeManagerApi from '@/app/node-manager/api';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { SafeStorage } from '@/app/node-manager/utils/safeStorage';
import ControllerInstall from './controllerInstall';
import ControllerUninstall from './controllerUninstall';
import CollectorInstallTable from './controllerTable';
import { useRouter, useSearchParams } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import { cloneDeep } from 'lodash';
import { ColumnItem } from '@/types';
import CollectorDetailDrawer from './collectorDetailDrawer';
import EditNode from './editNode';
import { useCommon } from '@/app/node-manager/context/common';
const { confirm } = Modal;

type TableRowSelection<T extends object = object> =
  TableProps<T>['rowSelection'];

const Node = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const cloudId = useCloudId();
  const searchParams = useSearchParams();
  const { isLoading, del } = useApiClient();
  const { getNodeList, delNode } = useNodeManagerApi();
  const sidecarItems = useSidecarItems();
  const collectorItems = useCollectorItems();
  const statusMap = useTelegrafMap();
  const fieldConfigs = useFieldConfigs();
  const commonContext = useCommon();
  const nodeStateEnum = commonContext?.nodeStateEnum || {};
  const name = searchParams.get('name') || '';
  const collectorRef = useRef<ModalRef>(null);
  const controllerRef = useRef<ModalRef>(null);
  const collectorDetailRef = useRef<any>(null);
  const editNodeRef = useRef<ModalRef>(null);
  const [nodeList, setNodeList] = useState<TableDataItem[]>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [showNodeTable, setShowNodeTable] = useState<boolean>(true);
  const [taskId, setTaskId] = useState<string>('');
  const [tableType, setTableType] = useState<string>('');
  const [showInstallController, setShowInstallController] =
    useState<boolean>(false);
  const [showInstallCollectorTable, setShowInstallCollectorTable] =
    useState<boolean>(false);
  const [activeColumns, setActiveColumns] = useState<ColumnItem[]>([]);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const columns = useColumns({
    checkConfig: (row: TableDataItem) => {
      const data = {
        cloud_region_id: cloudId.toString(),
        name,
      };
      SafeStorage.setSessionItem('cloudRegionInfo', { id: row.id });
      const params = new URLSearchParams(data);
      const targetUrl = `/node-manager/cloudregion/configuration?${params.toString()}`;
      router.push(targetUrl);
    },
    editNode: (row: TableDataItem) => {
      editNodeRef.current?.showModal({
        type: 'edit',
        form: row,
      });
    },
    deleteNode: async (row: TableDataItem) => {
      try {
        setLoading(true);
        await delNode(row.id as string);
        message.success(t('common.successfullyDeleted'));
        getNodes(searchFilters);
      } catch {
        setLoading(false);
      }
    },
  });

  const cancelInstall = useCallback(() => {
    setShowNodeTable(true);
    setShowInstallController(false);
  }, []);

  const cancelWait = useCallback(() => {
    setShowNodeTable(true);
    setShowInstallCollectorTable(false);
  }, []);

  const tableColumns = useMemo(() => {
    if (!activeColumns?.length) return columns;
    const _columns = cloneDeep(columns);
    const [first, ...remain] = activeColumns;
    _columns.splice(2, 0, first);
    _columns.splice(4, 0, ...remain);
    return _columns;
  }, [columns, nodeList, statusMap, activeColumns]);

  const enableOperateCollecter = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    const selectedNodes = (nodeList || []).filter((item) =>
      selectedRowKeys.includes(item.key)
    );
    const operatingSystems = selectedNodes.map((node) => node.operating_system);
    const uniqueOS = [...new Set(operatingSystems)];
    // 采集器：只检查操作系统是否一致
    return uniqueOS.length !== 1;
  }, [selectedRowKeys, nodeList]);

  const enableOperateController = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    const selectedNodes = (nodeList || []).filter((item) =>
      selectedRowKeys.includes(item.key)
    );
    const operatingSystems = selectedNodes.map((node) => node.operating_system);
    const uniqueOS = [...new Set(operatingSystems)];
    const installMethods = selectedNodes.map((node) => node.install_method);
    const uniqueInstallMethods = [...new Set(installMethods)];
    // 控制器：检查操作系统和安装方式是否都一致
    return uniqueOS.length !== 1 || uniqueInstallMethods.length !== 1;
  }, [selectedRowKeys, nodeList]);

  const getFirstSelectedNodeOS = useCallback(() => {
    const selectedNodes = (nodeList || []).filter((item) =>
      selectedRowKeys.includes(item.key)
    );
    return selectedNodes[0]?.operating_system || 'linux';
  }, [nodeList, selectedRowKeys]);

  useEffect(() => {
    if (!isLoading) {
      getCollectors();
      getNodes(searchFilters);
    }
  }, [isLoading]);

  useEffect(() => {
    if (!isLoading) getNodes(searchFilters);
  }, [pagination.current, pagination.pageSize]);

  const handleSidecarMenuClick: MenuProps['onClick'] = (e) => {
    if (e.key === 'uninstallSidecar') {
      const list = (nodeList || []).filter((item) =>
        selectedRowKeys.includes(item.key)
      );
      controllerRef.current?.showModal({
        type: e.key,
        form: { list },
      });
      return;
    }
    confirm({
      title: t('common.prompt'),
      content: t(`node-manager.cloudregion.node.${e.key}Tips`),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          const params = JSON.stringify(selectedRowKeys);
          try {
            await del(`/monitor/api/monitor_policy/${params}/`);
            message.success(t('common.operationSuccessful'));
            getNodes(searchFilters);
          } finally {
            resolve(true);
          }
        });
      },
    });
  };

  const handleCollectorMenuClick: MenuProps['onClick'] = (e) => {
    collectorRef.current?.showModal({
      type: e.key,
      ids: selectedRowKeys as string[],
      selectedsystem: getFirstSelectedNodeOS(),
    });
  };

  const SidecarmenuProps = {
    items: sidecarItems,
    onClick: handleSidecarMenuClick,
  };

  const CollectormenuProps = {
    items: collectorItems,
    onClick: handleCollectorMenuClick,
  };

  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys);
  };

  const getCheckboxProps = () => {
    return {
      disabled: false,
    };
  };

  const rowSelection: TableRowSelection<TableDataItem> = {
    selectedRowKeys,
    onChange: onSelectChange,
    getCheckboxProps: getCheckboxProps,
  };

  const handleSearchChange = (filters: SearchFilters) => {
    setSearchFilters(filters);
    getNodes(filters);
  };

  const getNodes = async (filters?: SearchFilters) => {
    setLoading(true);
    try {
      const params: any = {
        cloud_region_id: cloudId,
        page: pagination.current,
        page_size: pagination.pageSize,
      };

      if (filters && Object.keys(filters).length > 0) {
        params.filters = filters;
      }

      const res = await getNodeList(params);
      const data = (res?.items || []).map((item: TableDataItem) => ({
        ...item,
        key: item.id,
      }));
      setPagination((prev: Pagination) => ({
        ...prev,
        total: res?.count || 0,
      }));
      setNodeList(data);
    } finally {
      setLoading(false);
    }
  };

  const handleInstallController = () => {
    setShowNodeTable(false);
    setShowInstallController(true);
  };

  const getCollectors = async () => {
    setActiveColumns([
      {
        title: t('node-manager.cloudregion.node.nodeProperties'),
        dataIndex: 'node_properties',
        key: 'node_properties',
        onCell: () => ({
          style: {
            minWidth: 80,
          },
        }),
        render: (_: any, record: TableDataItem) => {
          // 获取操作系统映射
          const osValue = record.operating_system;
          const osLabel = nodeStateEnum?.os?.[osValue] || osValue;
          const OSIcon =
            osValue === 'linux'
              ? AppleFilled
              : osValue === 'windows'
                ? WindowsFilled
                : HddFilled;
          // 获取安装方式映射
          const installMethodValue = record.install_method;
          const installMethodLabel =
            nodeStateEnum?.install_method?.[installMethodValue] ||
            installMethodValue;
          const InstallIcon =
            installMethodValue === 'auto'
              ? ThunderboltFilled
              : CloudServerOutlined;
          // 获取节点类型映射
          const nodeTypeValue = record.node_type;
          const nodeTypeLabel =
            nodeStateEnum?.node_type?.[nodeTypeValue] || nodeTypeValue;
          const NodeTypeIcon =
            nodeTypeValue === 'container' ? ContainerFilled : HddFilled;
          return (
            <div className="flex gap-2">
              <Tooltip
                title={`${t(
                  'node-manager.cloudregion.node.nodeType'
                )}: ${nodeTypeLabel}`}
              >
                <NodeTypeIcon style={{ fontSize: '16px', cursor: 'pointer' }} />
              </Tooltip>
              <Tooltip
                title={`${t(
                  'node-manager.cloudregion.node.system'
                )}: ${osLabel}`}
              >
                <OSIcon style={{ fontSize: '16px', cursor: 'pointer' }} />
              </Tooltip>
              <Tooltip
                title={`${t(
                  'node-manager.cloudregion.node.installMethod'
                )}: ${installMethodLabel}`}
              >
                <InstallIcon style={{ fontSize: '16px', cursor: 'pointer' }} />
              </Tooltip>
            </div>
          );
        },
      },
      {
        title: t('node-manager.controller.controller'),
        dataIndex: 'controller',
        key: 'controller',
        onCell: () => ({
          style: {
            minWidth: 120,
          },
        }),
        render: (_: any, record: TableDataItem) => {
          // 根据当前行的操作系统动态确定 NATS-Executor ID
          const natsexecutorId =
            record.operating_system === 'linux'
              ? 'natsexecutor_linux'
              : 'natsexecutor_windows';
          const collectorTarget = (record.status?.collectors || []).find(
            (item: TableDataItem) => item.collector_id === natsexecutorId
          );
          const installTarget = (record.status?.collectors_install || []).find(
            (item: TableDataItem) => item.collector_id === natsexecutorId
          );
          const { title, tagColor } = getStatusInfo(
            collectorTarget,
            installTarget
          );
          return (
            <>
              <Tooltip
                title={`${record.status?.message}`}
                className="py-1 pr-1"
              >
                <Tag color={record.active ? 'success' : 'warning'}>Sidecar</Tag>
              </Tooltip>
              <Tooltip title={title}>
                <Tag color={tagColor} className="py-1 pr-1">
                  NATS-Executor
                </Tag>
              </Tooltip>
            </>
          );
        },
      },
      {
        title: t('node-manager.cloudregion.node.hostedProgram'),
        dataIndex: 'collectors',
        key: 'collectors',
        onCell: () => ({
          style: {
            minWidth: 200,
          },
        }),
        render: (_: any, record: TableDataItem) => {
          // 获取所有采集器（排除 NATS-Executor）
          const natsexecutorId =
            record.operating_system === 'linux'
              ? 'natsexecutor_linux'
              : 'natsexecutor_windows';

          const allCollectors = [
            ...(record.status?.collectors || []),
            ...(record.status?.collectors_install || []),
          ].filter(
            (collector: any) => collector.collector_id !== natsexecutorId
          );
          // 按状态分组
          const statusGroups = allCollectors.reduce(
            (groups: any, collector: any) => {
              const status = collector.status.toString();
              if (!groups[status]) {
                groups[status] = [];
              }
              groups[status].push(collector);
              return groups;
            },
            {}
          );
          // 生成状态标签
          const statusTags = Object.entries(statusGroups).map(
            ([status, collectors]: [string, any]) => {
              const statusInfo = statusMap[status] || {
                tagColor: 'default',
                text: t('node-manager.cloudregion.node.unknown'),
              };

              return (
                <Tag
                  key={status}
                  color={statusInfo.tagColor}
                  className="cursor-pointer mr-1 mb-1"
                  onClick={() => handleCollectorTagClick(record, allCollectors)}
                >
                  {statusInfo.text}: {collectors.length}
                </Tag>
              );
            }
          );
          return statusTags.length > 0 ? (
            <div className="flex">{statusTags}</div>
          ) : (
            <span>--</span>
          );
        },
      },
    ]);
  };

  const handleCollectorTagClick = (
    record: TableDataItem,
    collectors: any[]
  ) => {
    collectorDetailRef.current?.showModal({
      collectors,
      row: record,
    });
  };

  const getStatusInfo = (
    collectorTarget: TableDataItem,
    installTarget: TableDataItem
  ) => {
    const { message } = installTarget?.message || {};
    const statusCode = collectorTarget
      ? collectorTarget.status
      : installTarget?.status;
    const color = statusMap[statusCode]?.color || '#b2b5bd';
    const tagColor = statusMap[statusCode]?.tagColor || color || 'default';
    const status = statusMap[statusCode]?.text || '--';
    const engText = statusMap[statusCode]?.engText || '--';
    const str = message || engText;
    const title = collectorTarget ? collectorTarget.message : str;
    return {
      title,
      color,
      status,
      tagColor,
    };
  };

  const handleCollector = (config = { type: '', taskId: '' }) => {
    getNodes(searchFilters);
    if (['installCollector', 'uninstallController'].includes(config.type)) {
      setTaskId(config.taskId);
      setTableType(config.type);
      setShowNodeTable(false);
      setShowInstallCollectorTable(true);
    }
  };

  const handleTableChange = (pagination: any) => {
    setPagination(pagination);
  };

  return (
    <MainLayout>
      {showNodeTable && (
        <div className={`${nodeStyle.node} w-full h-full`}>
          <div className="overflow-hidden">
            <div className="flex items-center justify-between mb-4">
              <SearchCombination
                fieldConfigs={fieldConfigs}
                onChange={handleSearchChange}
                className="mr-[8px]"
              />
              <div className="flex">
                <PermissionWrapper requiredPermissions={['InstallController']}>
                  <Button
                    type="primary"
                    className="mr-[8px]"
                    onClick={handleInstallController}
                  >
                    {t('node-manager.cloudregion.node.installController')}
                  </Button>
                </PermissionWrapper>
                <Dropdown
                  className="mr-[8px]"
                  overlayClassName="customMenu"
                  menu={SidecarmenuProps}
                  disabled={enableOperateController}
                >
                  <Button>
                    <Space>
                      {t('node-manager.cloudregion.node.sidecar')}
                      <DownOutlined />
                    </Space>
                  </Button>
                </Dropdown>
                <Dropdown
                  className="mr-[8px]"
                  overlayClassName="customMenu"
                  menu={CollectormenuProps}
                  disabled={enableOperateCollecter}
                >
                  <Button>
                    <Space>
                      {t('node-manager.cloudregion.node.collector')}
                      <DownOutlined />
                    </Space>
                  </Button>
                </Dropdown>
                <ReloadOutlined onClick={() => getNodes(searchFilters)} />
              </div>
            </div>
            <CustomTable
              className={nodeStyle.table}
              columns={tableColumns}
              loading={loading}
              dataSource={nodeList}
              scroll={{ y: 'calc(100vh - 380px)', x: 'max-content' }}
              rowSelection={rowSelection}
              pagination={pagination}
              onChange={handleTableChange}
            />
            <CollectorModal
              ref={collectorRef}
              onSuccess={(config) => {
                handleCollector(config);
              }}
            />
            <ControllerUninstall
              ref={controllerRef}
              config={{
                os: getFirstSelectedNodeOS(),
                work_node: name,
              }}
              onSuccess={(config) => {
                handleCollector(config);
              }}
            />
            <CollectorDetailDrawer
              ref={collectorDetailRef}
              onSuccess={() => getNodes(searchFilters)}
            />
            <EditNode
              ref={editNodeRef}
              onSuccess={() => getNodes(searchFilters)}
            />
          </div>
        </div>
      )}
      {showInstallController && (
        <ControllerInstall
          config={{
            os: getFirstSelectedNodeOS(),
          }}
          cancel={cancelInstall}
        />
      )}
      {showInstallCollectorTable && (
        <CollectorInstallTable
          config={{ taskId, type: tableType }}
          cancel={cancelWait}
        />
      )}
    </MainLayout>
  );
};

export default Node;
