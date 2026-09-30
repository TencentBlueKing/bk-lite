import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { Form, Button, Input, message, Spin, Dropdown, Modal, Radio, Tag, Select, Switch, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DownOutlined,
  ExclamationCircleFilled,
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
import useMonitorUserHabitApi from '@/app/monitor/api/userHabit';
import FieldGuideTip from '@/components/field-guide-tip';
import type { PolicyTemplateItem } from '@/app/monitor/(pages)/event/template/templateBulkUtils';
import type { ChannelItem } from '@/app/monitor/types/event';
import {
  ALERT_CENTER_NATS_METHOD,
  COLLECTION_POLICY_ALERT_CENTER_FIELD,
  COLLECTION_POLICY_CONTROL_WIDTH,
  COLLECTION_POLICY_FIELD,
  COLLECTION_POLICY_NAME_PREFIX_FIELD,
  buildCollectionPolicyApplyPayload,
  collectionPolicyHabitKey,
  collectionPolicyHabitValue,
  extractCollectInstanceIds,
  isCollectionPolicyUiField,
  omitCollectionPolicyField,
  parseRememberedPushAlertCenter,
  parseRememberedTemplateKeys,
  pickAlertCenterChannelIds,
  policyTemplateSelectOptions,
  resolvePolicyTemplateList,
  resolveRememberedTemplateKeys,
  selectedPolicyTemplates
} from './automaticPolicyApply';
import { COLLECTION_POLICY_BULK_CONFIG_DEFAULTS } from '@/app/monitor/(pages)/event/template/templateBulkUtils';
import { TableDataItem } from '@/app/monitor/types';
import {
  IntegrationAccessProps,
  IntegrationMonitoredObject
} from '@/app/monitor/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import { cloneDeep } from 'lodash';
import { fillOptionalFormFields, usePluginFromJson } from '@/app/monitor/hooks/integration/usePluginFromJson';
import { useConfigRenderer } from '@/app/monitor/hooks/integration/useConfigRenderer';
import { cloudRegionProviderFromPlugin, useCloudRegionOptions } from '@/app/monitor/hooks/integration/useQcloudRegionOptions';
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
import ScriptTrialRunArea, {
  scriptTrialBlocksMetricActions
} from './scriptTrialRunArea';
import { applyScriptCollectSubmit, syncScriptRunAsForOs } from './scriptCollectForm';
import { resolveScriptTimeoutSeconds, SCRIPT_DETECT_TIMEOUT_MARGIN_SECONDS } from './scriptCollectTimeout';
import { hydrateScriptCollectFormValues } from './scriptCollectHydrate';
import {
  collectReservedTagViolations,
  excludeSelfMonitorMetrics,
  catalogMetricRefLabel,
  findDuplicateDisplayNames,
  listPluginCatalogMetrics,
  persistScriptMetrics,
  planScriptMetricHardSyncDeletes,
  SCRIPT_METRIC_PERSIST_MODE_ADD,
  SCRIPT_METRIC_PERSIST_MODE_OVERWRITE,
  ScriptMetricPersistMode,
  CatalogMetricRef
} from './scriptMetricPersist';
import {
  buildScriptMetricEditCarry,
  SCRIPT_METRIC_DRAFT_QUERY,
  writeScriptMetricEditCarry
} from './scriptMetricEditCarry';
import { BusinessMetricItem } from './scriptMetricsParser';
const { confirm } = Modal;

const OVERWRITE_NAME_PREVIEW = 8;

type ScriptMetricWriteMode = ScriptMetricPersistMode;

interface PendingScriptMetricWrite {
  params: Record<string, any>;
  templatesToApply: PolicyTemplateItem[];
  namePrefix?: string;
  pushAlertCenter: boolean;
  alertCenterChannelIds: Array<string | number>;
  staleDeletes: CatalogMetricRef[];
}

const ScriptMetricOverwriteContent = ({
  names,
  summary,
  cancelHint,
  expandLabel,
  collapseLabel
}: {
  names: string[];
  summary: string;
  cancelHint: string;
  expandLabel: string;
  collapseLabel: string;
}) => {
  const [expanded, setExpanded] = useState(false);
  const hiddenCount = names.length - OVERWRITE_NAME_PREVIEW;
  const visible =
    expanded || hiddenCount <= 0
      ? names
      : names.slice(0, OVERWRITE_NAME_PREVIEW);
  return (
    <div>
      <p className="mb-2">{summary}</p>
      <ul className="mb-2 max-h-40 list-disc overflow-auto pl-5">
        {visible.map((name, index) => (
          <li key={`${name}-${index}`} className="break-all">
            {name}
          </li>
        ))}
      </ul>
      {hiddenCount > 0 ? (
        <Button
          type="link"
          className="h-auto px-0"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setExpanded((open) => !open);
          }}
        >
          {expanded ? collapseLabel : expandLabel}
        </Button>
      ) : null}
      <p className="mb-0 mt-2 text-[var(--color-text-3)]">{cancelHint}</p>
    </div>
  );
};

