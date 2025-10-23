'use client';
import React, {
  useEffect,
  useRef,
  useState,
  useMemo,
  useCallback,
} from 'react';
import {
  Button,
  Input,
  message,
  Space,
  Modal,
  Tooltip,
  Tag,
  Dropdown,
  Segmented,
} from 'antd';
import {
  DownOutlined,
  ReloadOutlined,
  EllipsisOutlined,
} from '@ant-design/icons';
import type { MenuProps, TableProps, GetProps } from 'antd';
import nodeStyle from './index.module.scss';
import CollectorModal from './collectorModal';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import CustomTable from '@/components/custom-table';
import {
  useColumns,
  useTelegrafMap,
  useSidecarItems,
  useCollectorItems,
} from '@/app/node-manager/hooks/node';
import MainLayout from '../mainlayout/layout';
import useApiClient from '@/utils/request';
import useApiCloudRegion from '@/app/node-manager/api/cloudRegion';
import useApiCollector from '@/app/node-manager/api/collector';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import {
  COLLECTOR_LABEL,
  DISPLAY_PLUGINS,
} from '@/app/node-manager/constants/collector';
import ControllerInstall from './controllerInstall';
import ControllerUninstall from './controllerUninstall';
import CollectorInstallTable from './controllerTable';
import { useRouter, useSearchParams } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import { cloneDeep } from 'lodash';
import { ColumnItem } from '@/types';
const { confirm } = Modal;
const { Search } = Input;

type TableRowSelection<T extends object = object> =
  TableProps<T>['rowSelection'];
type SearchProps = GetProps<typeof Input.Search>;

