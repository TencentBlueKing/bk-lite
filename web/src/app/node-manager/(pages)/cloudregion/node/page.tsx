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
import { DownOutlined, ReloadOutlined } from '@ant-design/icons';
import type { MenuProps, TableProps, GetProps } from 'antd';
import nodeStyle from './index.module.scss';
import CollectorModal from './collectorModal';
import { useTranslation } from '@/utils/i18n';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import CustomTable from '@/components/custom-table';
import { useColumns } from '@/app/node-manager/hooks/node';
import Mainlayout from '../mainlayout/layout';
import useApiClient from '@/utils/request';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import useApiCollector from '@/app/node-manager/api/collector';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { useTelegrafMap } from '@/app/node-manager/constants/cloudregion';
import ControllerInstall from './controllerInstall';
import ControllerUninstall from './controllerUninstall';
import CollectorInstallTable from './controllerTable';
import { useRouter, useSearchParams } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import {
  OPERATE_SYSTEMS,
  useSidecaritems,
  useCollectoritems,
} from '@/app/node-manager/constants/cloudregion';
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
  const { getnodelist } = useApiCloudRegion();
  const { getCollectorlist } = useApiCollector();
  const sidecaritems = useSidecaritems();
  const collectoritems = useCollectoritems();
  const statusMap = useTelegrafMap();
  const name = searchParams.get('name') || '';
  const collectorRef = useRef<ModalRef>(null);
  const controllerRef = useRef<ModalRef>(null);
  const [nodelist, setNodelist] = useState<TableDataItem[]>();
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
  const checkConfig = (row: TableDataItem) => {
    const data = {
      cloud_region_id: cloudId.toString(),
      name,
    };
    sessionStorage.setItem('cloudRegionInfo', JSON.stringify({ id: row.id }));
    const params = new URLSearchParams(data);
    const targetUrl = `/node-manager/cloudregion/configuration?${params.toString()}`;
    router.push(targetUrl);
  };
  const columns = useColumns({ checkConfig });

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
  }, [columns, nodelist, statusMap, activeColumns]);

  const enableOperateCollecter = useMemo(() => {
    if (!selectedRowKeys.length) return true;
    return false;
  }, [selectedRowKeys, nodelist]);

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
      const list = (nodelist || []).filter((item) =>
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
    items: sidecaritems,
    onClick: handleSidecarMenuClick,
  };

  const CollectormenuProps = {
    items: collectoritems,
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
      const res = await getnodelist(params || getParams());
      const data = res.map((item: TableDataItem) => ({
        ...item,
        key: item.id,
      }));
      setNodelist(data);
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
    setNodelist([]);
    const params = getParams();
    params.operating_system = id;
    initData(params);
  };

  const getCollectors = async (selectedsystem: string) => {
    const data = await getCollectorlist({
      node_operating_system: selectedsystem,
    });
    const natsexecutors = ['natsexecutor_windows', 'natsexecutor_linux'];
    const columnItems = data
      .map((tex: TableDataItem) => {
        if (natsexecutors.includes(tex.id as string)) {
          return {
            title: tex.name,
            dataIndex: tex.id,
            render: (key: string, item: TableDataItem) => {
              const target = (item.status.collectors || []).find(
                (item: TableDataItem) => item.collector_id === tex.id
              );
              return target ? (
                <Tooltip title={`${target?.message}`}>
                  <Tag
                    bordered={false}
                    color={!target?.status ? 'success' : 'error'}
                  >
                    {!target?.status ? 'Running' : 'Error'}
                  </Tag>
                </Tooltip>
              ) : (
                '--'
              );
            },
          };
        }
        return {
          title: tex.name,
          dataIndex: tex.id,
          render: (key: string, item: TableDataItem) => {
            const target = (item.status.collectors || []).find(
              (item: TableDataItem) => item.collector_id === tex.id
            );
            return target ? (
              <Tooltip title={`${target?.message}`}>
                <div>
                  <span
                    className="recordStatus"
                    style={{
                      backgroundColor:
                        statusMap[target?.status]?.color || '#b2b5bd',
                    }}
                  ></span>
                  <span
                    style={{
                      color: statusMap[target?.status]?.color || '#b2b5bd',
                    }}
                  >
                    {!target?.status ? 'Running' : 'Error'}
                  </span>
                </div>
              </Tooltip>
            ) : (
              '--'
            );
          },
        };
      })
      .sort((item: TableDataItem) =>
        natsexecutors.includes(item.dataIndex) ? -1 : 0
      );
    setActiveColumns(columnItems);
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
    <Mainlayout>
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
            <div className="tablewidth">
              <CustomTable
                columns={tableColumns}
                loading={loading}
                dataSource={nodelist}
                scroll={{ y: 'calc(100vh - 326px)', x: 'calc(100vw - 300px)' }}
                rowSelection={rowSelection}
              />
            </div>
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
    </Mainlayout>
  );
};

export default Node;
