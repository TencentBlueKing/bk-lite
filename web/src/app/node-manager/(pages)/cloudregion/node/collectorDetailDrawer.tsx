'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useRef,
  useEffect,
} from 'react';
import { Tag, Empty, Button, Spin, Badge, Popconfirm, message } from 'antd';
import { RightOutlined, GlobalOutlined, EditOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import { useTelegrafMap } from '@/app/node-manager/hooks/node';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { STATUS_CODE_PRIORITY } from '@/app/node-manager/constants/cloudregion';
import {
  ModalSuccess,
  TableDataItem,
  ModalRef,
} from '@/app/node-manager/types';
import {
  ConfigData,
  ConfigListProps,
} from '@/app/node-manager/types/cloudregion';
import { Pagination } from '@/app/node-manager/types';
import useNodeManagerApi from '@/app/node-manager/api';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import CustomTable from '@/components/custom-table';
import ConfigModal from './configModal';
import PermissionWrapper from '@/components/permission';
import { useUserInfoContext } from '@/context/userInfo';

interface CollectorDetailDrawerProps extends ModalSuccess {
  nodeStateEnum?: any;
}

const CollectorDetailDrawer = forwardRef<ModalRef, CollectorDetailDrawerProps>(
  ({ onSuccess, nodeStateEnum = {} }, ref) => {
    const { t } = useTranslation();
    const { convertToLocalizedTime } = useLocalizedTime();
    const statusMap = useTelegrafMap();
    const cloudId = useCloudId();
    const { getConfiglist, getChildConfig, deleteSubConfig } =
      useNodeManagerApi();
    const commonContext = useUserInfoContext();
    const adminRef = useRef(commonContext?.roles || []);
    const isAdmin =
      adminRef.current.includes('admin') ||
      adminRef.current.includes('node--admin');
    const configModalRef = useRef<ModalRef>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [selectedCollector, setSelectedCollector] =
      useState<TableDataItem | null>(null);
    const [collectors, setCollectors] = useState<TableDataItem[]>([]);
    const [form, setForm] = useState<TableDataItem>({});
    const [allConfigs, setAllConfigs] = useState<ConfigData[]>([]);
    const [mainConfig, setMainConfig] = useState<ConfigData | null>(null);
    const [mainConfigLoading, setMainConfigLoading] = useState<boolean>(false);
    const [subConfigs, setSubConfigs] = useState<any[]>([]);
    const [subConfigLoading, setSubConfigLoading] = useState<boolean>(false);
    const [subConfigPagination, setSubConfigPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 10,
    });

    useImperativeHandle(ref, () => ({
      showModal: ({ collectors, row }) => {
        setVisible(true);
        // 过滤采集器列表:如果同一个collector_id同时存在于collectors和collectors_install中,只保留collectors中的
        const collectorsFromStatus = row.status?.collectors || [];
        const collectorsInstallFromStatus =
          row.status?.collectors_install || [];
        const collectorIds = new Set(
          collectorsFromStatus.map((c: any) => c.collector_id)
        );
        const filteredCollectors = [
          ...collectors.filter((c: any) =>
            collectorsFromStatus.some(
              (sc: any) => sc.collector_id === c.collector_id
            )
          ),
          ...collectors.filter(
            (c: any) =>
              collectorsInstallFromStatus.some(
                (sc: any) => sc.collector_id === c.collector_id
              ) && !collectorIds.has(c.collector_id)
          ),
        ];
        setCollectors(filteredCollectors);
        setForm(row);
        if (filteredCollectors.length > 0) {
          const sortedCollectors = [...filteredCollectors].sort((a, b) => {
            const priorityA = STATUS_CODE_PRIORITY[a.status] || 999;
            const priorityB = STATUS_CODE_PRIORITY[b.status] || 999;
            return priorityA - priorityB;
          });
          const firstCollector = sortedCollectors[0];
          // 处理message为对象的情况
          if (
            firstCollector.message &&
            typeof firstCollector.message === 'object'
          ) {
            firstCollector.message =
              firstCollector.message?.final_message || '';
          }
          setSelectedCollector(firstCollector);
          setMainConfig({
            key: '',
            collector_id: firstCollector.collector_id,
            name: '',
            operatingSystem: '',
            configInfo: '',
            nodeCount: 0,
            collector_name: firstCollector.collector_name,
          } as ConfigData);
          if (firstCollector.collector_id && row.id) {
            // 加载所有配置数据
            loadAllConfigs(
              row.id as string,
              firstCollector.collector_id as string
            );
          }
        }
      },
    }));

    // 加载所有配置数据（只调用一次 config_node_asso 接口）
    const loadAllConfigs = async (nodeId: string, firstCollectorId: string) => {
      setMainConfigLoading(true);
      try {
        const configList = await getConfiglist({
          cloud_region_id: cloudId,
          node_id: nodeId,
        });
        const configData: ConfigData[] = configList.map(
          (config: ConfigListProps) => ({
            ...config,
            key: config.id,
            operatingSystem: config.operating_system,
            configInfo: config.config_template || '',
            nodeCount: config.nodes?.length || 0,
            collector_name: config.collector_name || '',
          })
        );
        setAllConfigs(configData);
        const targetConfig = configData.find(
          (config) => config.collector_id === firstCollectorId
        );
        if (targetConfig) {
          setMainConfig(targetConfig);
          loadSubConfigs(targetConfig.key);
        } else {
          setMainConfig(null);
        }
      } catch (error) {
        console.error('Failed to load configs:', error);
      } finally {
        setMainConfigLoading(false);
      }
    };

    // 前端过滤主配置（根据 collector_id）
    const filterMainConfigByCollectorId = (collectorId: string) => {
      const targetConfig = allConfigs.find(
        (config) => config.collector_id === collectorId
      );
      if (targetConfig) {
        setMainConfig(targetConfig);
        loadSubConfigs(targetConfig.key);
      } else {
        setMainConfig(null);
        setSubConfigs([]);
        setSubConfigPagination({ current: 1, total: 0, pageSize: 10 });
      }
    };

    // 加载子配置
    const loadSubConfigs = async (
      configId: string,
      page?: number,
      pageSize?: number
    ) => {
      setSubConfigLoading(true);
      try {
        const params = {
          collector_config_id: configId,
          search: '',
          page: page || subConfigPagination.current,
          page_size: pageSize || subConfigPagination.pageSize,
        };
        const res = await getChildConfig(params);
        const data = res.items.map((item: any) => ({
          ...item,
          key: item.id,
        }));
        setSubConfigs(data);
        setSubConfigPagination((prev) => ({
          ...prev,
          current: params.page,
          pageSize: params.page_size,
          total: res?.count || 0,
        }));
      } catch (error) {
        console.error('Failed to load sub configs:', error);
      } finally {
        setSubConfigLoading(false);
      }
    };

    // 子配置分页变化
    useEffect(() => {
      if (mainConfig && visible) {
        loadSubConfigs(
          mainConfig.key,
          subConfigPagination.current,
          subConfigPagination.pageSize
        );
      }
    }, [subConfigPagination.current, subConfigPagination.pageSize]);

    const getSortedGroupedCollectors = () => {
      const groupedCollectors = collectors.reduce((groups, collector) => {
        const status = collector.status.toString();
        if (!groups[status]) {
          groups[status] = [];
        }
        groups[status].push(collector);
        return groups;
      }, {} as Record<string, TableDataItem[]>);
      return Object.entries(groupedCollectors).sort(([statusA], [statusB]) => {
        const priorityA = STATUS_CODE_PRIORITY[Number(statusA)] || 999;
        const priorityB = STATUS_CODE_PRIORITY[Number(statusB)] || 999;
        return priorityA - priorityB;
      });
    };

    const handleCancel = () => {
      setVisible(false);
      setCollectors([]);
      setSelectedCollector(null);
      setForm({});
      setMainConfig(null);
      setSubConfigs([]);
      setSubConfigPagination({ current: 1, total: 0, pageSize: 10 });
      setMainConfigLoading(false);
      setSubConfigLoading(false);
    };

    const handleCollectorClick = (collector: TableDataItem) => {
      setSubConfigs([]);
      setSubConfigPagination((pre) => ({
        ...pre,
        count: 0,
        current: 1,
      }));
      if (collector.message && typeof collector.message === 'object') {
        collector.message = collector.message?.final_message || '';
      }
      setSelectedCollector(collector);
      if (collector.collector_id) {
        filterMainConfigByCollectorId(collector.collector_id as string);
      }
    };

    // 处理主配置编辑
    const handleMainConfigEdit = () => {
      if (mainConfig) {
        configModalRef.current?.showModal({
          type: 'edit',
          form: mainConfig,
        });
      }
    };

    // 处理子配置编辑
    const handleSubConfigEdit = (record: any) => {
      configModalRef.current?.showModal({
        type: 'edit_child',
        form: record,
      });
    };

    // 配置弹窗成功回调
    const handleConfigModalSuccess = async (operateType: string) => {
      if (['add_child', 'edit_child'].includes(operateType)) {
        if (mainConfig) {
          await loadSubConfigs(mainConfig.key);
        }
        return;
      }
      if (form.id && selectedCollector?.collector_id) {
        await loadAllConfigs(
          form.id as string,
          selectedCollector.collector_id as string
        );
      }
      onSuccess?.();
    };

    // 子配置表格列定义
    const subConfigColumns = [
      {
        title: t('node-manager.cloudregion.Configuration.collectionType'),
        dataIndex: 'collect_type',
        key: 'collect_type',
        width: 150,
        render: (text: string) => <Tag color="green">{text}</Tag>,
      },
      {
        title: t('node-manager.cloudregion.Configuration.configurationType'),
        dataIndex: 'config_type',
        key: 'config_type',
        width: 150,
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        width: 100,
        fixed: 'right' as const,
        render: (_: any, record: any) => (
          <>
            <PermissionWrapper requiredPermissions={['EditSubConfiguration']}>
              <Button type="link" onClick={() => handleSubConfigEdit(record)}>
                {t('common.edit')}
              </Button>
            </PermissionWrapper>
            {isAdmin && (
              <Popconfirm
                title={t(`common.prompt`)}
                description={t(
                  'node-manager.cloudregion.Configuration.deleteSubConfigWarning'
                )}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => {
                  handleDelete(record.key);
                }}
              >
                <Button type="link" danger className="ml-[10px]">
                  {t('common.delete')}
                </Button>
              </Popconfirm>
            )}
          </>
        ),
      },
    ];

    const handleDelete = (id: number) => {
      setSubConfigLoading(true);
      deleteSubConfig(id)
        .then(() => {
          message.success(t('common.delSuccess'));
          loadSubConfigs(mainConfig?.key as string);
        })
        .catch(() => {
          setSubConfigLoading(false);
        });
    };

    const handleSubConfigTableChange = (pagination: any) => {
      setSubConfigPagination(pagination);
    };

    const getStatusInfo = (status: number) => {
      return (
        statusMap[status] || {
          tagColor: 'default',
          color: '#b2b5bd',
          text: t('node-manager.cloudregion.node.unknown'),
          engText: 'Unknown',
        }
      );
    };

    const getOSIcon = () => {
      const osValue = form?.operating_system;
      return (
        <Icon
          className="mr-[8px] center-align"
          type={osValue === 'linux' ? 'Linux' : 'Window-Windows'}
          style={{ transform: 'scale(1.3)', display: 'inline-block' }}
        />
      );
    };

    const getOSLabel = () => {
      const osValue = form?.operating_system;
      return nodeStateEnum?.os?.[osValue] || osValue;
    };

    return (
      <div>
        <OperateDrawer
          title={form?.name || '--'}
          subTitle={
            <>
              <Tag
                icon={<GlobalOutlined />}
                color="blue"
                className="text-[14px]"
              >
                {form?.ip || '--'}
              </Tag>
              {form?.operating_system && (
                <Tag color="green" icon={getOSIcon()} className="text-[14px]">
                  {getOSLabel()}
                </Tag>
              )}
            </>
          }
          headerExtra={
            <div
              style={{
                color: 'var(--color-text-3)',
                fontSize: '12px',
              }}
            >
              {t('node-manager.cloudregion.node.lastReportTime')}：
              {form.updated_at ? convertToLocalizedTime(form.updated_at) : '--'}
            </div>
          }
          open={visible}
          width={800}
          destroyOnClose
          onClose={handleCancel}
        >
          <div className="flex h-full">
            <div className="w-1/3 pr-4 border-r border-gray-200">
              <div className="flex items-center mb-2">
                <b className="mr-2">
                  {t('node-manager.cloudregion.node.hostedProgramList')}
                </b>
                <Badge
                  size="small"
                  count={collectors.length}
                  showZero
                  color="var(--color-fill-1)"
                  style={{
                    backgroundColor: 'var(--color-fill-2)',
                    color: 'var(--color-text-2)',
                    boxShadow: 'none',
                  }}
                />
              </div>
              <div className="space-y-2">
                {getSortedGroupedCollectors().map(([status, items]) => {
                  return (
                    <div key={status} className="text-[12px]">
                      <div className="space-y-2 mb-2">
                        {items.map((collector) => {
                          const collectorStatusInfo = getStatusInfo(
                            collector.status
                          );
                          return (
                            <div
                              key={collector.collector_id}
                              className={`p-3 rounded cursor-pointer transition-colors flex items-center justify-between border-l-4 ${
                                selectedCollector?.collector_id ===
                                collector.collector_id
                                  ? 'bg-[var(--color-bg-hover)] border-blue-200'
                                  : 'bg-[var(--color-bg-1)] border-gray-200 hover:bg-[var(--color-bg-hover)]'
                              }`}
                              style={{
                                border: '1px solid var(--color-border-1)',
                                borderLeft: `4px solid ${collectorStatusInfo.color}`,
                              }}
                              onClick={() => handleCollectorClick(collector)}
                            >
                              <div className="flex items-center flex-1">
                                <div className="mr-2">
                                  {collectorStatusInfo.icon}
                                </div>
                                <div className="flex-1">
                                  <div className="font-medium text-sm">
                                    {collector.collector_name}
                                  </div>
                                  <div
                                    className="text-xs mt-1"
                                    style={{ color: collectorStatusInfo.color }}
                                  >
                                    {collectorStatusInfo.text}
                                  </div>
                                </div>
                              </div>
                              <RightOutlined className="text-xs" />
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="w-2/3 pl-4 flex flex-col overflow-y-auto">
              {selectedCollector ? (
                <div className="space-y-4 flex flex-col h-full">
                  {/* 采集器名称 */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-sm text-[var(--color-text-2)]">
                      {selectedCollector.collector_name}
                    </span>
                  </div>
                  {/* 状态信息 */}
                  <div className="py-3 px-4 bg-[var(--color-fill-1)] rounded flex-shrink-0">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm">
                        {t('node-manager.cloudregion.node.runningStatus')}
                      </span>
                      <Tag
                        color={getStatusInfo(selectedCollector.status).tagColor}
                      >
                        {getStatusInfo(selectedCollector.status).text}
                      </Tag>
                    </div>
                    <div
                      className="text-xs"
                      style={{
                        color: getStatusInfo(selectedCollector.status).color,
                      }}
                    >
                      <span className="flex items-center text-xs">
                        <span
                          style={{
                            color: getStatusInfo(selectedCollector.status)
                              .color,
                            fontSize: '16px',
                            marginRight: '4px',
                          }}
                        >
                          {React.cloneElement(
                            getStatusInfo(selectedCollector.status).icon.props
                              .children,
                            {
                              style: {
                                ...getStatusInfo(selectedCollector.status).icon
                                  .props.children.props.style,
                                fontSize: '14px',
                              },
                            }
                          )}
                        </span>
                        {selectedCollector.message || '--'}
                      </span>
                      <p className="mt-[4px]">
                        {selectedCollector.verbose_message || ''}
                      </p>
                    </div>
                  </div>

                  <Spin spinning={mainConfigLoading}>
                    {/* 主配置 */}
                    <div className="py-3 px-4 mb-4 bg-[var(--color-fill-1)] rounded flex-shrink-0">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold">
                          {t(
                            'node-manager.cloudregion.Configuration.mainConfiguration'
                          )}
                        </span>
                        <PermissionWrapper
                          requiredPermissions={['EditMainConfiguration']}
                        >
                          <Button
                            type="primary"
                            size="small"
                            icon={<EditOutlined />}
                            disabled={!mainConfig?.key}
                            onClick={handleMainConfigEdit}
                          >
                            {t('common.edit')}
                          </Button>
                        </PermissionWrapper>
                      </div>
                    </div>
                    {/* 子配置 */}
                    {mainConfig && (
                      <div className="flex-1 flex flex-col">
                        <div className="bg-[var(--color-fill-2)] rounded-t flex items-center justify-between p-[10px] flex-shrink-0">
                          <span className="text-sm font-bold">
                            {t(
                              'node-manager.cloudregion.Configuration.subconfiguration'
                            )}
                          </span>
                          <span className="text-xs text-[var(--color-text-3)]">
                            {subConfigPagination.total || 0}
                            {t('common.items')}
                          </span>
                        </div>
                        <div className="flex-1">
                          <CustomTable
                            scroll={{
                              y: !subConfigs?.length
                                ? 'auto'
                                : 'calc(100vh - 474px)',
                              x: 'max-content',
                            }}
                            columns={subConfigColumns}
                            dataSource={subConfigs}
                            loading={subConfigLoading}
                            rowKey="id"
                            pagination={subConfigPagination}
                            size="small"
                            onChange={handleSubConfigTableChange}
                          />
                        </div>
                      </div>
                    )}
                  </Spin>
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </div>
          </div>
        </OperateDrawer>
        {/* 配置编辑弹窗 */}
        <ConfigModal
          ref={configModalRef}
          config={{ collectors: [] }}
          onSuccess={handleConfigModalSuccess}
        />
      </div>
    );
  }
);

CollectorDetailDrawer.displayName = 'CollectorDetailDrawer';
export default CollectorDetailDrawer;