interface CollectDetectState {
  status: 'pending' | 'running' | 'success' | 'failed' | 'warning' | 'stopped';
  warning_type?: 'no_permission' | 'rate_limit';
  fingerprint?: string;
  result?: Record<string, any>;
  error_message?: string;
  started_at?: string | null;
  finished_at?: string | null;
  debug_timeout?: number;
  wait_stopped?: boolean;
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
  const { get, post, patch, isLoading } = useApiClient();
  const {
    createCollectDetectTask,
    getCollectDetectTask,
    getMonitorNodeList,
    updateNodeChildConfig,
    getPluginChildConfig
  } = useIntegrationApi();
  const {
    getPolicyTemplate,
    bulkCreatePoliciesFromTemplates,
    getSystemChannelList
  } = useEventApi();
  const { getUserHabit, saveUserHabit } = useMonitorUserHabitApi();
  const router = useRouter();
  const { renderTableColumn } = useConfigRenderer();
  const jsonConfig = usePluginFromJson();
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const pluginId = searchParams.get('plugin_id') || '';
  const pluginName = searchParams.get('plugin_name') || '';
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
  const saveInFlightRef = useRef(false);
  const [nodesLoading, setNodesLoading] = useState<boolean>(false);
  const [initTableItems, setInitTableItems] =
    useState<IntegrationMonitoredObject>({});
  const [isTableInitialized, setIsTableInitialized] = useState<boolean>(false);
  const hasInitializedFormRef = useRef(false);
  const [storedScriptForm, setStoredScriptForm] = useState<
    Record<string, any> | undefined
  >(undefined);
  const [scriptValuesApplied, setScriptValuesApplied] = useState(false);
  const [currentConfig, setCurrentConfig] = useState<any>(null);
  const [configLoading, setConfigLoading] = useState<boolean>(false);
  const [policyTemplates, setPolicyTemplates] = useState<PolicyTemplateItem[]>(
    []
  );
  const [policyTemplatesLoading, setPolicyTemplatesLoading] =
    useState<boolean>(false);
  const [alertCenterChannels, setAlertCenterChannels] = useState<ChannelItem[]>(
    []
  );
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [activeTrialRowKey, setActiveTrialRowKey] = useState<string>('');
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
    if (data.length > 0 && (!activeTrialRowKey || !data.some((r) => r.key === activeTrialRowKey))) {
      setActiveTrialRowKey(data[0].key as string);
    }
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
      form.setFieldsValue({
        [COLLECTION_POLICY_FIELD]: [],
        [COLLECTION_POLICY_NAME_PREFIX_FIELD]:
          COLLECTION_POLICY_BULK_CONFIG_DEFAULTS.name_prefix,
        [COLLECTION_POLICY_ALERT_CENTER_FIELD]: false
      });
      return;
    }
    let cancelled = false;
    setPolicyTemplatesLoading(true);
    const habitKey = collectionPolicyHabitKey(pluginId);
    Promise.all([
      getPolicyTemplate({
        monitor_object_name: objectName,
        plugin_id: pluginId
      }),
      habitKey
        ? getUserHabit(habitKey).catch(() => null)
        : Promise.resolve(null)
    ])
      .then(([data, habit]) => {
        if (cancelled) return;
        const templates = resolvePolicyTemplateList(data, pluginId);
        setPolicyTemplates(templates);
        form.setFieldsValue({
          [COLLECTION_POLICY_FIELD]: resolveRememberedTemplateKeys(
            templates,
            parseRememberedTemplateKeys(habit)
          ),
          [COLLECTION_POLICY_NAME_PREFIX_FIELD]:
            COLLECTION_POLICY_BULK_CONFIG_DEFAULTS.name_prefix,
          [COLLECTION_POLICY_ALERT_CENTER_FIELD]:
            parseRememberedPushAlertCenter(habit) === true
        });
      })
      .catch(() => {
        if (cancelled) return;
        setPolicyTemplates([]);
        form.setFieldsValue({
          [COLLECTION_POLICY_FIELD]: [],
          [COLLECTION_POLICY_NAME_PREFIX_FIELD]:
            COLLECTION_POLICY_BULK_CONFIG_DEFAULTS.name_prefix,
          [COLLECTION_POLICY_ALERT_CENTER_FIELD]: false
        });
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

  useEffect(() => {
    if (isLoading) {
      setAlertCenterChannels([]);
      return;
    }
    let cancelled = false;
    getSystemChannelList({
      channel_type: 'nats',
      channel_method: ALERT_CENTER_NATS_METHOD
    })
      .then((data) => {
        if (cancelled) return;
        setAlertCenterChannels(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (!cancelled) {
          setAlertCenterChannels([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isLoading]);

  // 获取基础配置（不依赖 dataSource）
  const baseConfig = useMemo(() => {
    if (configLoading || !currentConfig) {
      return null;
    }
    return currentConfig;
  }, [configLoading, currentConfig]);

  const regionProvider = cloudRegionProviderFromPlugin(baseConfig, {
    objectName,
    pluginName,
  });
  const {
    regionOptions,
    loadingRegions,
    refreshRegions,
    multiple: regionMultiple,
  } = useCloudRegionOptions({
    enabled: Boolean(regionProvider),
    provider: regionProvider || 'qcloud',
    form,
  });

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
        region_option: regionOptions,
      },
      optionControls: {
        region_option: {
          loading: loadingRegions,
          onRefresh: refreshRegions,
          multiple: regionMultiple,
        },
      },
    });
    return {
      formItems: cfg.formItems,
      defaultForm: cfg.defaultForm,
      initTableItems: cfg.initTableItems
    };
  }, [
    baseConfig,
    pluginId,
    form,
    nodeList,
    regionOptions,
    loadingRegions,
    refreshRegions,
    regionMultiple,
    jsonConfig.buildPluginUI,
  ]);

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
  const templateType = searchParams.get('template_type') || '';
  const isScriptTemplate =
    templateType === 'script' ||
    collectType === 'script' ||
    currentConfig?.collect_type === 'script';

  useEffect(() => {
    if (!pluginId || configLoading) return;
    if (!isScriptTemplate) {
      setStoredScriptForm((prev) => (prev === undefined ? {} : prev));
      return;
    }
    let cancelled = false;
    getPluginChildConfig({ monitor_plugin_id: pluginId })
      .then((content) => {
        if (cancelled) return;
        setStoredScriptForm(
          hydrateScriptCollectFormValues(
            currentConfig?.form_fields,
            content,
            currentConfig?.collect_type || 'script'
          )
        );
      })
      .catch(() => {
        if (!cancelled) {
          setStoredScriptForm({});
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    pluginId,
    isScriptTemplate,
    configLoading,
    currentConfig,
    getPluginChildConfig
  ]);

  const activeRecord = useMemo(() => {
    return (
      dataSource.find((row) => row.key === activeTrialRowKey) ||
      dataSource[0]
    );
  }, [dataSource, activeTrialRowKey]);

  const activeTrialTask = useMemo(() => {
    if (!activeRecord?.key) return undefined;
    return collectDetectTasks[activeRecord.key as string];
  }, [activeRecord, collectDetectTasks]);

  const scriptTrialFailed =
    isScriptTemplate && scriptTrialBlocksMetricActions(activeTrialTask);

  const activeTrialInstanceName = useMemo(() => {
    if (!activeRecord) return undefined;
    const named =
      activeRecord.instance_name ||
      activeRecord.ip ||
      activeRecord.host ||
      activeRecord.instance_id;
    if (named) return String(named);
    if (dataSource.length < 2) return undefined;
    const index = dataSource.findIndex((row) => row.key === activeRecord.key);
    if (index < 0) return undefined;
    return t('monitor.integrations.trialRunBoundInstance', '实例 {index}', {
      index: index + 1
    });
  }, [activeRecord, dataSource, t]);

  const isAnyTrialRunning = useMemo(() => {
    return Object.values(collectDetectTasks).some(
      (t) => t?.status === 'pending' || t?.status === 'running'
    );
  }, [collectDetectTasks]);

  const [trialMetricsByRow, setTrialMetricsByRow] = useState<
    Record<string, BusinessMetricItem[]>
  >({});
  const [scriptDebugHasBusinessMetrics, setScriptDebugHasBusinessMetrics] =
    useState(false);
  const [scriptCatalogBlocking, setScriptCatalogBlocking] = useState(false);
  const [scriptCatalogError, setScriptCatalogError] = useState(false);
  const [scriptWriteMode, setScriptWriteMode] =
    useState<ScriptMetricWriteMode>(SCRIPT_METRIC_PERSIST_MODE_ADD);
  const [scriptWriteChoice, setScriptWriteChoice] =
    useState<PendingScriptMetricWrite | null>(null);
  const [duplicateDisplayNameWarning, setDuplicateDisplayNameWarning] =
    useState<string[]>([]);

  const handleSelectedScriptMetricsChange = useCallback(
    (metrics: BusinessMetricItem[]) => {
      const rowKey = (activeRecord?.key as string) || 'default';
      setTrialMetricsByRow((prev) => ({
        ...prev,
        [rowKey]: metrics
      }));
    },
    [activeRecord?.key]
  );

  const handleBusinessMetricsAvailableChange = useCallback(
    (available: boolean) => {
      setScriptDebugHasBusinessMetrics(available);
    },
    []
  );

  const selectedScriptMetrics = useMemo(() => {
    const map = new Map<string, BusinessMetricItem>();
    Object.values(trialMetricsByRow).forEach((items) => {
      items.forEach((item) => {
        if (!map.has(item.name)) {
          map.set(item.name, item);
        }
      });
    });
    return Array.from(map.values());
  }, [trialMetricsByRow]);

  const reservedScriptTagKeys = useMemo(
    () => collectReservedTagViolations(selectedScriptMetrics),
    [selectedScriptMetrics]
  );
  const hasReservedScriptTagError = reservedScriptTagKeys.length > 0;
  const hasReservedScriptError = hasReservedScriptTagError;
  const reservedTagRenameText = t(
    'monitor.integrations.reservedTagRename',
    '保留字段，请换名'
  );
  const reservedMetricIdText = t(
    'monitor.integrations.reservedMetricId',
    '指标 ID 与保留字段冲突，请更换'
  );
  const goEditSelectFirstText = t(
    'monitor.integrations.goEditMetricsSelectFirst',
    '请先勾选指标'
  );
  const showSelectMetricsFirst =
    isScriptTemplate &&
    scriptDebugHasBusinessMetrics &&
    !hasReservedScriptError &&
    !selectedScriptMetrics.length;

  const persistSelectedScriptMetrics = async (
    targetPluginId: string | number,
    targetObjectId: string | number,
    metricsToPersist: BusinessMetricItem[],
    staleDeletes: CatalogMetricRef[] = [],
    mode: ScriptMetricPersistMode = SCRIPT_METRIC_PERSIST_MODE_ADD
  ) => {
    await persistScriptMetrics({
      pluginId: targetPluginId,
      objectId: targetObjectId,
      metrics: excludeSelfMonitorMetrics(metricsToPersist),
      staleDeletes,
      mode,
      client: { get, post, patch, t }
    });
  };

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
            updated[`${name}_warning`] = null;
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
      cloneDeep(form.getFieldsValue(true))
    );
    delete formValues.nodes;
    const rowValues = Object.keys(record)
      .filter(
        (key) =>
          key !== 'key' &&
          !key.endsWith('_error') &&
          !key.endsWith('_warning')
      )
      .reduce((acc, key) => {
        acc[key] = record[key];
        return acc;
      }, {} as Record<string, any>);
    const instance: Record<string, any> = fillOptionalFormFields(
      {
        ...formValues,
        ...rowValues,
        instance_type: configsInfo?.instance_type || formValues.instance_type,
        collect_type: configsInfo?.collect_type || formValues.collect_type,
        monitor_plugin_id: Number(pluginId) || formValues.monitor_plugin_id,
        plugin_id: formValues.plugin_id || pluginId
      },
      currentConfig?.form_fields
    );
    if (!instance.instance_id) {
      instance.instance_id =
        record.instance_id ||
        record.instance_name ||
        formValues.instance_id ||
        formValues.instance_name ||
        (record.key as string);
    }
    const nodeId = getRowNodeId(record);
    const selectedNode = nodeList.find(
      (node) =>
        String(node.id) === String(nodeId) || String(node.value) === String(nodeId)
    );
    if (selectedNode?.operating_system && !instance.operating_system) {
      instance.operating_system = selectedNode.operating_system;
    }
    return applyScriptCollectSubmit(instance, instance.collect_type);
  };

  const ensureCollectFormValid = async () => {
    try {
      await form.validateFields();
      return true;
    } catch (error: any) {
      const first = error?.errorFields?.[0]?.errors?.[0];
      if (first) {
        message.error(String(first));
      }
      return false;
    }
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
      ) : presentation.tone === 'warning' ? (
        <ExclamationCircleFilled className="text-[#faad14]" />
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
                      : presentation.tone === 'warning'
                        ? 'warning'
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
    retryCount = 0,
    maxRetries = 60,
    debugTimeout?: number
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
      updateCollectDetectState(rowKey, {
        ...task,
        fingerprint,
        started_at: (task as any).started_at,
        finished_at: (task as any).finished_at,
        debug_timeout: debugTimeout
      });
      if (['pending', 'running'].includes(task.status) && retryCount < maxRetries) {
        collectDetectTimersRef.current[rowKey] = setTimeout(() => {
          pollCollectDetectTask(
            rowKey,
            taskId,
            fingerprint,
            mode,
            retryCount + 1,
            maxRetries,
            debugTimeout
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

  const stopCollectDetectWait = (rowKey: string) => {
    if (collectDetectTimersRef.current[rowKey]) {
      clearTimeout(collectDetectTimersRef.current[rowKey]);
      delete collectDetectTimersRef.current[rowKey];
    }
    delete activeCollectDetectFingerprintRef.current[rowKey];
    setCollectDetectTasks((prev) => {
      const current = prev[rowKey];
      if (!current) {
        return prev;
      }
      return {
        ...prev,
        [rowKey]: {
          ...current,
          status: 'stopped',
          wait_stopped: true
        }
      };
    });
  };

  const cancelInFlightCollectDetectExcept = (keepKey: string) => {
    Object.keys(collectDetectTimersRef.current).forEach((key) => {
      if (key === keepKey) return;
      clearTimeout(collectDetectTimersRef.current[key]);
      delete collectDetectTimersRef.current[key];
    });
    Object.keys(activeCollectDetectFingerprintRef.current).forEach((key) => {
      if (key !== keepKey) {
        delete activeCollectDetectFingerprintRef.current[key];
      }
    });
    setCollectDetectTasks((prev) => {
      const runningKeys = Object.keys(prev).filter((key) => {
        if (key === keepKey) return false;
        const status = prev[key]?.status;
        return status === 'pending' || status === 'running';
      });
      if (!runningKeys.length) return prev;
      const next = { ...prev };
      runningKeys.forEach((key) => {
        delete next[key];
      });
      return next;
    });
  };

  const handleCollectDetect = async (
    record: IntegrationMonitoredObject,
    mode: CollectDetectMode = 'single'
  ) => {
    if (isScriptTemplate && mode === 'batch') {
      return;
    }
    const rowKey = record.key as string;
    setActiveTrialRowKey(rowKey);
    const nodeId = getRowNodeId(record);
    if (!nodeId) {
      message.warning(t('monitor.integrations.collectDetectNodeRequired'));
      return;
    }
    if (mode !== 'batch' && !(await ensureCollectFormValid())) {
      return;
    }
    const fingerprint = buildCollectDetectFingerprint(record);
    if (isScriptTemplate) {
      cancelInFlightCollectDetectExcept(rowKey);
    }
    activeCollectDetectFingerprintRef.current[rowKey] = fingerprint;
    const debugTimeout = isScriptTemplate
      ? resolveScriptTimeoutSeconds(
        form.getFieldValue('timeout'),
        form.getFieldValue('interval')
      )
      : 60;
    const maxRetries = isScriptTemplate
      ? Math.max(
        1,
        Math.ceil(
          ((debugTimeout + SCRIPT_DETECT_TIMEOUT_MARGIN_SECONDS) * 1000) / 2000
        ) + 2
      )
      : 60;
    updateCollectDetectState(rowKey, {
      status: 'running',
      fingerprint,
      debug_timeout: debugTimeout
    });
    try {
      const data = (await createCollectDetectTask({
        monitor_plugin_id: Number(pluginId),
        monitor_object_id: Number(objectId),
        node_id: nodeId,
        instance_key: record.instance_id || record.instance_name || rowKey,
        instance: buildDetectInstance(record),
        timeout: debugTimeout
      })) as { task_id: React.Key };
      pollCollectDetectTask(
        rowKey,
        data.task_id,
        fingerprint,
        mode,
        0,
        maxRetries,
        debugTimeout
      );
    } catch (error: any) {
      const status = error?.response?.status;
      const respMsg = error?.response?.data?.message || error?.message || '';
      let warningType: 'no_permission' | 'rate_limit' | undefined;
      if (
        status === 429 ||
        respMsg.includes('频繁') ||
        respMsg.includes('throttle') ||
        respMsg.includes('Throttled')
      ) {
        warningType = 'rate_limit';
      } else if (
        status === 403 ||
        respMsg.includes('无权') ||
        respMsg.includes('权限') ||
        respMsg.includes('permission') ||
        respMsg.includes('Unauthorized')
      ) {
        warningType = 'no_permission';
      }
      updateCollectDetectState(rowKey, {
        status: warningType ? 'warning' : 'failed',
        fingerprint,
        warning_type: warningType,
        error_message: warningType === 'rate_limit'
          ? t('monitor.integrations.trialRunRateLimit', '调试过于频繁，请稍后重试')
          : warningType === 'no_permission'
            ? t('monitor.integrations.trialRunNoPermission', '当前账号无权调试该对象/节点')
            : respMsg || t('common.operationFailed')
      });
    }
  };

  const handleBatchCollectDetect = async () => {
    if (isScriptTemplate) {
      return;
    }
    const selectedRows = getRowsForBatchCollectDetect(
      dataSource,
      selectedRowKeys
    );
    const runnableRows = selectedRows.filter((row) => getRowNodeId(row));
    if (!runnableRows.length) {
      message.warning(t('monitor.integrations.collectDetectNodeRequired'));
      return;
    }
    if (!(await ensureCollectFormValid())) {
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
      return (
        <Tag>
          {isScriptTemplate
            ? t('monitor.integrations.scriptCollectUntested', '未调试')
            : t('monitor.integrations.collectDetectUntested')}
        </Tag>
      );
    }
    const clickableClassName = 'cursor-pointer';
    if (task.status === 'warning') {
      return (
        <Tag
          color="warning"
          className={clickableClassName}
          onClick={() => {
            setActiveTrialRowKey(record.key as string);
            if (!isScriptTemplate) showCollectDetectResult(task);
          }}
        >
          {t('monitor.integrations.trialRunWarning', '警告')}
        </Tag>
      );
    }
    if (['pending', 'running'].includes(task.status)) {
      return (
        <Tag
          color="processing"
          className={clickableClassName}
          onClick={() => {
            setActiveTrialRowKey(record.key as string);
            if (!isScriptTemplate) showCollectDetectResult(task);
          }}
        >
          {isScriptTemplate
            ? t('monitor.integrations.scriptCollectRunning', '调试中')
            : t('monitor.integrations.collectDetectRunning')}
        </Tag>
      );
    }
    return task.status === 'success' ? (
      <Tag
        color="success"
        className={clickableClassName}
        onClick={() => {
          setActiveTrialRowKey(record.key as string);
          if (!isScriptTemplate) showCollectDetectResult(task);
        }}
      >
        {t('monitor.integrations.collectDetectSuccess')}
      </Tag>
    ) : (
      <Tag
        color="error"
        className={clickableClassName}
        onClick={() => {
          setActiveTrialRowKey(record.key as string);
          if (!isScriptTemplate) showCollectDetectResult(task);
        }}
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
              onClick={() => {
                setActiveTrialRowKey(record.key as string);
                handleCollectDetect(record);
              }}
            >
              {isScriptTemplate
                ? t('monitor.integrations.trialRun', '调试')
                : t('monitor.integrations.collectDetect')}
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
          title: isScriptTemplate
            ? t('monitor.integrations.scriptCollectStatus', '调试状态')
            : t('monitor.integrations.collectDetectStatus'),
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
    collectDetectTasks,
    isScriptTemplate
  ]);

  const pluginFormCacheKey = [
    pluginId,
    currentConfig?.collect_type || '',
    JSON.stringify(currentConfig?.form_fields ?? null),
    nodeList.map((node) => node.id || node.value).join(',')
  ].join('|');
  const cachedPluginFormRef = useRef<{ key: string; items: React.ReactNode }>({
    key: '',
    items: null
  });
  if (!pluginId) {
    cachedPluginFormRef.current = { key: '', items: null };
  } else if (cachedPluginFormRef.current.key !== pluginFormCacheKey) {
    cachedPluginFormRef.current = {
      key: formConfig?.formItems ? pluginFormCacheKey : '',
      items: formConfig?.formItems || null
    };
  }
  const formItems = cachedPluginFormRef.current.items;
  const visibleFormItems =
    !isScriptTemplate || scriptValuesApplied ? formItems : null;

  useEffect(() => {
    if (isLoading) return;
    getNodeList();
  }, [isLoading]);

  useEffect(() => {
    hasInitializedFormRef.current = false;
    setStoredScriptForm(undefined);
    setScriptValuesApplied(false);
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
    if (isScriptTemplate && storedScriptForm === undefined) return;
    if (!hasInitializedFormRef.current) {
      const initialValues = applyIfmibDeploymentState(
        {
          ...defaults,
          ...(storedScriptForm || {})
        },
        enableIfmibFromUrl
      );
      form.setFieldsValue(initialValues);
      trackSnmpFilterMutexLastChanged({}, form.getFieldsValue(true), form);
      hasInitializedFormRef.current = true;
      if (isScriptTemplate) {
        setScriptValuesApplied(true);
      }
    } else if (isScriptTemplate && storedScriptForm) {
      if (!scriptValuesApplied) {
        form.setFieldsValue(storedScriptForm);
        setScriptValuesApplied(true);
      } else if (storedScriptForm.script) {
        const currentScript = form.getFieldValue('script');
        if (currentScript === undefined || currentScript === null || currentScript === '') {
          form.setFieldValue('script', storedScriptForm.script);
        }
      }
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
        ...(storedScriptForm || {}),
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
  }, [
    configLoading,
    defaultFormKey,
    enableIfmibFromUrl,
    form,
    isScriptTemplate,
    scriptValuesApplied,
    storedScriptForm
  ]);

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
    ...(supportCollectDetect && !isScriptTemplate
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
          [`${name}_error`]: null,
          [`${name}_warning`]: null
        };
      });
    });
    // 验证所有字段
    visibleTableColumns.forEach((column: any) => {
      const { name, rules = [], required = false } = column;
      normalizedData.forEach((row, index) => {
        const value = row[name];
        let errorMsg: string | null = null;
        let warningMsg: string | null = null;
        // 如果字段标记为required，进行必填验证
        if (required) {
          if (
            value === undefined ||
            value === null ||
            value === '' ||
            (typeof value === 'string' && !value.trim()) ||
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
                  const msg = rule.message || t('common.required');
                  if (rule.warningOnly) {
                    warningMsg = warningMsg || msg;
                  } else {
                    errorMsg = msg;
                    break;
                  }
                }
              }
            }
          }
        }
        if (errorMsg || warningMsg) {
          if (errorMsg) {
            hasError = true;
          }
          newData[index] = {
            ...newData[index],
            [`${name}_error`]: errorMsg,
            [`${name}_warning`]: warningMsg
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
    if (
      policyTemplatesLoading ||
      confirmLoading ||
      saveInFlightRef.current ||
      scriptWriteChoice
    ) {
      return;
    }
    if (isScriptTemplate && scriptCatalogBlocking) {
      return;
    }
    if (isScriptTemplate && hasReservedScriptError) {
      return;
    }
    if (isScriptTemplate && scriptTrialBlocksMetricActions(activeTrialTask)) {
      return;
    }
    if (
      isScriptTemplate &&
      scriptDebugHasBusinessMetrics &&
      !selectedScriptMetrics.length
    ) {
      message.warning(goEditSelectFirstText);
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
    form.validateFields().then(async (values) => {
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
        const pushAlertCenter = Boolean(
          values[COLLECTION_POLICY_ALERT_CENTER_FIELD]
        );
        const alertCenterChannelIds = pickAlertCenterChannelIds(
          alertCenterChannels
        );
        if (pushAlertCenter && templatesToApply.length && !alertCenterChannelIds.length) {
          message.error(
            t(
              'monitor.integrations.pushToAlertCenterMissing',
              '未找到告警中心 NATS 通道，请先在系统管理中配置'
            )
          );
          return;
        }
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
        if (
          isScriptTemplate &&
          scriptDebugHasBusinessMetrics &&
          selectedScriptMetrics.length > 0
        ) {
          const persistable = excludeSelfMonitorMetrics(selectedScriptMetrics);
          const existing = await listPluginCatalogMetrics({
            pluginId,
            objectId,
            client: { get }
          });
          const staleDeletes = planScriptMetricHardSyncDeletes(
            existing,
            persistable
          );
          setDuplicateDisplayNameWarning(
            findDuplicateDisplayNames(persistable, existing)
          );
          setScriptWriteMode(SCRIPT_METRIC_PERSIST_MODE_ADD);
          setScriptWriteChoice({
            params,
            templatesToApply,
            namePrefix: values[COLLECTION_POLICY_NAME_PREFIX_FIELD],
            pushAlertCenter,
            alertCenterChannelIds,
            staleDeletes
          });
          return;
        }
        addNodesConfig(
          params,
          templatesToApply,
          values[COLLECTION_POLICY_NAME_PREFIX_FIELD],
          pushAlertCenter,
          alertCenterChannelIds,
          [],
          SCRIPT_METRIC_PERSIST_MODE_ADD
        );
      } catch (error: any) {
        message.error(error?.message || t('common.operationFailed'));
      }
    });
  };

  const addNodesConfig = async (
    params: Record<string, any> = {},
    templatesToApply: PolicyTemplateItem[] = [],
    namePrefix?: string,
    pushAlertCenter = false,
    alertCenterChannelIds: Array<string | number> = [],
    staleDeletes: CatalogMetricRef[] = [],
    persistMode: ScriptMetricPersistMode = SCRIPT_METRIC_PERSIST_MODE_ADD
  ) => {
    if (saveInFlightRef.current) {
      return;
    }
    saveInFlightRef.current = true;
    try {
      setConfirmLoading(true);
      const collectResult = await updateNodeChildConfig(params);
      let didPersistMetrics = false;
      if (
        isScriptTemplate &&
        scriptDebugHasBusinessMetrics &&
        selectedScriptMetrics.length > 0
      ) {
        await persistSelectedScriptMetrics(
          pluginId,
          objectId,
          excludeSelfMonitorMetrics(selectedScriptMetrics),
          staleDeletes,
          persistMode
        );
        didPersistMetrics = true;
      }
      const goIntegrationList = () => {
        const nextSearch = new URLSearchParams({
          objId: objectId
        });
        router.push(`/monitor/integration/list?${nextSearch.toString()}`);
      };
      const goPersistedMetrics = () => {
        const payload = buildScriptMetricEditCarry(selectedScriptMetrics);
        if (payload.metrics.length) {
          writeScriptMetricEditCarry(objectId, pluginId, payload);
        }
        const metricSearch = new URLSearchParams(searchParams.toString());
        metricSearch.set(SCRIPT_METRIC_DRAFT_QUERY, '1');
        router.push(
          `/monitor/integration/list/detail/metric?${metricSearch.toString()}`
        );
      };
      if (templatesToApply.length) {
        const policyPayload = buildCollectionPolicyApplyPayload({
          monitorObjectId: objectId,
          templates: templatesToApply,
          instanceIds: extractCollectInstanceIds(collectResult, params),
          namePrefix,
          pushAlertCenter,
          alertCenterChannelIds
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
      } else if (didPersistMetrics) {
        message.success(
          t('monitor.integrations.scriptMetricsPersistSuccess', '指标已保存')
        );
      } else {
        message.success(t('common.addSuccess'));
      }
      if (didPersistMetrics) {
        goPersistedMetrics();
      } else {
        goIntegrationList();
      }
    } catch (error: any) {
      const errorText =
        error?.response?.data?.message ||
        error?.message ||
        t('common.operationFailed');
      if (
        typeof errorText === 'string' &&
        (errorText.includes(reservedTagRenameText) ||
          errorText.includes(reservedMetricIdText))
      ) {
        return;
      }
      if (
        isScriptTemplate &&
        typeof errorText === 'string' &&
        errorText.includes('已存在采集配置')
      ) {
        message.warning(
          t(
            'monitor.integrations.scriptCollectConfigExistsUpdating',
            '该实例已有脚本采集配置，将更新现有配置'
          )
        );
        return;
      }
      message.error(errorText);
    } finally {
      saveInFlightRef.current = false;
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
      initialValues={{
        [COLLECTION_POLICY_NAME_PREFIX_FIELD]: t(
          'monitor.integrations.collectionNamePrefixDefault',
          '接入批量'
        ),
        [COLLECTION_POLICY_ALERT_CENTER_FIELD]: false
      }}
      onValuesChange={(changed, all) => {
        const changedKeys = Object.keys(changed);
        const isPolicyUiOnlyChange =
          changedKeys.length > 0 &&
          changedKeys.every((key) => isCollectionPolicyUiField(key));
        if (!isPolicyUiOnlyChange) {
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
        if (Object.prototype.hasOwnProperty.call(changed, 'script_os')) {
          syncScriptRunAsForOs(form, String(changed.script_os ?? ''));
        }
        if (
          Object.prototype.hasOwnProperty.call(
            changed,
            COLLECTION_POLICY_FIELD
          ) ||
          Object.prototype.hasOwnProperty.call(
            changed,
            COLLECTION_POLICY_ALERT_CENTER_FIELD
          )
        ) {
          const habitKey = collectionPolicyHabitKey(pluginId);
          if (habitKey) {
            saveUserHabit(
              habitKey,
              collectionPolicyHabitValue(
                all[COLLECTION_POLICY_FIELD],
                all[COLLECTION_POLICY_ALERT_CENTER_FIELD]
              )
            ).catch(() => undefined);
          }
        }
      }}
    >
      <div className="flex items-center justify-between mb-[10px]">
        <b className="text-[14px] ml-[-10px]">
          {t('monitor.integrations.configuration')}
        </b>
        <GuideEntryButton />
      </div>
      {visibleFormItems}
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
          showSearch
          optionFilterProp="label"
          maxTagCount="responsive"
          loading={policyTemplatesLoading}
          options={policyTemplateSelectOptions(policyTemplates, {
            builtin: t('monitor.events.templateTypeBuiltin', '内置'),
            custom: t('monitor.events.templateTypeCustom', '自定义')
          })}
          placeholder={t(
            'monitor.integrations.monitoringPolicyPlaceholder'
          )}
          style={{ width: COLLECTION_POLICY_CONTROL_WIDTH }}
        />
      </Form.Item>
      <Form.Item
        noStyle
        shouldUpdate={(prev, next) =>
          prev[COLLECTION_POLICY_FIELD] !== next[COLLECTION_POLICY_FIELD]
        }
      >
        {() => {
          const selectedKeys = form.getFieldValue(COLLECTION_POLICY_FIELD);
          const hasSelectedTemplates =
            Array.isArray(selectedKeys) && selectedKeys.length > 0;
          return (
            <Form.Item
              name={COLLECTION_POLICY_NAME_PREFIX_FIELD}
              label={t('monitor.events.namePrefix', '策略名称前缀')}
              rules={
                hasSelectedTemplates
                  ? [
                    {
                      required: true,
                      message: t(
                        'monitor.events.namePrefixRequired',
                        '请输入策略名称前缀'
                      )
                    }
                  ]
                  : []
              }
            >
              <Input
                placeholder={t(
                  'monitor.events.namePrefixPlaceholder',
                  '例如：生产环境-'
                )}
                style={{ width: COLLECTION_POLICY_CONTROL_WIDTH }}
              />
            </Form.Item>
          );
        }}
      </Form.Item>
      <Form.Item
        name={COLLECTION_POLICY_ALERT_CENTER_FIELD}
        valuePropName="checked"
        label={
          <span className="inline-flex items-center">
            {t('monitor.integrations.pushToAlertCenter', '推送告警中心')}
            <FieldGuideTip
              short={t('monitor.integrations.pushToAlertCenterDes')}
              title={t('monitor.integrations.fieldGuideTip')}
            />
          </span>
        }
      >
        <Switch />
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
          scroll={{ x: 'max-content' }}
          dataSource={dataSource}
          columns={columns}
          rowKey="key"
          pagination={false}
          rowSelection={rowSelection}
        />
      </Form.Item>
      {isScriptTemplate && (
        <ScriptTrialRunArea
          task={activeTrialTask}
          spinning={['pending', 'running'].includes(activeTrialTask?.status || '')}
          onTrialRun={() => {
            const target =
              dataSource.find((row) => row.key === activeTrialRowKey) ||
              dataSource[0];
            if (target) {
              setActiveTrialRowKey(target.key as string);
              handleCollectDetect(target);
            }
          }}
          onStopWaiting={() => {
            const rowKey = (activeRecord?.key || activeTrialRowKey) as string;
            if (rowKey) {
              stopCollectDetectWait(rowKey);
            }
          }}
          timeoutSeconds={
            activeTrialTask?.debug_timeout ??
            resolveScriptTimeoutSeconds(
              form.getFieldValue('timeout'),
              form.getFieldValue('interval')
            )
          }
          nodeSelected={Boolean(getRowNodeId(activeRecord || {}))}
          instanceName={activeTrialInstanceName}
          pluginId={pluginId}
          objectId={objectId}
          onSelectedMetricsChange={handleSelectedScriptMetricsChange}
          onBusinessMetricsAvailableChange={handleBusinessMetricsAvailableChange}
          onCatalogBlockingChange={setScriptCatalogBlocking}
          onCatalogErrorChange={setScriptCatalogError}
        />
      )}
      <Form.Item>
        <div className="flex flex-wrap items-center gap-3">
          <Permission requiredPermissions={['Add']}>
            <Tooltip
              title={
                scriptCatalogError
                  ? t(
                    'monitor.integrations.scriptCatalogLoadFailed',
                    '指标目录加载失败，暂无法确认写入'
                  )
                  : undefined
              }
            >
              <span className="inline-block">
                <Button
                  type="primary"
                  loading={confirmLoading}
                  disabled={
                    confirmLoading ||
                    isAnyTrialRunning ||
                    hasReservedScriptError ||
                    scriptTrialFailed ||
                    scriptCatalogBlocking
                  }
                  onClick={handleSave}
                >
                  {t('common.confirm')}
                </Button>
              </span>
            </Tooltip>
          </Permission>
          {hasReservedScriptTagError && (
            <span
              className="text-[13px] text-[var(--color-fail)]"
              role="alert"
            >
              {reservedTagRenameText}
            </span>
          )}
          {showSelectMetricsFirst && (
            <span
              className="text-[13px] text-[var(--color-fail)]"
              role="alert"
            >
              {goEditSelectFirstText}
            </span>
          )}
        </div>
      </Form.Item>
    </Form>
  );

  const scriptWriteDeleteNames = (scriptWriteChoice?.staleDeletes || [])
    .map((item) => catalogMetricRefLabel(item))
    .filter(Boolean);

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
      <Modal
        title={t('monitor.integrations.scriptMetricsWriteTitle', '确认写入指标')}
        open={Boolean(scriptWriteChoice)}
        width={560}
        centered
        destroyOnHidden
        maskClosable={!confirmLoading}
        confirmLoading={confirmLoading}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onCancel={() => {
          if (confirmLoading) return;
          setScriptWriteChoice(null);
        }}
        onOk={() => {
          const choice = scriptWriteChoice;
          if (!choice || confirmLoading || saveInFlightRef.current) return;
          const staleDeletes =
            scriptWriteMode === SCRIPT_METRIC_PERSIST_MODE_OVERWRITE
              ? choice.staleDeletes
              : [];
          setScriptWriteChoice(null);
          void addNodesConfig(
            choice.params,
            choice.templatesToApply,
            choice.namePrefix,
            choice.pushAlertCenter,
            choice.alertCenterChannelIds,
            staleDeletes,
            scriptWriteMode
          );
        }}
      >
        <Radio.Group
          className="flex w-full flex-col gap-3"
          value={scriptWriteMode}
          onChange={(event) =>
            setScriptWriteMode(event.target.value as ScriptMetricWriteMode)
          }
        >
          <Radio value={SCRIPT_METRIC_PERSIST_MODE_ADD} className="whitespace-normal">
            {t(
              'monitor.integrations.scriptMetricsWriteAppend',
              '仅新增：写入本次勾选指标，不删除目录中的旧指标'
            )}
          </Radio>
          <Radio
            value={SCRIPT_METRIC_PERSIST_MODE_OVERWRITE}
            className="whitespace-normal"
          >
            {t(
              'monitor.integrations.scriptMetricsWriteOverwrite',
              '覆盖：写入本次勾选，并删除本次选择中未出现的旧指标'
            )}
          </Radio>
        </Radio.Group>
        {duplicateDisplayNameWarning.length > 0 ? (
          <p className="mb-0 mt-3 text-[13px] text-[var(--color-warning)]">
            {t(
              'monitor.integrations.duplicateDisplayName',
              '展示名称与已有指标重复'
            )}
            ：{duplicateDisplayNameWarning.join('、')}
          </p>
        ) : null}
        {scriptWriteMode === SCRIPT_METRIC_PERSIST_MODE_OVERWRITE ? (
          <div className="mt-3">
            {scriptWriteDeleteNames.length > 0 ? (
              <ScriptMetricOverwriteContent
                names={scriptWriteDeleteNames}
                summary={t(
                  'monitor.integrations.scriptMetricsHardSyncHint',
                  '将删除本插件目录中、本次选择里没有的旧指标，共 {count} 个。',
                  { count: scriptWriteDeleteNames.length }
                )}
                cancelHint={t(
                  'monitor.integrations.scriptMetricsHardSyncCancel',
                  '取消则中止本次确认。'
                )}
                expandLabel={t(
                  'monitor.integrations.scriptMetricsHardSyncMore',
                  '展开全部（共 {count} 个）',
                  { count: scriptWriteDeleteNames.length }
                )}
                collapseLabel={t(
                  'monitor.integrations.scriptMetricsHardSyncCollapse',
                  '收起'
                )}
              />
            ) : (
              <div className="space-y-2 text-[13px] text-[var(--color-text-3)]">
                <p className="mb-0">
                  {t(
                    'monitor.integrations.scriptMetricsWriteOverwriteEmpty',
                    '没有需要删除的旧指标。'
                  )}
                </p>
                <p className="mb-0">
                  {t(
                    'monitor.integrations.scriptMetricsHardSyncCancel',
                    '取消则中止本次确认。'
                  )}
                </p>
              </div>
            )}
          </div>
        ) : (
          <p className="mb-0 mt-3 text-[13px] text-[var(--color-text-3)]">
            {t(
              'monitor.integrations.scriptMetricsHardSyncCancel',
              '取消则中止本次确认。'
            )}
          </p>
        )}
      </Modal>
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
