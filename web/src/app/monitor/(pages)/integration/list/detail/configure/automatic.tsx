import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Form, Button, message, Spin, Empty, Dropdown, Modal, Tag } from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined, ThunderboltOutlined, UploadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { v4 as uuidv4 } from 'uuid';
import { useSearchParams, useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/monitor/api/integration';
import { TableDataItem } from '@/app/monitor/types';
import {
  IntegrationAccessProps,
  IntegrationMonitoredObject
} from '@/app/monitor/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import { cloneDeep } from 'lodash';
import { usePluginFromJson } from '@/app/monitor/hooks/integration/usePluginFromJson';
import { useConfigRenderer } from '@/app/monitor/hooks/integration/useConfigRenderer';
import BatchEditModal from './batchEditModal';
import ExcelImportModal from './excelImportModal';
const { confirm } = Modal;

interface CollectDetectState {
  status: 'pending' | 'running' | 'success' | 'failed';
  result?: Record<string, any>;
  error_message?: string;
}

const AutomaticConfiguration: React.FC<IntegrationAccessProps> = ({}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const {
    createCollectDetectTask,
    getCollectDetectTask,
    getMonitorNodeList,
    updateNodeChildConfig
  } = useIntegrationApi();
  const router = useRouter();
  const { renderTableColumn } = useConfigRenderer();
  const jsonConfig = usePluginFromJson();
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const pluginId = searchParams.get('plugin_id') || '';
  const objectId = searchParams.get('id') || '';
  const pluginDisplayName = searchParams.get('plugin_display_name') || '';
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
  const [collectDetectTasks, setCollectDetectTasks] = useState<
    Record<string, CollectDetectState>
  >({});
  const collectDetectTimersRef = useRef<
    Record<string, ReturnType<typeof setTimeout>>
  >({});
  const batchEditModalRef = useRef<any>(null);
  const excelImportModalRef = useRef<any>(null);

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
        node_ids_option: nodeList
      }
    });
    return {
      formItems: cfg.formItems,
      defaultForm: cfg.defaultForm,
      initTableItems: cfg.initTableItems
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
        getParams: () => ({})
      };
    }
    return jsonConfig.buildPluginUI(pluginId, {
      mode: 'auto',
      dataSource,
      onTableDataChange,
      form,
      externalOptions: {
        node_ids_option: nodeList
      }
    });
  }, [
    baseConfig,
    pluginId,
    dataSource,
    form,
    nodeList,
    jsonConfig.buildPluginUI
  ]);

  const collectType = useMemo(() => {
    return configsInfo?.collect_type || '';
  }, [configsInfo]);

  const supportCollectDetect = !!currentConfig?.support_collect_detect;

  useEffect(() => {
    return () => {
      Object.values(collectDetectTimersRef.current).forEach(clearTimeout);
    };
  }, []);

  const getRowNodeId = (record: IntegrationMonitoredObject) => {
    if (Array.isArray(record.node_ids)) {
      return record.node_ids[0];
    }
    return record.node_ids;
  };

  const buildDetectInstance = (record: IntegrationMonitoredObject) => {
    const formValues = cloneDeep(form.getFieldsValue());
    delete formValues.nodes;
    const rowValues = Object.keys(record)
      .filter((key) => key !== 'key' && !key.endsWith('_error'))
      .reduce((acc, key) => {
        acc[key] = record[key];
        return acc;
      }, {} as Record<string, any>);
    return {
      ...formValues,
      ...rowValues,
      instance_type: configsInfo?.instance_type
    };
  };

  const formatCollectDetectMessage = (task: CollectDetectState) => {
    const result = task.result || {};
    const parts = [
      `状态：${task.status}`,
      `退出码：${result.exit_code ?? '--'}`,
      result.stdout ? `stdout:\n${result.stdout}` : '',
      result.stderr || task.error_message
        ? `stderr:\n${result.stderr || task.error_message}`
        : ''
    ].filter(Boolean);
    return parts.join('\n\n');
  };

  const showCollectDetectResult = (task: CollectDetectState) => {
    Modal.info({
      title:
        task.status === 'success'
          ? t('monitor.integrations.collectDetectSuccess')
          : t('monitor.integrations.collectDetectFailed'),
      width: 720,
      content: (
        <pre className="mt-[12px] max-h-[420px] overflow-auto whitespace-pre-wrap rounded bg-[#f5f7fa] p-[12px] text-[12px] leading-[18px]">
          {formatCollectDetectMessage(task)}
        </pre>
      )
    });
  };

  const updateCollectDetectState = (
    rowKey: string,
    task: CollectDetectState
  ) => {
    setCollectDetectTasks((prev) => ({
      ...prev,
      [rowKey]: task
    }));
  };

  const pollCollectDetectTask = async (
    rowKey: string,
    taskId: React.Key,
    retryCount = 0
  ) => {
    try {
      const task = (await getCollectDetectTask(taskId)) as CollectDetectState;
      updateCollectDetectState(rowKey, task);
      if (['pending', 'running'].includes(task.status) && retryCount < 60) {
        collectDetectTimersRef.current[rowKey] = setTimeout(() => {
          pollCollectDetectTask(rowKey, taskId, retryCount + 1);
        }, 2000);
        return;
      }
      showCollectDetectResult(task);
    } catch (error: any) {
      updateCollectDetectState(rowKey, {
        status: 'failed',
        error_message: error?.message || t('common.operationFailed')
      });
    }
  };

  const handleCollectDetect = async (record: IntegrationMonitoredObject) => {
    const rowKey = record.key as string;
    const nodeId = getRowNodeId(record);
    if (!nodeId) {
      message.warning(t('monitor.integrations.collectDetectNodeRequired'));
      return;
    }
    updateCollectDetectState(rowKey, { status: 'running' });
    try {
      const data = (await createCollectDetectTask({
        monitor_plugin_id: Number(pluginId),
        monitor_object_id: Number(objectId),
        node_id: nodeId,
        instance_key: record.instance_id || record.instance_name || rowKey,
        instance: buildDetectInstance(record)
      })) as { task_id: React.Key };
      pollCollectDetectTask(rowKey, data.task_id);
    } catch (error: any) {
      updateCollectDetectState(rowKey, {
        status: 'failed',
        error_message: error?.message || t('common.operationFailed')
      });
    }
  };

  const renderCollectDetectStatus = (record: IntegrationMonitoredObject) => {
    const task = collectDetectTasks[record.key as string];
    if (!task) {
      return <Tag>{t('monitor.integrations.collectDetectUntested')}</Tag>;
    }
    if (['pending', 'running'].includes(task.status)) {
      return <Tag color="processing">{t('monitor.integrations.collectDetectRunning')}</Tag>;
    }
    return task.status === 'success' ? (
      <Tag color="success">{t('monitor.integrations.collectDetectSuccess')}</Tag>
    ) : (
      <Tag color="error">{t('monitor.integrations.collectDetectFailed')}</Tag>
    );
  };

  // 动态生成 columns
  const columns = useMemo(() => {
    if (configLoading || !currentConfig || !currentConfig.table_columns) {
      return [];
    }
    const dataColumns = currentConfig.table_columns.map((columnConfig: any) =>
      renderTableColumn(columnConfig, dataSource, onTableDataChange, {
        node_ids_option: nodeList
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
      width: supportCollectDetect ? 240 : 160,
      fixed: 'right' as const,
      render: (_: any, record: IntegrationMonitoredObject) => (
        <>
          {supportCollectDetect && (
            <Button
              type="link"
              icon={<ThunderboltOutlined />}
              loading={['pending', 'running'].includes(
                collectDetectTasks[record.key as string]?.status
              )}
              className="mr-[10px]"
              onClick={() => handleCollectDetect(record)}
            >
              {t('monitor.integrations.collectDetect')}
            </Button>
          )}
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
          {dataSource.length > 1 && (
            <Button
              type="link"
              onClick={() => handleDelete(record.key as string)}
            >
              {t('common.delete')}
            </Button>
          )}
        </>
      )
    };
    const collectDetectStatusColumn = supportCollectDetect
      ? [
        {
          title: t('monitor.integrations.collectDetectStatus'),
          key: 'collect_detect_status',
          dataIndex: 'collect_detect_status',
          width: 140,
          render: (_: any, record: IntegrationMonitoredObject) =>
            renderCollectDetectStatus(record)
        }
      ]
      : [];
    return [...dataColumns, ...collectDetectStatusColumn, actionColumn];
  }, [
    configLoading,
    currentConfig,
    dataSource,
    nodeList,
    renderTableColumn,
    t,
    collectType,
    supportCollectDetect,
    collectDetectTasks
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
    if (
      !configLoading &&
      Object.keys(formConfig.initTableItems).length &&
      !isTableInitialized
    ) {
      const initItems = {
        ...formConfig.initTableItems,
        group_ids: formConfig.initTableItems.group_ids || groupId,
        key: uuidv4()
      };
      setInitTableItems(initItems);
      setDataSource([initItems]);
      setIsTableInitialized(true); // 避免无限初始化
    }
  }, [configLoading, formConfig.initTableItems, groupId]);

  const handleAdd = (key: string) => {
    const index = dataSource.findIndex((item) => item.key === key);
    const newData = {
      ...initTableItems,
      key: uuidv4()
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
    // 同步清理已删除行的选中状态
    setSelectedRowKeys((prev) => prev.filter((k) => k !== key));
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
            key: uuidv4()
          };
          setDataSource([newData]);
        } else {
          setDataSource(updatedData);
        }
        setSelectedRowKeys([]);
      }
    });
  };

  const handleBatchEdit = () => {
    const selectedRows = dataSource.filter((item) =>
      selectedRowKeys.includes(item.key as string)
    );
    batchEditModalRef.current?.showModal({
      columns: currentConfig?.table_columns || [],
      selectedRows,
      nodeList
    });
  };

  const handleBatchEditSuccess = (editedFields: any) => {
    const updatedData = dataSource.map((item) => {
      if (selectedRowKeys.includes(item.key as string)) {
        return {
          ...item,
          ...editedFields
        };
      }
      return item;
    });
    setDataSource(updatedData);
  };

  const handleImport = () => {
    excelImportModalRef.current?.showModal({
      title: t('monitor.integrations.importData'),
      columns: currentConfig?.table_columns || [],
      nodeList,
      pluginName: pluginDisplayName
    });
  };

  const handleImportSuccess = (importedData: any[]) => {
    const newRows = importedData.map((row) => ({
      ...row,
      key: uuidv4(),
      group_ids: row.group_ids || groupId
    }));
    setDataSource([...dataSource, ...newRows]);
  };

  const batchMenuItems: MenuProps['items'] = [
    {
      key: 'batchEdit',
      label: t('common.batchEdit')
    },
    {
      key: 'batchDelete',
      label: t('common.batchDelete'),
      disabled: dataSource.length === 1
    }
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
    }
  };

  const initData = () => {
    form.setFieldsValue({
      ...(formConfig?.defaultForm || {})
    });
  };

  const getNodeList = async () => {
    setNodesLoading(true);
    try {
      const data = await getMonitorNodeList({
        monitor_plugin_id: Number(pluginId),
        cloud_region_id: 0,
        page: 1,
        page_size: -1,
        is_active: true
      });
      const formattedNodes = (data.nodes || []).map((node: any) => ({
        ...node,
        label: `${node.name} (${node.ip})`,
        value: node.id
      }));
      setNodeList(formattedNodes);
    } finally {
      setNodesLoading(false);
    }
  };

  const validateTableData = (): boolean => {
    if (!currentConfig?.table_columns) return true;
    let hasError = false;
    const newData = [...dataSource];
    // 先清除所有字段的错误状态
    newData.forEach((row, index) => {
      currentConfig.table_columns.forEach((column: any) => {
        const { name } = column;
        newData[index] = {
          ...newData[index],
          [`${name}_error`]: null
        };
      });
    });
    // 验证所有字段
    currentConfig.table_columns.forEach((column: any) => {
      const { name, rules = [], required = false } = column;
      dataSource.forEach((row, index) => {
        const value = row[name];
        let errorMsg: string | null = null;
        // 如果字段标记为required，进行必填验证
        if (required) {
          if (
            value === undefined ||
            value === null ||
            value === '' ||
            (Array.isArray(value) && value.length === 0)
          ) {
            errorMsg = t('common.required');
          }
        }
        // 如果有rules配置，按照rules验证（只支持pattern类型）
        if (rules.length > 0 && !errorMsg) {
          for (const rule of rules) {
            // 正则验证（只在有值时验证）
            if (rule.type === 'pattern') {
              if (value !== undefined && value !== null && value !== '') {
                const regex = new RegExp(rule.pattern);
                if (!regex.test(String(value))) {
                  errorMsg = rule.message || t('common.required');
                  break;
                }
              }
            }
          }
        }
        if (errorMsg) {
          hasError = true;
          newData[index] = {
            ...newData[index],
            [`${name}_error`]: errorMsg
          };
        }
      });
    });
    // 更新数据源以显示错误状态
    setDataSource(newData);
    if (hasError) {
      return false;
    }
    return true;
  };

  const handleSave = () => {
    // 先验证表格数据
    if (!validateTableData()) {
      return;
    }
    form.validateFields().then((values) => {
      try {
        const row = cloneDeep(values);
        delete row.nodes;
        const params =
          configsInfo?.getParams?.(row, {
            dataSource,
            nodeList,
            objectId
          }) || {};
        params.monitor_object_id = Number(objectId);
        params.monitor_plugin_id = Number(pluginId);
        addNodesConfig(params);
      } catch (error: any) {
        message.error(error?.message || t('common.operationFailed'));
      }
    });
  };

  const addNodesConfig = async (params = {}) => {
    try {
      setConfirmLoading(true);
      await updateNodeChildConfig(params);
      message.success(t('common.addSuccess'));
      const searchParams = new URLSearchParams({
        objId: objectId
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
              <div className="flex gap-[8px]">
                <Button
                  icon={<UploadOutlined />}
                  type="primary"
                  onClick={handleImport}
                >
                  {t('common.import')}
                </Button>
                <Dropdown
                  menu={{
                    items: batchMenuItems,
                    onClick: handleBatchMenuClick
                  }}
                  disabled={!selectedRowKeys.length}
                >
                  <Button>
                    {t('monitor.integrations.batchOperation')}
                    <DownOutlined className="ml-[4px]" />
                  </Button>
                </Dropdown>
              </div>
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
                    // 校验值得唯一性
                    if (currentConfig?.table_columns) {
                      const uniqueFields = currentConfig.table_columns.filter(
                        (col: any) => col.is_only === true
                      );
                      for (const field of uniqueFields) {
                        const fieldName = field.name;
                        const fieldLabel = field.label;
                        const valueSet = new Set<string>();
                        for (const row of dataSource) {
                          const value = row[fieldName];
                          // 跳过空值
                          if (
                            value === null ||
                            value === undefined ||
                            value === ''
                          ) {
                            continue;
                          }
                          const valueStr = String(value);
                          if (valueSet.has(valueStr)) {
                            const errorMsg = t(
                              'monitor.integrations.duplicateFieldError'
                            )
                              .replace('{{field}}', fieldLabel)
                              .replace('{{value}}', valueStr);
                            return Promise.reject(new Error(errorMsg));
                          }
                          valueSet.add(valueStr);
                        }
                      }
                    }
                    return Promise.resolve();
                  }
                }
              ]}
            >
              <CustomTable
                scroll={{ x: 'calc(100vw - 320px)' }}
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
      <ExcelImportModal
        ref={excelImportModalRef}
        onSuccess={handleImportSuccess}
      />
    </Spin>
  );
};

export default AutomaticConfiguration;
