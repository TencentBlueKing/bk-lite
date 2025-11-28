'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useRef,
} from 'react';
import { Tag, Button, Badge } from 'antd';
import {
  RightOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ToolOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import CustomTable from '@/components/custom-table';
import EditConfig from './updateConfig';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useIntegrationApi from '@/app/monitor/api/integration';
import { ModalRef } from '@/app/monitor/types';
import { ModalSuccess } from '@/app/node-manager/types';
import {
  PluginItem,
  ConfigItem,
  ShowModalParams,
  TemplateDrawerRef,
} from '@/app/monitor/types/integration';

const TemplateConfigDrawer = forwardRef<TemplateDrawerRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { convertToLocalizedTime } = useLocalizedTime();
    const { getInstanceChildConfig } = useIntegrationApi();
    const configRef = useRef<ModalRef>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [loading, setLoading] = useState<boolean>(false);
    const [selectedPlugin, setSelectedPlugin] = useState<PluginItem | null>(
      null
    );
    const [plugins, setPlugins] = useState<PluginItem[]>([]);
    const [configList, setConfigList] = useState<ConfigItem[]>([]);
    const [instanceName, setInstanceName] = useState<string>('');
    const [objName, setObjName] = useState<string>('');
    const [showTemplateList, setShowTemplateList] = useState<boolean>(true);

    useImperativeHandle(ref, () => ({
      showModal: async ({
        instanceName,
        instanceId,
        instanceType,
        selectedConfigId,
        objName,
        plugins: externalPlugins,
        showTemplateList: shouldShowList = true,
      }: ShowModalParams) => {
        setVisible(true);
        setInstanceName(instanceName);
        setObjName(objName || '');
        setShowTemplateList(shouldShowList);
        // 设置外层传入的plugins
        setPlugins(externalPlugins || []);
        // 立即设置选中的插件，让用户打开弹窗时就能看到内容
        let selectedTemp: any;
        if (externalPlugins && externalPlugins.length > 0) {
          if (shouldShowList) {
            // 显示列表模式：默认选中第一个插件（按状态排序后）
            const sortedPlugins = [...externalPlugins].sort(
              (a: any, b: any) => {
                // 手动接入排最后
                if (a.collect_mode === 'manual' && b.collect_mode === 'auto')
                  return 1;
                if (a.collect_mode === 'auto' && b.collect_mode === 'manual')
                  return -1;
                // 正常状态排前面
                if (
                  (a.status === 'normal' || a.status === 'online') &&
                  b.status !== 'normal' &&
                  b.status !== 'online'
                )
                  return -1;
                if (
                  a.status !== 'normal' &&
                  a.status !== 'online' &&
                  (b.status === 'normal' || b.status === 'online')
                )
                  return 1;
                return 0;
              }
            );
            selectedTemp = sortedPlugins[0];
          } else {
            // 隐藏列表模式：选中指定的插件
            if (selectedConfigId) {
              selectedTemp = externalPlugins.find(
                (t: any) => t.name === selectedConfigId
              );
            } else {
              // 如果没有指定config_id，说明是手动模板
              selectedTemp = externalPlugins.find(
                (t: any) => t.collect_mode === 'manual'
              );
            }
          }
          setSelectedPlugin(selectedTemp);
          // 如果选中的是手动模板，不需要调用接口
          if (selectedTemp && selectedTemp.collect_mode === 'manual') {
            setConfigList([]);
            return;
          }
        }
        setLoading(true);
        try {
          const templateData = await getInstanceChildConfig({
            instance_id: instanceId,
            instance_type: instanceType,
            collect_type: selectedTemp?.collect_type,
            collector: selectedTemp?.collector,
          });
          const dataWithId = (templateData || []).map(
            (item: any, index: number) => ({
              ...item,
              id: index,
            })
          );
          setConfigList(dataWithId);
        } finally {
          setLoading(false);
        }
      },
    }));

    const handleCancel = () => {
      setVisible(false);
      setPlugins([]);
      setConfigList([]);
      setSelectedPlugin(null);
      setInstanceName('');
      setObjName('');
      setShowTemplateList(true);
    };

    const handlePluginClick = (plugin: PluginItem) => {
      if (
        selectedPlugin?.name === plugin.name &&
        selectedPlugin?.collect_type === plugin.collect_type
      ) {
        return;
      }
      setSelectedPlugin(plugin);
      setConfigList([]);
    };

    const getCollectType = (row: ConfigItem) => {
      if (row.collect_type === 'host') {
        return `${row.collect_type}(${row.config_type})`;
      }
      return row.collect_type || '--';
    };

    const openConfigModal = (row: ConfigItem) => {
      configRef.current?.showModal({
        title: t('monitor.integrations.updateConfigration'),
        type: 'edit',
        form: {
          ...row,
          objName: objName,
        },
      });
    };

    const getStatusInfo = (status: string) => {
      if (status === 'normal') {
        return {
          color: '#52c41a',
          tagColor: 'success',
          text: t('monitor.integrations.normal'),
          icon: (
            <div
              className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: 'rgba(82, 196, 26, 0.1)' }}
            >
              <CheckCircleOutlined
                style={{
                  color: '#52c41a',
                  fontWeight: 'bold',
                  fontSize: '12px',
                }}
              />
            </div>
          ),
        };
      } else {
        return {
          color: '#ff4d4f',
          tagColor: 'error',
          text: t('monitor.integrations.unavailable'),
          icon: (
            <div
              className="w-6 h-6 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: 'rgba(255, 77, 79, 0.1)' }}
            >
              <CloseCircleOutlined
                style={{
                  color: '#ff4d4f',
                  fontWeight: 'bold',
                  fontSize: '12px',
                }}
              />
            </div>
          ),
        };
      }
    };

    const isManualAccess = (plugin: PluginItem) => {
      return plugin.collect_mode === 'manual';
    };

    const getGroupedPlugins = () => {
      const grouped = plugins.reduce((groups, plugin) => {
        const status = plugin.status;
        if (!groups[status]) {
          groups[status] = [];
        }
        groups[status].push(plugin);
        return groups;
      }, {} as Record<string, PluginItem[]>);

      // Sort groups: normal/online first, then unavailable
      return Object.entries(grouped).sort(([statusA], [statusB]) => {
        if (statusA === 'normal' || statusA === 'online') return -1;
        if (statusB === 'normal' || statusB === 'online') return 1;
        return 0;
      });
    };

    const getConfigColumns = () => {
      return [
        {
          title: t('monitor.integrations.collectionMethod'),
          dataIndex: 'collect_type',
          key: 'collect_type',
          width: 150,
          render: (_: any, record: ConfigItem) => <>{getCollectType(record)}</>,
        },
        {
          title: t('monitor.integrations.collectionPeriod'),
          dataIndex: 'interval',
          key: 'interval',
          width: 150,
          render: (_: any, record: ConfigItem) => {
            const interval =
              record?.config_content?.child?.content?.config?.interval;
            return interval ? <Tag color="blue">{interval}</Tag> : <>--</>;
          },
        },
        {
          title: t('common.action'),
          key: 'action',
          dataIndex: 'action',
          fixed: 'right' as const,
          width: 60,
          render: (_: any, record: ConfigItem) => (
            <>
              <Button
                type="link"
                disabled={!record.config_ids?.length}
                onClick={() => openConfigModal(record)}
              >
                {t('common.edit')}
              </Button>
            </>
          ),
        },
      ];
    };

    return (
      <div>
        <EditConfig ref={configRef} onSuccess={onSuccess} />
        <OperateDrawer
          title={instanceName || '--'}
          open={visible}
          width={800}
          destroyOnClose
          onClose={handleCancel}
        >
          <div className="flex h-full">
            {/* 左侧：模板列表 */}
            {showTemplateList && plugins.length > 0 && (
              <div className="w-1/3 pr-4 border-r border-[var(--color-border-1)]">
                <div className="flex items-center mb-2">
                  <b className="mr-2">
                    {t('monitor.integrations.templateList')}
                  </b>
                  <Badge
                    size="small"
                    count={plugins.length}
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
                  {getGroupedPlugins().map(([status, items]) => {
                    return (
                      <div key={status} className="text-[12px]">
                        <div className="space-y-2 mb-2">
                          {items.map((plugin, idx) => {
                            const pluginStatusInfo = getStatusInfo(
                              plugin.status
                            );
                            const isSelected =
                              selectedPlugin?.name === plugin.name &&
                              selectedPlugin?.collect_type ===
                                plugin.collect_type;
                            return (
                              <div
                                key={`${plugin.name}-${idx}`}
                                className={`p-3 rounded cursor-pointer transition-colors flex items-center justify-between border-l-4 ${
                                  isSelected
                                    ? 'bg-[var(--color-bg-hover)] border-blue-200'
                                    : 'bg-[var(--color-bg-1)] border-gray-200 hover:bg-[var(--color-bg-hover)]'
                                }`}
                                style={{
                                  border: '1px solid var(--color-border-1)',
                                  borderLeft: `4px solid ${pluginStatusInfo.color}`,
                                }}
                                onClick={() => handlePluginClick(plugin)}
                              >
                                <div className="flex items-center flex-1">
                                  <div className="mr-2">
                                    {pluginStatusInfo.icon}
                                  </div>
                                  <div className="flex-1">
                                    <div className="font-medium text-sm mb-1">
                                      {plugin.collector
                                        ? `${plugin.name || '--'}（${
                                          plugin.collector
                                        }）`
                                        : plugin.name || '--'}
                                    </div>
                                    <Tag
                                      color="blue"
                                      icon={
                                        isManualAccess(plugin) ? (
                                          <ToolOutlined />
                                        ) : (
                                          <ApiOutlined />
                                        )
                                      }
                                      className="text-xs"
                                    >
                                      {isManualAccess(plugin)
                                        ? t('monitor.integrations.manualAccess')
                                        : t('monitor.integrations.autoAccess')}
                                    </Tag>
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
            )}

            {/* 右侧：模板详情 */}
            <div
              className={
                showTemplateList && plugins.length > 0 ? 'w-2/3 pl-4' : 'w-full'
              }
            >
              {selectedPlugin && (
                <div className="space-y-4">
                  {/* 标题和标签 */}
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-[var(--color-text-2)]">
                      {selectedPlugin.collector
                        ? `${selectedPlugin.name || '--'}（${
                          selectedPlugin.collector
                        }）`
                        : selectedPlugin.name || '--'}
                    </span>
                    <Tag
                      color="blue"
                      icon={
                        isManualAccess(selectedPlugin) ? (
                          <ToolOutlined />
                        ) : (
                          <ApiOutlined />
                        )
                      }
                    >
                      {isManualAccess(selectedPlugin)
                        ? t('monitor.integrations.manualAccess')
                        : t('monitor.integrations.autoAccess')}
                    </Tag>
                  </div>

                  {/* 上报状态 */}
                  <div className="py-3 px-4 bg-[var(--color-fill-1)] rounded">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm">
                        {t('monitor.integrations.reportingStatus')}
                      </span>
                      <Tag
                        color={getStatusInfo(selectedPlugin.status).tagColor}
                      >
                        {getStatusInfo(selectedPlugin.status).text}
                      </Tag>
                    </div>
                    <div className="text-xs text-[var(--color-text-3)]">
                      {t('monitor.integrations.lastReportTime')}：
                      {selectedPlugin.time
                        ? convertToLocalizedTime(selectedPlugin.time)
                        : '--'}
                    </div>
                  </div>

                  {/* 配置列表 */}
                  <div className="bg-[var(--color-fill-2)] rounded">
                    {isManualAccess(selectedPlugin) ? (
                      <div className="flex flex-col items-center justify-center py-8 px-4">
                        <span className="text-4xl mb-3 text-[var(--color-text-3)]">
                          {isManualAccess(selectedPlugin) ? (
                            <ToolOutlined />
                          ) : (
                            <ApiOutlined />
                          )}
                        </span>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.integrations.manualAccessTip')}
                        </span>
                      </div>
                    ) : (
                      <div>
                        <div className="flex items-center justify-between p-[10px]">
                          <span className="text-sm font-bold">
                            {t('monitor.integrations.configurationList')}
                          </span>
                          <span className="text-xs text-[var(--color-text-3)]">
                            {configList.length}
                            {t('common.items')}
                          </span>
                        </div>
                        <CustomTable
                          scroll={{ x: 'max-content' }}
                          rowKey="id"
                          dataSource={configList}
                          columns={getConfigColumns()}
                          pagination={false}
                          loading={loading}
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </OperateDrawer>
      </div>
    );
  }
);

TemplateConfigDrawer.displayName = 'TemplateConfigDrawer';
export default TemplateConfigDrawer;