const Node = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const cloudId = useCloudId();
  const searchParams = useSearchParams();
  const { isLoading, del } = useApiClient();
  const { getNodeList, delNode } = useApiCloudRegion();
  const { getCollectorlist } = useApiCollector();
  const sidecarItems = useSidecarItems();
  const collectorItems = useCollectorItems();
  const statusMap = useTelegrafMap();
  const name = searchParams.get('name') || '';
  const collectorRef = useRef<ModalRef>(null);
  const controllerRef = useRef<ModalRef>(null);
  const [nodeList, setNodeList] = useState<TableDataItem[]>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [showNodeTable, setShowNodeTable] = useState<boolean>(true);
  const [searchText, setSearchText] = useState<string>('');
  const [taskId, setTaskId] = useState<string>('');
  const [tableType, setTableType] = useState<string>('');
  const [showInstallController, setShowInstallController] =
    useState<boolean>(false);
  const [showInstallCollectorTable, setShowInstallCollectorTable] =
    useState<boolean>(false);
  const [system, setSystem] = useState<string>('linux');
  const [activeColumns, setActiveColumns] = useState<ColumnItem[]>([]);
  const DISPLAY_PLUGINS_COUNT = 4; // 最多展示几个插件

  const columns = useColumns({
    checkConfig: (row: TableDataItem) => {
      const data = {
        cloud_region_id: cloudId.toString(),
        name,
      };
      sessionStorage.setItem('cloudRegionInfo', JSON.stringify({ id: row.id }));
      const params = new URLSearchParams(data);
      const targetUrl = `/node-manager/cloudregion/configuration?${params.toString()}`;
      router.push(targetUrl);
    },
    deleteNode: async (row: TableDataItem) => {
      try {
        setLoading(true);
        await delNode(row.id as string);
        message.success(t('common.successfullyDeleted'));
        getNodes('refresh');
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

  const enableOperateSideCar = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    return false;
  }, [selectedRowKeys]);

  const tableColumns = useMemo(() => {
    if (!activeColumns?.length) return columns;
    const _columns = cloneDeep(columns);
    _columns.splice(3, 0, ...activeColumns);
    return _columns;
  }, [columns, nodeList, statusMap, activeColumns]);

  const enableOperateCollecter = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    return false;
  }, [selectedRowKeys, nodeList]);

  useEffect(() => {
    if (!isLoading) {
      initData();
    }
  }, [isLoading]);

  const initData = (params?: any) => {
    setLoading(true);
    const getNodeData = params ? getNodes('init', params) : getNodes('init');
    Promise.all([
      getNodeData,
      getCollectors(params?.operating_system || system),
    ]).finally(() => {
      setLoading(false);
    });
  };

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
            getNodes('refresh');
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
      selectedsystem: system,
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

  //选择相同的系统节点，判断是否禁用按钮
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

  const onSearch: SearchProps['onSearch'] = (value) => {
    setSearchText(value);
    const params = getParams();
    params.name = value;
    getNodes('refresh', params);
  };

  const getParams = () => {
    return {
      name: searchText,
      operating_system: system,
      cloud_region_id: cloudId,
    };
  };

  const getNodes = async (
    type: string,
    params?: {
      name?: string;
      operating_system?: string;
      cloud_region_id?: number;
    }
  ) => {
    setLoading(true);
    try {
      const res = await getNodeList(params || getParams());
      const data = res.map((item: TableDataItem) => ({
        ...item,
        key: item.id,
      }));
      setNodeList(data);
    } finally {
      setLoading(type === 'init');
    }
  };

  const handleInstallController = () => {
    setShowNodeTable(false);
    setShowInstallController(true);
  };

  const onSystemChange = (id: string) => {
    setSystem(id);
    setActiveColumns([]);
    setNodeList([]);
    const params = getParams();
    params.operating_system = id;
    initData(params);
  };

  const getCollectorLabelKey = (value: string = '') => {
    for (const key in COLLECTOR_LABEL) {
      if (COLLECTOR_LABEL[key].includes(value)) {
        return key;
      }
    }
  };

  const getCollectorName = (id: string, data: TableDataItem[] = []) => {
    return data.find((item: TableDataItem) => item.id === id)?.name || '--';
  };

  const renderColunms = (
    record: TableDataItem,
    {
      type,
      data,
    }: {
      type: string;
      data: any;
    }
  ) => {
    const collectors = [
      ...new Set(
        [
          ...(record.status?.collectors_install || []),
          ...(record.status?.collectors || []),
        ].map((item) => item.collector_id)
      ),
    ].filter((id: string) => {
      const labelKey = getCollectorName(id, data || []);
      return getCollectorLabelKey(labelKey) === type;
    });
    const tagList = collectors.map((collectorId: string) => {
      const collectorTarget = (record.status?.collectors || []).find(
        (dataItem: TableDataItem) => dataItem.collector_id === collectorId
      );
      const installTarget = (record.status?.collectors_install || []).find(
        (dataItem: TableDataItem) => dataItem.collector_id === collectorId
      );
      const { title, tagColor } = getStatusInfo(collectorTarget, installTarget);
      return (
        <Tooltip
          title={title}
          key={collectorId}
          zIndex={99999}
          className="py-1 pr-1"
        >
          <Tag color={tagColor}>
            {getCollectorName(collectorId, data || [])}
          </Tag>
        </Tooltip>
      );
    });
    if (tagList.length) {
      const items = tagList.slice(DISPLAY_PLUGINS_COUNT).map((tag, index) => ({
        key: index,
        label: tag,
      }));
      return (
        <div className="flex items-center justify-center">
          {tagList.length > DISPLAY_PLUGINS_COUNT ? (
            <>
              {tagList.slice(0, DISPLAY_PLUGINS_COUNT)}
              <Dropdown menu={{ items }} placement="bottom">
                <EllipsisOutlined className="text-[var(--color-primary)] text-[16px] cursor-pointer" />
              </Dropdown>
            </>
          ) : (
            tagList
          )}
        </div>
      );
    }
    return '--';
  };

  const getCollectors = async (selectedsystem: string) => {
    const data =
      (await getCollectorlist({
        node_operating_system: selectedsystem,
      })) || [];
    const natsexecutorId =
      selectedsystem === 'linux'
        ? 'natsexecutor_linux'
        : 'natsexecutor_windows';
    const columnItems: any = DISPLAY_PLUGINS.map((type: string) => ({
      title: type,
      dataIndex: type,
      key: type,
      onCell: () => ({
        style: {
          minWidth: 120,
        },
      }),
      align: 'center',
      render: (_: any, record: TableDataItem) =>
        renderColunms(record, {
          type,
          data,
        }),
    }));
    setActiveColumns([
      {
        title: 'Controller',
        dataIndex: natsexecutorId,
        key: natsexecutorId,
        onCell: () => ({
          style: {
            minWidth: 120,
          },
        }),
        render: (_: any, record: TableDataItem) => {
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
      ...columnItems,
    ]);
  };

  const getStatusInfo = (
    collectorTarget: TableDataItem,
    installTarget: TableDataItem
  ) => {
    const { message } = installTarget?.message || {};
    const statusCode = collectorTarget
      ? collectorTarget.status
      : installTarget?.status;
    const tagColor = statusMap[statusCode]?.tagColor || 'default';
    const color = statusMap[statusCode]?.color || '#b2b5bd';
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
    getNodes('refresh');
    if (['installCollector', 'uninstallController'].includes(config.type)) {
      setTaskId(config.taskId);
      setTableType(config.type);
      setShowNodeTable(false);
      setShowInstallCollectorTable(true);
    }
  };

  return (
    <MainLayout>
      {showNodeTable && (
        <div className={`${nodeStyle.node} w-full h-full`}>
          <div className="overflow-hidden">
            <div className="flex justify-between w-full overflow-y-hidden mb-4">
              <Segmented
                options={OPERATE_SYSTEMS}
                value={system}
                onChange={onSystemChange}
              />
              <div>
                <Search
                  className="w-64 mr-[8px]"
                  placeholder={t('common.search')}
                  enterButton
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  onSearch={onSearch}
                />
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
                  disabled={enableOperateSideCar}
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
                <ReloadOutlined onClick={() => getNodes('refresh')} />
              </div>
            </div>
            <CustomTable
              className={nodeStyle.table}
              columns={tableColumns}
              loading={loading}
              dataSource={nodeList}
              scroll={{ y: 'calc(100vh - 326px)', x: 'max-content' }}
              rowSelection={rowSelection}
            />
            <CollectorModal
              ref={collectorRef}
              onSuccess={(config) => {
                handleCollector(config);
              }}
            />
            <ControllerUninstall
              ref={controllerRef}
              config={{ os: system, work_node: name }}
              onSuccess={(config) => {
                handleCollector(config);
              }}
            />
          </div>
        </div>
      )}
      {showInstallController && (
        <ControllerInstall config={{ os: system }} cancel={cancelInstall} />
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
