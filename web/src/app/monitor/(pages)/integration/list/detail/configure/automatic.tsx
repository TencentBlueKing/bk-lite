import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Form, Button, message, Spin, Dropdown, Modal, Tag, Select } from 'antd';
import type { MenuProps } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DownOutlined,
  LoadingOutlined,
  UploadOutlined
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import CompactEmptyState from '@/components/compact-empty-state';
import CustomTable from '@/components/custom-table';
import { v4 as uuidv4 } from 'uuid';
import { useSearchParams, useRouter } from 'next/navigation';
import useApiClient from '@/utils/request';
import useIntegrationApi from '@/app/monitor/api/integration';
import useEventApi from '@/app/monitor/api/event';
import FieldGuideTip from '@/components/field-guide-tip';
import type { PolicyTemplateItem } from '@/app/monitor/(pages)/event/template/templateBulkUtils';
import {
  COLLECTION_POLICY_CONTROL_WIDTH,
  COLLECTION_POLICY_FIELD,
  buildCollectionPolicyApplyPayload,
  defaultSelectedTemplateKeys,
  extractCollectInstanceIds,
  omitCollectionPolicyField,
  policyTemplateSelectOptions,
  resolvePolicyTemplateList,
  selectedPolicyTemplates
} from './automaticPolicyApply';
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
import {
  getSnmpFilterMutexConflicts,
  trackSnmpFilterMutexLastChanged
} from '@/app/monitor/hooks/integration/snmpFilterMutex';
import { toMonitorNodeOption } from '@/app/monitor/hooks/integration/nodeOptions';
import BatchEditModal from './batchEditModal';
import ExcelImportModal from './excelImportModal';
import PluginGuidePanel from './pluginGuidePanel';
import GuideEntryButton from './guideEntryButton';
import { normalizePasswordFields } from '@/components/password/normalizePasswordWhitespace';
import {
  buildCollectDetectFingerprint as buildCollectDetectFingerprintValue,
  CollectDetectMode,
  getCollectDetectResultPresentation,
  getRowsForBatchCollectDetect,
  shouldAcceptCollectDetectResult,
  shouldAutoShowCollectDetectResultOnComplete
} from './automaticCollectDetect';
import {
  collectDependencyFieldNames,
  filterColumnsByDependency,
  FormFieldDependency,
  isDependencySatisfied
} from '@/app/monitor/hooks/integration/formFieldDependency';
import {
  applyIfmibDeploymentState,
  getIfmibDeploymentPatch
} from './ifmibDeploymentState';
import { getSnmpInterfaceFilterModePatch } from '@/app/monitor/hooks/integration/snmpInterfaceFilterMode';
import {
  countAccessAssets,
  mergeImportedAssetRows
} from './automaticAssetCount';
const { confirm } = Modal;

interface CollectDetectState {
  status: 'pending' | 'running' | 'success' | 'failed';
  fingerprint?: string;
  result?: Record<string, any>;
  error_message?: string;
}

interface IntegrationTableColumnConfig {
  name: string;
  label: string;
  is_only?: boolean;
  dependency?: FormFieldDependency;
  [key: string]: unknown;
}

