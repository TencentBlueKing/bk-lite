import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Form, Button, message, Spin, Empty, Dropdown, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { v4 as uuidv4 } from 'uuid';
import { useSearchParams, useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/monitor/api/integration';
import { TableDataItem } from '@/app/monitor/types';
import {
  IntegrationAccessProps,
  IntegrationMonitoredObject,
} from '@/app/monitor/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import { cloneDeep } from 'lodash';
import { usePluginFromJson } from '@/app/monitor/hooks/integration/usePluginFromJson';
import { useConfigRenderer } from '@/app/monitor/hooks/integration/useConfigRenderer';
import BatchEditModal from './batchEditModal';
const { confirm } = Modal;

const AutomaticConfiguration: React.FC<IntegrationAccessProps> = ({}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getMonitorNodeList, updateNodeChildConfig } = useIntegrationApi();
  const router = useRouter();
  const { renderTableColumn } = useConfigRenderer();
  const jsonConfig = usePluginFromJson();
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const pluginId = searchParams.get('plugin_id') || '';
  const objectId = searchParams.get('id') || '';
  const [dataSource, setDataSource] = useState<IntegrationMonitoredObject[]>(
    []
  );
  const [nodeList, setNodeList] = useState<TableDataItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [nodesLoading, setNodesLoading] = useState<boolean>(false);
  const [initTableItems, setInitTableItems] =
    useState<IntegrationMonitoredObject>({});
  const [isTableInitialized, setIsTableInitialized] = useState<boolean>(false);
  const [currentConfig, setCurrentConfig] = useState<any>(null);
  const [configLoading, setConfigLoading] = useState<boolean>(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const batchEditModalRef = useRef<any>(null);

  const onTableDataChange = (data: IntegrationMonitoredObject[]) => {
    setDataSource(data);
  };

  useEffect(() => {
    if (pluginId) {
      setConfigLoading(true);
      jsonConfig
        .getPluginConfig(pluginId)
        .then((data) => {
          setCurrentConfig(data);
        })
        .finally(() => {
          setConfigLoading(false);
        });
    }
  }, [pluginId, jsonConfig.getPluginConfig]);

  // 获取基础配置（不依赖 dataSource）
  const baseConfig = useMemo(() => {
    if (configLoading || !currentConfig) {
      return null;
    }
    return currentConfig;
  }, [configLoading, currentConfig]);

  // 获取表单配置
  const formConfig = useMemo(() => {
    if (!baseConfig || !pluginId) {
      return { formItems: null, defaultForm: {}, initTableItems: {} };
    }
    const cfg = jsonConfig.buildPluginUI(pluginId, {
      mode: 'auto',
      dataSource: [],
      onTableDataChange,
      form,
      externalOptions: {
        node_ids_option: nodeList,
      },
    });
    return {
      formItems: cfg.formItems,
      defaultForm: cfg.defaultForm,
      initTableItems: cfg.initTableItems,
    };
  }, [baseConfig, pluginId, form, nodeList, jsonConfig.buildPluginUI]);

  // 获取动态配置（依赖 dataSource）
  const configsInfo = useMemo(() => {
    if (!baseConfig || !pluginId) {
      return {
        collect_type: '',
        config_type: [],
        collector: '',
        instance_type: '',
        object_name: '',
        getParams: () => ({}),
      };
    }
    return jsonConfig.buildPluginUI(pluginId, {
      mode: 'auto',
      dataSource,
      onTableDataChange,
      form,
      externalOptions: {
        node_ids_option: nodeList,
      },
    });
  }, [
    baseConfig,
    pluginId,
    dataSource,
    form,
    nodeList,
    jsonConfig.buildPluginUI,
  ]);

  const collectType = useMemo(() => {
    return configsInfo?.collect_type || '';
  }, [configsInfo]);

  // 动态生成 columns
  const columns = useMemo(() => {
    if (configLoading || !currentConfig || !currentConfig.table_columns) {
      return [];
    }
    const dataColumns = currentConfig.table_columns.map((columnConfig: any) =>
      renderTableColumn(columnConfig, dataSource, onTableDataChange, {
        node_ids_option: nodeList,
      })
    );

    // 检查是否有 enable_row_filter 为 true 的列
    const hasRowFilter = currentConfig.table_columns.some(
      (col: any) => col.enable_row_filter === true
    );

    const actionColumn = {
      title: t('common.action'),
      key: 'action',
      dataIndex: 'action',
      width: 160,
      fixed: 'right' as const,
      render: (_: any, record: IntegrationMonitoredObject, index: number) => (
        <>
          <Button
            type="link"
            className="mr-[10px]"
            onClick={() => handleAdd(record.key as string)}
          >
            {t('common.add')}
          </Button>
          {!['host', 'trap'].includes(collectType) && !hasRowFilter && (
            <Button
              type="link"
              className="mr-[10px]"
              onClick={() => handleCopy(record)}
            >
              {t('common.copy')}
            </Button>
          )}
          {!!index && (
            <Button
              type="link"
              onClick={() => handleDelete(record.key as string)}
            >
              {t('common.delete')}
            </Button>
          )}
        </>
      ),
    };
    return [...dataColumns, actionColumn];
  }, [
    configLoading,
    currentConfig,
    dataSource,
    nodeList,
    renderTableColumn,
    t,
    collectType,
  ]);

  const formItems = useMemo(() => {
    return formConfig?.formItems || null;
  }, [formConfig]);

  useEffect(() => {
    if (isLoading) return;
    getNodeList();
    initData();
  }, [isLoading]);

  useEffect(() => {
    if (configLoading || !formConfig.initTableItems || isTableInitialized) {
      return;
    }
    const initItems = {
      ...formConfig.initTableItems,
      node_ids: null,
      instance_name: null,
      group_ids: groupId,
      key: uuidv4(),
    };
    setInitTableItems(initItems);
    setDataSource([initItems]);
    setIsTableInitialized(true);
  }, [configLoading, formConfig.initTableItems, groupId, isTableInitialized]);

  const handleAdd = (key: string) => {
    const index = dataSource.findIndex((item) => item.key === key);
    const newData = {
      ...initTableItems,
      key: uuidv4(),
    };
    const updatedData = [...dataSource];
    updatedData.splice(index + 1, 0, newData);
    setDataSource(updatedData);
  };

  const handleCopy = (row: IntegrationMonitoredObject) => {
    const index = dataSource.findIndex((item) => item.key === row.key);
    const newData: IntegrationMonitoredObject = { ...row, key: uuidv4() };
    const updatedData = [...dataSource];
    updatedData.splice(index + 1, 0, newData);
    setDataSource(updatedData);
  };

  const handleDelete = (key: string) => {
    const updatedData = dataSource.filter((item) => item.key !== key);
    setDataSource(updatedData);
  };

  const handleBatchDelete = () => {
    confirm({
      title: t('common.prompt'),
      content: t('monitor.integrations.batchDeleteConfirm'),
      centered: true,
      onOk() {
        const updatedData = dataSource.filter(
          (item) => !selectedRowKeys.includes(item.key as string)
        );
        // 如果删除后为空，保留一条空行
        if (updatedData.length === 0) {
          const newData = {
            ...initTableItems,
            key: uuidv4(),
          };
          setDataSource([newData]);
        } else {
          setDataSource(updatedData);
        }
        setSelectedRowKeys([]);
      },
    });
  };

  const handleBatchEdit = () => {
    const selectedRows = dataSource.filter((item) =>
      selectedRowKeys.includes(item.key as string)
    );
    batchEditModalRef.current?.showModal({
      columns: currentConfig?.table_columns || [],
      selectedRows,
      nodeList,
    });
  };

  const handleBatchEditSuccess = (editedFields: any) => {
    const updatedData = dataSource.map((item) => {
      if (selectedRowKeys.includes(item.key as string)) {
        return {
          ...item,
          ...editedFields,
        };
      }
      return item;
    });
    setDataSource(updatedData);
  };

  const batchMenuItems: MenuProps['items'] = [
    {
      key: 'batchEdit',
      label: t('common.batchEdit'),
    },
    {
      key: 'batchDelete',
      label: t('common.batchDelete'),
      disabled: selectedRowKeys.length === 1 && dataSource.length === 1,
    },
  ];

  const handleBatchMenuClick: MenuProps['onClick'] = (e) => {
    if (e.key === 'batchEdit') {
      handleBatchEdit();
    } else if (e.key === 'batchDelete') {
      handleBatchDelete();
    }
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
  };

  const initData = () => {
    form.setFieldsValue({
      ...(formConfig?.defaultForm || {}),
    });
  };

  const getNodeList = async () => {
    setNodesLoading(true);
    try {
      const data = await getMonitorNodeList({
        cloud_region_id: 0,
        page: 1,
        page_size: -1,
        is_active: true,
      });
      const formattedNodes = (data.nodes || []).map((node: any) => ({
        ...node,
        label: `${node.name} (${node.ip})`,
        value: node.id,
      }));
      setNodeList(formattedNodes);
    } finally {
      setNodesLoading(false);
    }
  };

  const handleSave = () => {
    form.validateFields().then((values) => {
      const row = cloneDeep(values);
      delete row.nodes;
      const params =
        configsInfo?.getParams?.(row, {
          dataSource,
          nodeList,
          objectId,
        }) || {};
      params.monitor_object_id = Number(objectId);
      addNodesConfig(params);
    });
  };

  const addNodesConfig = async (params = {}) => {
    try {
      setConfirmLoading(true);
      await updateNodeChildConfig(params);
      message.success(t('common.addSuccess'));
      const searchParams = new URLSearchParams({
        objId: objectId,
      });
      const targetUrl = `/monitor/integration/list?${searchParams.toString()}`;
      router.push(targetUrl);
    } finally {
      setConfirmLoading(false);
    }
  };

  // 判断是否显示空状态
  const showEmpty =
    !configLoading && (!currentConfig || !currentConfig.table_columns);

  return (
    <Spin spinning={configLoading || nodesLoading}>
      <div className="px-[10px]">
        {showEmpty ? (
          <div
            className="flex items-center justify-center"
            style={{ minHeight: '400px' }}
          >
            <Empty description={t('monitor.integrations.noConfigData')} />
          </div>
        ) : (
          <Form form={form} name="basic" layout="vertical">
            <b className="text-[14px] flex mb-[10px] ml-[-10px]">
              {t('monitor.integrations.configuration')}
            </b>
            {formItems}
            <b className="text-[14px] flex mb-[10px] ml-[-10px]">
              {t('monitor.integrations.basicInformation')}
            </b>
            <div className="flex items-center justify-between mb-[10px]">
              <span className="text-[14px]">
                {t('monitor.integrations.MonitoredObject')}
                <span
                  className="text-[#ff4d4f] align-middle text-[14px] ml-[4px]"
                  style={{ fontFamily: 'SimSun, sans-serif' }}
                >
                  *
                </span>
              </span>
              <Dropdown
                menu={{
                  items: batchMenuItems,
                  onClick: handleBatchMenuClick,
                }}
                disabled={!selectedRowKeys.length}
              >
                <Button>
                  {t('monitor.integrations.batchOperation')}
                  <DownOutlined className="ml-[4px]" />
                </Button>
              </Dropdown>
            </div>
            <Form.Item
              name="nodes"
              rules={[
                {
                  required: true,
                  validator: async () => {
                    if (!dataSource.length) {
                      return Promise.reject(new Error(t('common.required')));
                    }
                    if (
                      dataSource.some((item) =>
                        Object.values(item).some((value) => !value)
                      )
                    ) {
                      return Promise.reject(new Error(t('common.required')));
                    }
                    return Promise.resolve();
                  },
                },
              ]}
            >
              <CustomTable
                scroll={{ y: 'calc(100vh - 490px)', x: 'calc(100vw - 320px)' }}
                dataSource={dataSource}
                columns={columns}
                rowKey="key"
                pagination={false}
                rowSelection={rowSelection}
              />
            </Form.Item>
            <Form.Item>
              <Permission requiredPermissions={['Add']}>
                <Button
                  type="primary"
                  loading={confirmLoading}
                  onClick={handleSave}
                >
                  {t('common.confirm')}
                </Button>
              </Permission>
            </Form.Item>
          </Form>
        )}
      </div>
      <BatchEditModal
        ref={batchEditModalRef}
        onSuccess={handleBatchEditSuccess}
      />
    </Spin>
  );
};

export default AutomaticConfiguration;