interface TableValidationResult {
  data: IntegrationMonitoredObject[] | null;
  trimmedPassword: boolean;
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
  const { getPolicyTemplate, bulkCreatePoliciesFromTemplates } = useEventApi();
  const router = useRouter();
  const { renderTableColumn } = useConfigRenderer();
  const jsonConfig = usePluginFromJson();
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const pluginId = searchParams.get('plugin_id') || '';
  const objectId = searchParams.get('id') || '';
  const objectName = searchParams.get('name') || '';
  const enableIfmibFromUrl = searchParams.get('enable_ifmib') !== 'false';
  // URL 常见参数：name / plugin_name；兼容历史 plugin_display_name。
  const pluginDisplayName =
    searchParams.get('plugin_display_name') ||
    searchParams.get('name') ||
    searchParams.get('plugin_name') ||
    '';
  const [dataSource, setDataSource] = useState<IntegrationMonitoredObject[]>(
    []
  );
  const [nodeList, setNodeList] = useState<TableDataItem[]>([]);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [nodesLoading, setNodesLoading] = useState<boolean>(false);
  const [initTableItems, setInitTableItems] =
    useState<IntegrationMonitoredObject>({});
  const [isTableInitialized, setIsTableInitialized] = useState<boolean>(false);
  const hasInitializedFormRef = useRef(false);
  const [currentConfig, setCurrentConfig] = useState<any>(null);
  const [configLoading, setConfigLoading] = useState<boolean>(false);
  const [policyTemplates, setPolicyTemplates] = useState<PolicyTemplateItem[]>(
    []
  );
  const [policyTemplatesLoading, setPolicyTemplatesLoading] =
    useState<boolean>(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [collectDetectTasks, setCollectDetectTasks] = useState<
    Record<string, CollectDetectState>
  >({});
  const collectDetectTimersRef = useRef<
    Record<string, ReturnType<typeof setTimeout>>
  >({});
  const activeCollectDetectFingerprintRef = useRef<Record<string, string>>({});
  const batchEditModalRef = useRef<any>(null);
  const excelImportModalRef = useRef<any>(null);

  const clearCollectDetectState = () => {
    Object.values(collectDetectTimersRef.current).forEach(clearTimeout);
    collectDetectTimersRef.current = {};
    activeCollectDetectFingerprintRef.current = {};
    setCollectDetectTasks({});
  };

  const onTableDataChange = (data: IntegrationMonitoredObject[]) => {
    setDataSource(data);
    clearCollectDetectState();
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

  useEffect(() => {
    if (isLoading || !pluginId || !objectName) {
      setPolicyTemplates([]);
      setPolicyTemplatesLoading(false);
      form.setFieldsValue({ [COLLECTION_POLICY_FIELD]: [] });
      return;
    }
    let cancelled = false;
    setPolicyTemplatesLoading(true);
    getPolicyTemplate({
      monitor_object_name: objectName,
      plugin_id: pluginId
    })
      .then((data) => {
        if (cancelled) return;
        const templates = resolvePolicyTemplateList(data, pluginId);
        setPolicyTemplates(templates);
        form.setFieldsValue({
          [COLLECTION_POLICY_FIELD]: defaultSelectedTemplateKeys(templates)
        });
      })
      .catch(() => {
        if (cancelled) return;
        setPolicyTemplates([]);
        form.setFieldsValue({ [COLLECTION_POLICY_FIELD]: [] });
      })
      .finally(() => {
        if (!cancelled) {
          setPolicyTemplatesLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // 模板列表只随当前插件/对象切换；getPolicyTemplate 引用变化不应冲掉用户选择。
  }, [isLoading, pluginId, objectName, form]);

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
  const [formSnapshot, setFormSnapshot] = useState<Record<string, any>>({});
  const tableDependencyFields = useMemo(
    () => collectDependencyFieldNames(currentConfig?.table_columns),
    [currentConfig]
  );
  const visibleTableColumns = useMemo<IntegrationTableColumnConfig[]>(
    () =>
      filterColumnsByDependency<IntegrationTableColumnConfig>(
        currentConfig?.table_columns || [],
        (field) =>
          Object.prototype.hasOwnProperty.call(formSnapshot, field)
            ? formSnapshot[field]
            : form.getFieldValue(field)
      ),
    [currentConfig, formSnapshot, form]
  );
  const accessAssetCount = useMemo(
    () => countAccessAssets(dataSource, visibleTableColumns, initTableItems),
    [dataSource, visibleTableColumns, initTableItems]
  );

  useEffect(() => {
    return () => {
      Object.values(collectDetectTimersRef.current).forEach(clearTimeout);
    };
  }, []);

  useEffect(() => {
    if (!currentConfig?.table_columns?.length) return;
    const getValue = (field: string) =>
      Object.prototype.hasOwnProperty.call(formSnapshot, field)
        ? formSnapshot[field]
        : form.getFieldValue(field);
    const hiddenNames = currentConfig.table_columns
      .filter(
        (column: any) =>
          column?.name && !isDependencySatisfied(column.dependency, getValue)
      )
      .map((column: any) => column.name as string);
    if (!hiddenNames.length) return;
    setDataSource((prev) => {
      let changed = false;
      const next = prev.map((row) => {
        let rowChanged = false;
        const updated: IntegrationMonitoredObject = { ...row };
        hiddenNames.forEach((name) => {
          const value = updated[name];
          if (
            value !== undefined &&
            value !== null &&
            value !== '' &&
            !(Array.isArray(value) && value.length === 0)
          ) {
            updated[name] = undefined;
            updated[`${name}_error`] = null;
            rowChanged = true;
          }
        });
        if (rowChanged) {
          changed = true;
          return updated;
        }
        return row;
      });
      return changed ? next : prev;
    });
  }, [currentConfig, formSnapshot, form]);

  const getRowNodeId = (record: IntegrationMonitoredObject) => {
    if (Array.isArray(record.node_ids)) {
      return record.node_ids[0];
    }
    return record.node_ids;
  };

  const buildDetectInstance = (record: IntegrationMonitoredObject) => {
    const formValues = omitCollectionPolicyField(
      cloneDeep(form.getFieldsValue())
    );
    delete formValues.nodes;
    const rowValues = Object.keys(record)
      .filter((key) => key !== 'key' && !key.endsWith('_error'))
      .reduce((acc, key) => {
        acc[key] = record[key];
        return acc;
      }, {} as Record<string, any>);
    const instance: Record<string, any> = {
      ...formValues,
      ...rowValues,
      instance_type: configsInfo?.instance_type
    };
    return instance;
  };

  const buildCollectDetectFingerprint = (record: IntegrationMonitoredObject) =>
    buildCollectDetectFingerprintValue({
      monitorPluginId: Number(pluginId),
      monitorObjectId: Number(objectId),
      nodeId: getRowNodeId(record),
      instance: buildDetectInstance(record)
    });

  const getCollectDetectOutputBlocks = (task: CollectDetectState) => {
    const result = task.result || {};
    return [
      { label: 'stdout', value: result.stdout },
      { label: 'stderr', value: result.stderr || task.error_message }
    ].filter((item) => item.value);
  };

  const showCollectDetectResult = (task: CollectDetectState) => {
    const presentation = getCollectDetectResultPresentation(task);
    const result = task.result || {};
    const outputBlocks = getCollectDetectOutputBlocks(task);
    const icon =
      presentation.tone === 'success' ? (
        <CheckCircleOutlined className="text-[#52c41a]" />
      ) : presentation.tone === 'error' ? (
        <CloseCircleOutlined className="text-[#ff4d4f]" />
      ) : (
        <LoadingOutlined className="text-[#1677ff]" />
      );
    Modal.info({
      icon,
      title: t(presentation.titleKey),
      width: 720,
      content: (
        <div className="mt-[14px]">
          <div className="grid grid-cols-2 gap-[10px] rounded-[6px] border border-[#e5e7eb] bg-[#fafafa] p-[12px]">
            <div>
              <div className="text-[12px] text-[#6b7280]">
                {t('monitor.integrations.collectDetectStatus')}
              </div>
              <Tag
                color={
                  presentation.tone === 'success'
                    ? 'success'
                    : presentation.tone === 'error'
                      ? 'error'
                      : 'processing'
                }
                className="mt-[6px]"
              >
                {t(presentation.titleKey)}
              </Tag>
            </div>
            <div>
              <div className="text-[12px] text-[#6b7280]">
                {t('monitor.integrations.collectDetectExitCode')}
              </div>
              <div className="mt-[6px] font-mono text-[13px] text-[#111827]">
                {result.exit_code ?? '--'}
              </div>
            </div>
          </div>
          <div className="mt-[12px] space-y-[10px]">
            {result.request_url && (
              <div className="overflow-hidden rounded-[6px] border border-[var(--color-border)]">
                <div className="border-b border-[var(--color-border)] bg-[var(--color-fill-1)] px-[12px] py-[8px] text-[12px] text-[var(--color-text-2)]">
                  {t('monitor.integrations.collectDetectRequestUrl')}
                </div>
                <div className="break-all bg-[var(--color-bg)] px-[12px] py-[10px] font-mono text-[12px] leading-[18px] text-[var(--color-text-1)]">
                  {String(result.request_url)}
                </div>
              </div>
            )}
            {outputBlocks.length ? (
              outputBlocks.map((item) => (
                <div
                  key={item.label}
                  className="overflow-hidden rounded-[6px] border border-[#e5e7eb]"
                >
                  <div className="border-b border-[#e5e7eb] bg-[#f8fafc] px-[12px] py-[8px] font-mono text-[12px] text-[#374151]">
                    {item.label}
                  </div>
                  <pre className="m-0 max-h-[300px] overflow-auto whitespace-pre-wrap bg-[#111827] p-[12px] font-mono text-[12px] leading-[18px] text-[#e5e7eb]">
                    {String(item.value)}
                  </pre>
                </div>
              ))
            ) : (
              <div className="rounded-[6px] border border-dashed border-[#d1d5db] bg-[#fafafa] px-[12px] py-[18px] text-center text-[13px] text-[#6b7280]">
                {t('monitor.integrations.collectDetectNoOutput')}
              </div>
            )}
          </div>
        </div>
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
    fingerprint: string,
    mode: CollectDetectMode,
    retryCount = 0
  ) => {
    try {
      const task = (await getCollectDetectTask(taskId)) as CollectDetectState;
      if (
        !shouldAcceptCollectDetectResult(
          { rowKey, fingerprint },
          activeCollectDetectFingerprintRef.current
        )
      ) {
        return;
      }
      updateCollectDetectState(rowKey, { ...task, fingerprint });
      if (['pending', 'running'].includes(task.status) && retryCount < 60) {
        collectDetectTimersRef.current[rowKey] = setTimeout(() => {
          pollCollectDetectTask(
            rowKey,
            taskId,
            fingerprint,
            mode,
            retryCount + 1
          );
        }, 2000);
        return;
      }
      // 产品决策：测试完成不主动弹窗，由用户点击列表中的状态标签自行查看。
      if (shouldAutoShowCollectDetectResultOnComplete(mode)) {
        showCollectDetectResult(task);
      }
    } catch (error: any) {
      if (
        !shouldAcceptCollectDetectResult(
          { rowKey, fingerprint },
          activeCollectDetectFingerprintRef.current
        )
      ) {
        return;
      }
      updateCollectDetectState(rowKey, {
        status: 'failed',
        fingerprint,
        error_message: error?.message || t('common.operationFailed')
      });
    }
  };

  const handleCollectDetect = async (
    record: IntegrationMonitoredObject,
    mode: CollectDetectMode = 'single'
  ) => {
    const rowKey = record.key as string;
    const nodeId = getRowNodeId(record);
    if (!nodeId) {
      message.warning(t('monitor.integrations.collectDetectNodeRequired'));
      return;
    }
    const fingerprint = buildCollectDetectFingerprint(record);
    activeCollectDetectFingerprintRef.current[rowKey] = fingerprint;
    updateCollectDetectState(rowKey, { status: 'running', fingerprint });
    try {
      const data = (await createCollectDetectTask({
        monitor_plugin_id: Number(pluginId),
        monitor_object_id: Number(objectId),
        node_id: nodeId,
        instance_key: record.instance_id || record.instance_name || rowKey,
        instance: buildDetectInstance(record)
      })) as { task_id: React.Key };
      pollCollectDetectTask(rowKey, data.task_id, fingerprint, mode);
    } catch (error: any) {
      updateCollectDetectState(rowKey, {
        status: 'failed',
        fingerprint,
        error_message: error?.message || t('common.operationFailed')
      });
    }
  };

  const handleBatchCollectDetect = async () => {
    const selectedRows = getRowsForBatchCollectDetect(
      dataSource,
      selectedRowKeys
    );
    const runnableRows = selectedRows.filter((row) => getRowNodeId(row));
    if (!runnableRows.length) {
      message.warning(t('monitor.integrations.collectDetectNodeRequired'));
      return;
    }
    message.info(
      t('monitor.integrations.collectDetectBatchStarted', '', {
        count: runnableRows.length
      })
    );
    await Promise.all(
      runnableRows.map((row) => handleCollectDetect(row, 'batch'))
    );
  };

  const renderCollectDetectStatus = (record: IntegrationMonitoredObject) => {
    const task = collectDetectTasks[record.key as string];
    if (!task || task.fingerprint !== buildCollectDetectFingerprint(record)) {
      return <Tag>{t('monitor.integrations.collectDetectUntested')}</Tag>;
    }
    const clickableClassName = 'cursor-pointer';
    if (['pending', 'running'].includes(task.status)) {
      return (
        <Tag
          color="processing"
          className={clickableClassName}
          onClick={() => showCollectDetectResult(task)}
        >
          {t('monitor.integrations.collectDetectRunning')}
        </Tag>
      );
    }
    return task.status === 'success' ? (
      <Tag
        color="success"
        className={clickableClassName}
        onClick={() => showCollectDetectResult(task)}
      >
        {t('monitor.integrations.collectDetectSuccess')}
      </Tag>
    ) : (
      <Tag
        color="error"
        className={clickableClassName}
        onClick={() => showCollectDetectResult(task)}
      >
        {t('monitor.integrations.collectDetectFailed')}
      </Tag>
    );
  };

  // 动态生成 columns
  const columns = useMemo(() => {
    if (configLoading || !currentConfig || !visibleTableColumns.length) {
      return [];
    }
    const dataColumns = visibleTableColumns.map((columnConfig: any) =>
      renderTableColumn(columnConfig, dataSource, onTableDataChange, {
        node_ids_option: nodeList
      })
    );
    // 检查是否有 enable_row_filter 为 true 的列
    const hasRowFilter = visibleTableColumns.some(
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
              loading={['pending', 'running'].includes(
                collectDetectTasks[record.key as string]?.fingerprint ===
                  buildCollectDetectFingerprint(record)
                  ? collectDetectTasks[record.key as string]?.status
                  : ''
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
    visibleTableColumns,
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
  }, [isLoading]);

  useEffect(() => {
    hasInitializedFormRef.current = false;
  }, [pluginId]);

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

  // defaultForm 每次 buildPluginUI 都会新建对象引用；用序列化值做依赖，避免
  // effect 每轮 setFormSnapshot → 重渲染 → 再触发 effect 的死循环卡死页面。
  const defaultFormKey = JSON.stringify(formConfig?.defaultForm ?? {});

  useEffect(() => {
    if (configLoading) return;
    const defaults = formConfig?.defaultForm;
    if (!defaults) return;
    if (!hasInitializedFormRef.current) {
      const initialValues = applyIfmibDeploymentState(defaults, enableIfmibFromUrl);
      form.setFieldsValue(initialValues);
      trackSnmpFilterMutexLastChanged({}, form.getFieldsValue(true), form);
      hasInitializedFormRef.current = true;
    }
    // UI 字段可能在首次初始化后才挂载；其自身 default_value=true 会覆盖前一次
    // 空表单初始化。因此只在 IF-MIB 字段真实可用时，以 URL 中当前下发流程状态回填。
    const ifmibPatch = getIfmibDeploymentPatch(defaults, enableIfmibFromUrl);
    if (Object.keys(ifmibPatch).length) {
      form.setFieldsValue(ifmibPatch);
    }
    setFormSnapshot((prev) => {
      const next = {
        ...defaults,
        ...prev,
        ...form.getFieldsValue(true)
      };
      let unchanged = false;
      try {
        unchanged = JSON.stringify(prev) === JSON.stringify(next);
      } catch {
        unchanged = false;
      }
      return unchanged ? prev : next;
    });
    // 刻意依赖 defaultFormKey 而非 defaultForm 对象引用。
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stabilize defaultForm identity
  }, [configLoading, defaultFormKey, enableIfmibFromUrl, form]);

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
      columns: visibleTableColumns,
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
      columns: visibleTableColumns,
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
    setDataSource(
      mergeImportedAssetRows(
        dataSource,
        newRows,
        visibleTableColumns,
        initTableItems
      )
    );
  };

  const batchMenuItems: MenuProps['items'] = [
    ...(supportCollectDetect
      ? [
        {
          key: 'batchCollectDetect',
          label: t('monitor.integrations.collectDetectBatch')
        }
      ]
      : []),
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
    if (e.key === 'batchCollectDetect') {
      handleBatchCollectDetect();
    } else if (e.key === 'batchEdit') {
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
      const formattedNodes = (data.nodes || []).map((node: any) =>
        toMonitorNodeOption(
          node,
          t('monitor.integrations.hostMonitoringAlreadyConfigured'),
          t('monitor.integrations.hostMonitoringStatusUnavailable')
        )
      );
      setNodeList(formattedNodes);
    } finally {
      setNodesLoading(false);
    }
  };

  const validateTableData = (): TableValidationResult => {
    if (!visibleTableColumns.length) {
      return { data: dataSource, trimmedPassword: false };
    }
    let hasError = false;
    let trimmedPassword = false;
    const normalizedData = dataSource.map((row) => {
      const result = normalizePasswordFields(
        row as Record<string, unknown>,
        visibleTableColumns,
        { includeReadOnly: true }
      );
      if (result.changedFields.length) {
        trimmedPassword = true;
      }
      return result.values as IntegrationMonitoredObject;
    });
    const newData = [...normalizedData];
    // 先清除所有字段的错误状态
    newData.forEach((row, index) => {
      visibleTableColumns.forEach((column: any) => {
        const { name } = column;
        newData[index] = {
          ...newData[index],
          [`${name}_error`]: null
        };
      });
    });
    // 验证所有字段
    visibleTableColumns.forEach((column: any) => {
      const { name, rules = [], required = false } = column;
      normalizedData.forEach((row, index) => {
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
      return { data: null, trimmedPassword };
    }
    return { data: newData, trimmedPassword };
  };

  const handleSave = () => {
    if (policyTemplatesLoading) {
      return;
    }
    const normalizedForm = normalizePasswordFields(
      form.getFieldsValue(true),
      currentConfig?.form_fields,
      { includeReadOnly: true }
    );
    const trimmedFormPassword = normalizedForm.changedFields.length > 0;
    if (trimmedFormPassword) {
      form.setFieldsValue(normalizedForm.values);
    }
    // 先验证表格数据
    const tableValidation = validateTableData();
    if (trimmedFormPassword || tableValidation.trimmedPassword) {
      message.warning(t('common.passwordWhitespaceTrimmed'));
    }
    if (!tableValidation.data) {
      return;
    }
    form.validateFields().then((values) => {
      try {
        const mutexErrors = getSnmpFilterMutexConflicts(values, t);
        if (mutexErrors.length) {
          mutexErrors.forEach((msg) => message.error(msg));
          return;
        }
        const templatesToApply = selectedPolicyTemplates(
          policyTemplates,
          values[COLLECTION_POLICY_FIELD]
        );
        const row = omitCollectionPolicyField(cloneDeep(values));
        delete row.nodes;
        const params =
          configsInfo?.getParams?.(row, {
            dataSource: tableValidation.data,
            nodeList,
            objectId
          }) || {};
        params.monitor_object_id = Number(objectId);
        params.monitor_plugin_id = Number(pluginId);
        addNodesConfig(params, templatesToApply);
      } catch (error: any) {
        message.error(error?.message || t('common.operationFailed'));
      }
    });
  };

  const addNodesConfig = async (
    params: Record<string, any> = {},
    templatesToApply: PolicyTemplateItem[] = []
  ) => {
    try {
      setConfirmLoading(true);
      const collectResult = await updateNodeChildConfig(params);
      if (templatesToApply.length) {
        const policyPayload = buildCollectionPolicyApplyPayload({
          monitorObjectId: objectId,
          templates: templatesToApply,
          instanceIds: extractCollectInstanceIds(collectResult, params)
        });
        if (!policyPayload) {
          message.success(t('common.addSuccess'));
          message.error(
            t('monitor.integrations.policyCreateFailed', '', {
              error: t('common.operationFailed')
            })
          );
        } else {
          try {
            const result = await bulkCreatePoliciesFromTemplates(policyPayload);
            message.success(t('common.addSuccess'));
            message.success(
              t('monitor.events.bulkCreateSuccess', '', {
                count: result?.created_count ?? templatesToApply.length
              })
            );
          } catch (policyError: any) {
            message.success(t('common.addSuccess'));
            message.error(
              t('monitor.integrations.policyCreateFailed', '', {
                error:
                  policyError?.response?.data?.message ||
                  policyError?.message ||
                  t('common.operationFailed')
              })
            );
          }
        }
      } else {
        message.success(t('common.addSuccess'));
      }
      const nextSearch = new URLSearchParams({
        objId: objectId
      });
      router.push(`/monitor/integration/list?${nextSearch.toString()}`);
    } catch (error: any) {
      message.error(
        error?.response?.data?.message ||
          error?.message ||
          t('common.operationFailed')
      );
    } finally {
      setConfirmLoading(false);
    }
  };

  // 判断是否显示空状态
  const showEmpty =
    !configLoading && (!currentConfig || !currentConfig.table_columns);

  const configSection = showEmpty ? (
    <div
      className="flex items-center justify-center"
      style={{ minHeight: '400px' }}
    >
      <CompactEmptyState description={t('monitor.integrations.noConfigData')} />
    </div>
  ) : (
    <Form
      form={form}
      name="basic"
      layout="vertical"
      onValuesChange={(changed, all) => {
        const changedKeys = Object.keys(changed);
        if (
          !(
            changedKeys.length === 1 &&
            changedKeys[0] === COLLECTION_POLICY_FIELD
          )
        ) {
          clearCollectDetectState();
        }
        const defaultIfTypeExclude = currentConfig?.form_fields?.find(
          (field: { name?: string }) => field.name === 'iftype_exclude'
        )?.default_value;
        const interfaceFilterModePatch = getSnmpInterfaceFilterModePatch(
          changed,
          defaultIfTypeExclude
        );
        const nextValues = Object.keys(interfaceFilterModePatch).length
          ? { ...all, ...interfaceFilterModePatch }
          : all;
        if (Object.keys(interfaceFilterModePatch).length) {
          form.setFieldsValue(interfaceFilterModePatch);
        }
        trackSnmpFilterMutexLastChanged(changed, nextValues, form);
        if (Object.prototype.hasOwnProperty.call(changed, 'enable_ifmib')) {
          const params = new URLSearchParams(searchParams);
          params.set('enable_ifmib', String(changed.enable_ifmib !== false));
          router.replace(`/monitor/integration/list/detail/configure?${params.toString()}`);
        }
        if (
          !tableDependencyFields.length ||
          tableDependencyFields.some((field) =>
            Object.prototype.hasOwnProperty.call(changed, field)
          )
        ) {
          setFormSnapshot(nextValues);
        }
      }}
    >
      <div className="flex items-center justify-between mb-[10px]">
        <b className="text-[14px] ml-[-10px]">
          {t('monitor.integrations.configuration')}
        </b>
        <GuideEntryButton />
      </div>
      {formItems}
      <Form.Item
        name={COLLECTION_POLICY_FIELD}
        label={
          <span className="inline-flex items-center">
            {t('monitor.integrations.monitoringPolicy')}
            <FieldGuideTip
              short={t('monitor.integrations.monitoringPolicyDes')}
              title={t('monitor.integrations.fieldGuideTip')}
            />
          </span>
        }
      >
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          loading={policyTemplatesLoading}
          options={policyTemplateSelectOptions(policyTemplates)}
          placeholder={t(
            'monitor.integrations.monitoringPolicyPlaceholder'
          )}
          style={{ width: COLLECTION_POLICY_CONTROL_WIDTH }}
        />
      </Form.Item>
      <b className="text-[14px] flex mb-[10px] ml-[-10px]">
        {t('monitor.integrations.basicInformation')}
      </b>
      <div className="flex items-center justify-between mb-[10px]">
        <div className="flex items-center gap-[8px]">
          <span className="text-[14px]">
            {t('monitor.integrations.MonitoredObject')}
            <span
              className="text-[#ff4d4f] align-middle text-[14px] ml-[4px]"
              style={{ fontFamily: 'SimSun, sans-serif' }}
            >
              *
            </span>
          </span>
          <span
            aria-live="polite"
            className="text-[13px] tabular-nums text-[var(--color-text-2)]"
          >
            {t('monitor.integrations.accessAssetCount', '', {
              count: accessAssetCount
            })}
          </span>
          <span className="text-[12px] text-[var(--color-text-3)]">
            {t('monitor.integrations.accessAssetCountHint')}
          </span>
        </div>
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
              if (visibleTableColumns.length) {
                const uniqueFields = visibleTableColumns.filter(
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
                        'monitor.integrations.duplicateFieldError',
                        '',
                        {
                          field: fieldLabel,
                          value: valueStr
                        }
                      );
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
  );

  return (
    <Spin spinning={configLoading || nodesLoading || policyTemplatesLoading}>
      <div className="px-[10px]">
        <PluginGuidePanel
          pluginId={pluginId}
          pluginName={pluginDisplayName}
        >
          {configSection}
        </PluginGuidePanel>
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
