'use client';
import { useEffect, useMemo, useState, useRef } from 'react';
import { Spin, Button, Form, Input, message, Steps } from 'antd';
import useApiClient from '@/utils/request';
import OperateModal from '@/components/operate-modal';
import useMonitorApi from '@/app/monitor/api';
import {
  fetchAllMetricsGroups,
  fetchAllMonitorMetrics
} from '@/app/monitor/api/fetchMetricCatalogPages';
import useEventApi from '@/app/monitor/api/event';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  UserItem,
  SegmentedItem,
  TableDataItem,
  ObjectItem,
  MetricItem,
  IndexViewItem,
  ThresholdField,
  FilterItem
} from '@/app/monitor/types';
import {
  PluginItem,
  SourceFeild,
  StrategyFields,
  ChannelItem
} from '@/app/monitor/types/event';
import { useCommon } from '@/app/monitor/context/common';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import strategyStyle from '../index.module.scss';
import { ArrowLeftOutlined } from '@ant-design/icons';
import SelectAssets from '../selectAssets';
import { useSearchParams, useRouter } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import { cloneDeep } from 'lodash';
import BasicInfoForm, { BasicInfoFormRef } from './basicInfoForm';
import MetricDefinitionForm from './metricDefinitionForm';
import AlertConditionsForm from './alertConditionsForm';
import NotificationForm from './notificationForm';
import MetricPreview from './metricPreview';
import VariablesTable from './variablesTable';
import { isStringArray } from '@/app/monitor/utils/common';
import { loadMonitorPluginsByObjectCached } from '@/app/monitor/utils/monitorPluginCache';
import {
  getMetricDimensionNames,
  sanitizeGroupBy
} from '@/app/monitor/utils/metricDimensions';
import {
  COMPARISON_METHOD,
  ENUM_COMPARISON_METHOD
} from '@/app/monitor/constants/event';
import {
  buildMetricUnitCascaderOptions,
  getCalculationUnitOnMetricRowsChange,
  getReverseModeCalculationUnit,
  getThresholdUnitOnCalculationUnitChange,
  pruneNoticeUsers,
  shouldRequireNoticeUsers,
  resolveEffectiveCalculationUnit,
  resolveInitialMetricPluginId,
  resolveThresholdUnit,
  resolveUnitOnMetricSelect,
  restoreCalculationUnitState,
  scaleThresholdValuesForUnitChange
} from './strategyDetailUtils';
import { MetricExpressionRow } from './metricExpressionTypes';
import {
  buildMetricExpressionQueryCondition,
  createMetricRow,
  DEFAULT_FORMULA_EXPRESSION,
  DEFAULT_FORMULA_RESULT_NAME,
  getMetricExpressionModeForRows,
  MetricExpressionMode,
  resolveMetricExpressionUnits,
  toMetricExpressionStateFromQueryCondition
} from './formulaExpressionUtils';
const defaultGroup = ['instance_id'];

const StrategyOperation = () => {
  const { t } = useTranslation();
  const translateWithFallback = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { post, put, isLoading } = useApiClient();
  const {
    getMetricsGroup,
    getMonitorMetrics,
    getMonitorPlugin,
    getMonitorObject,
    getAllUsers
  } = useMonitorApi();
  const { getMonitorPolicy, getSystemChannelList, savePolicyTemplate } = useEventApi();
  const commonContext = useCommon();
  const unitList = commonContext?.unitList || [];
  const groupedUnitOptions = useMemo(
    () => buildMetricUnitCascaderOptions(commonContext?.groupedUnitList || []),
    [commonContext?.groupedUnitList]
  );
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const router = useRouter();
  const organizations = Form.useWatch('organizations', form);
  const [noticeUserList, setNoticeUserList] = useState<UserItem[]>([]);
  const [noticeUserLoadKey, setNoticeUserLoadKey] = useState('');
  const organizationKey = useMemo(() => {
    return (Array.isArray(organizations) ? organizations : [])
      .map((item) => Number(item))
      .filter((item) => Number.isFinite(item) && item > 0)
      .sort((a, b) => a - b)
      .join(',');
  }, [organizations]);
  const instRef = useRef<ModalRef>(null);
  const formContainerRef = useRef<HTMLDivElement>(null);
  const basicInfoRef = useRef<HTMLDivElement>(null);
  const basicInfoFormRef = useRef<BasicInfoFormRef>(null);
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const monitorObjId = searchParams.get('monitorObjId');
  const monitorName = searchParams.get('monitorName');
  const type = searchParams.get('type') || '';
  const detailId = searchParams.get('id');
  const detailName = searchParams.get('name') || '--';
  const isCreateFlow = ['builtIn', 'add'].includes(type);
  const { getGroupIds, ready: objectConfigReady } = useObjectConfigInfo(monitorName);
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [templateSaving, setTemplateSaving] = useState<boolean>(false);
  const [templateSavedOnce, setTemplateSavedOnce] = useState(false);
  const [templateConfirmVisible, setTemplateConfirmVisible] = useState(false);
  const [templateMetaDefaults, setTemplateMetaDefaults] = useState({
    name: '',
    description: '',
  });
  const [templateMetaForm] = Form.useForm<{ name: string; description: string }>();
  const pendingTemplateConfigRef = useRef<StrategyFields | null>(null);
  const templateSubmittingRef = useRef(false);
  // create 流程：从当前页面“保存模版”成功后，只允许创建 1 次（需要重新进入页面才能再创建）。
  // 用 ref 做同步锁，避免后端请求已完成但弹窗尚未完全关闭前出现重复请求。
  const templateSavedOnceRef = useRef(false);

  useEffect(() => {
    if (!templateConfirmVisible) return;
    templateMetaForm.setFieldsValue(templateMetaDefaults);
  }, [templateConfirmVisible, templateMetaDefaults, templateMetaForm]);
  const [source, setSource] = useState<SourceFeild>({
    type: '',
    values: []
  });
  const [metric, setMetric] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [metricsLoading, setMetricsLoading] = useState<boolean>(false);
  const [unit, setUnit] = useState<string>('min');
  const [periodUnit, setPeriodUnit] = useState<string>('min');
  const [nodataUnit, setNodataUnit] = useState<string>('min');
  const [noDataRecoveryUnit, setNoDataRecoveryUnit] = useState<string>('min');
  const [conditions, setConditions] = useState<FilterItem[]>([]);
  const [metricRows, setMetricRows] = useState<MetricExpressionRow[]>([
    createMetricRow(0)
  ]);
  const [metricExpressionMode, setMetricExpressionMode] =
    useState<MetricExpressionMode>('metric');
  const [formulaResultName, setFormulaResultName] = useState<string>(
    () =>
      translateWithFallback(
        'monitor.events.formulaDefaultResultName',
        DEFAULT_FORMULA_RESULT_NAME
      )
  );
  const [formulaExpression, setFormulaExpression] =
    useState<string>(DEFAULT_FORMULA_EXPRESSION);
  const [labelsByRef, setLabelsByRef] = useState<Record<string, string[]>>({});
  const [noDataAlert, setNoDataAlert] = useState<number | null>(null);
  const [noDataRecovery, setNoDataRecovery] = useState<number | null>(null);
  const [noDataAlertLevel, setNoDataAlertLevel] = useState<string>('none');
  const [noDataAlertName, setNoDataAlertName] = useState<string>('');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const currentMonitorObject = useMemo(
    () =>
      objects.find((item) => String(item.id) === String(monitorObjId)),
    [objects, monitorObjId]
  );
  const [groupBy, setGroupBy] = useState<string[]>(
    getGroupIds(monitorName as string)?.default || defaultGroup
  );

  useEffect(() => {
    if (!objectConfigReady || !monitorName) return;
    const defaults = getGroupIds(monitorName)?.default;
    if (defaults?.length) {
      setGroupBy((prev) => (prev === defaultGroup || prev.length === 0 ? defaults : prev));
    }
  }, [objectConfigReady, monitorName, getGroupIds]);
  const [groupAlgorithm, setGroupAlgorithm] = useState<string | null>('avg');
  const [period, setPeriod] = useState<number | null>(null);
  const [algorithm, setAlgorithm] = useState<string | null>(null);
  const [formData, setFormData] = useState<StrategyFields>({
    threshold: [],
    source: { type: '', values: [] }
  });
  const [threshold, setThreshold] = useState<ThresholdField[]>([
    {
      level: 'critical',
      method: '>',
      value: null
    },
    {
      level: 'error',
      method: '>',
      value: null
    },
    {
      level: 'warning',
      method: '>',
      value: null
    }
  ]);
  const [calculationUnit, setCalculationUnit] = useState<string | null>(null);
  const [thresholdUnit, setThresholdUnit] = useState<string | null>(null);
  const [pluginList, setPluginList] = useState<SegmentedItem[]>([]);
  const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>([]);
  const [initMetricData, setInitMetricData] = useState<MetricItem[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [enableAlerts, setEnableAlerts] = useState<string[]>(['threshold']);
  const initialMetricPluginIdRef = useRef<string | number | undefined>(undefined);
  const effectiveCalculationUnit = resolveEffectiveCalculationUnit({
    isFormulaMode: metricExpressionMode === 'formula',
    unit: calculationUnit,
    unitList
  });
  const effectiveThresholdUnit = resolveThresholdUnit({
    thresholdUnit,
    calculationUnit: effectiveCalculationUnit,
    unitList
  });

  useEffect(() => {
    if (!unitList.length) return;
    setThresholdUnit((current) =>
      getThresholdUnitOnCalculationUnitChange({
        thresholdUnit: current,
        calculationUnit: effectiveCalculationUnit,
        unitList
      })
    );
  }, [effectiveCalculationUnit, unitList]);

  useEffect(() => {
    if (!isLoading) {
      initialMetricPluginIdRef.current = undefined;
      setPageLoading(true);
      Promise.all([
        getPlugins(),
        getChannelList(),
        getObjects(),
        detailId && getStragyDetail()
      ]).finally(() => {
        setPageLoading(false);
      });
    }
  }, [isLoading]);

  // 通知人候选按策略所属组织渲染；组织变更后自动剔除越界已选通知人
  useEffect(() => {
    const applyPrunedNoticeUsers = (
      pruned: Array<string | number>
    ) => {
      form.setFieldValue('notice_users', pruned);
      // 开启通知且渠道需要通知人时，清空后立即触发校验，阻止带着空通知人保存
      if (
        shouldRequireNoticeUsers({
          notice: form.getFieldValue('notice'),
          noticeTypeIds: form.getFieldValue('notice_type_ids') || [],
          channelList
        }) &&
        pruned.length === 0
      ) {
        Promise.resolve().then(() => {
          form.validateFields(['notice_users']).catch(() => undefined);
        });
      }
    };

    const orgIds = organizationKey
      ? organizationKey.split(',').map((item) => Number(item))
      : [];

    if (!orgIds.length) {
      setNoticeUserList([]);
      setNoticeUserLoadKey('');
      const current = form.getFieldValue('notice_users') || [];
      if (Array.isArray(current) && current.length) {
        applyPrunedNoticeUsers([]);
      } else if (
        shouldRequireNoticeUsers({
          notice: form.getFieldValue('notice'),
          noticeTypeIds: form.getFieldValue('notice_type_ids') || [],
          channelList
        })
      ) {
        Promise.resolve().then(() => {
          form.validateFields(['notice_users']).catch(() => undefined);
        });
      }
      return;
    }

    let cancelled = false;
    getAllUsers(orgIds)
      .then((users) => {
        if (cancelled) return;
        const list = Array.isArray(users) ? users : [];
        setNoticeUserList(list);
        setNoticeUserLoadKey(organizationKey);
        const current = form.getFieldValue('notice_users') || [];
        const pruned = pruneNoticeUsers(current, list);
        if (
          Array.isArray(current) &&
          (pruned.length !== current.length ||
            pruned.some(
              (item, index) => String(item) !== String(current[index])
            ))
        ) {
          applyPrunedNoticeUsers(pruned);
        } else if (
          pruned.length === 0 &&
          shouldRequireNoticeUsers({
            notice: form.getFieldValue('notice'),
            noticeTypeIds: form.getFieldValue('notice_type_ids') || [],
            channelList
          })
        ) {
          Promise.resolve().then(() => {
            form.validateFields(['notice_users']).catch(() => undefined);
          });
        }
      })
      .catch(() => {
        // 拉取失败时不改动已选通知人，避免误清空
      });

    return () => {
      cancelled = true;
    };
  }, [organizationKey, form, channelList]);

  // dealDetail 可能再次用详情里的 notice_users 覆盖表单，候选就绪后需再裁一次
  useEffect(() => {
    if (!organizationKey || noticeUserLoadKey !== organizationKey) {
      return;
    }
    const current = form.getFieldValue('notice_users') || [];
    const pruned = pruneNoticeUsers(current, noticeUserList);
    if (
      Array.isArray(current) &&
      (pruned.length !== current.length ||
        pruned.some((item, index) => String(item) !== String(current[index])))
    ) {
      form.setFieldValue('notice_users', pruned);
      if (
        shouldRequireNoticeUsers({
          notice: form.getFieldValue('notice'),
          noticeTypeIds: form.getFieldValue('notice_type_ids') || [],
          channelList
        }) &&
        pruned.length === 0
      ) {
        Promise.resolve().then(() => {
          form.validateFields(['notice_users']).catch(() => undefined);
        });
      }
    }
  }, [formData, noticeUserList, noticeUserLoadKey, organizationKey, form, channelList]);

  useEffect(() => {
    form.resetFields();
    if (['builtIn', 'add'].includes(type)) {
      const strategyInfo = JSON.parse(
        sessionStorage.getItem('strategyInfo') || '{}'
      );
      const channelItem = channelList[0];
      const initForm: TableDataItem = {
        organizations: groupId,
        notice_type_ids: channelItem ? [channelItem.id] : [],
        notice_type: channelItem?.channel_type,
        notice: false,
        period: 5,
        schedule: 5,
        trigger_count: 1,
        recovery_condition: 5,
        collect_type: pluginList[0]?.value,
        group_algorithm: 'avg',
        algorithm: 'avg_over_time'
      };
      let _metricId = searchParams.get('metricId') || null;
      if (type === 'builtIn') {
        ['name', 'alert_name', 'group_algorithm', 'algorithm'].forEach((item) => {
          initForm[item] = strategyInfo[item] || initForm[item] || null;
        });
        feedbackThreshold(strategyInfo.threshold || []);
        _metricId = strategyInfo.metric_name || null;
      }
      // 设置无数据告警名称默认值
      const defaultNoDataAlertName = t('monitor.events.noDataAlertNameDefault');
      setNoDataAlertName(defaultNoDataAlertName);
      // 设置汇聚方式默认值
      setGroupAlgorithm(initForm.group_algorithm || 'avg');
      setAlgorithm(initForm.algorithm || 'avg_over_time');
      // 设置无数据告警默认值为5分钟
      setNoDataAlert(5);
      form.setFieldsValue({
        ...initForm,
        no_data_alert_name: defaultNoDataAlertName
      });
      // 只有在指标数据加载完成后才设置 metric，确保 Select 组件能正确显示选中值
      if (initMetricData.length > 0 && _metricId) {
        const metricExists = initMetricData.some(
          (item) => item.name === _metricId
        );
        if (metricExists) {
          setMetric(_metricId);
          // 同时设置 labels，确保条件维度能正常使用
          const target = initMetricData.find((item) => item.name === _metricId);
          if (target) {
            const _labels = getMetricDimensionNames(target?.dimensions);
            const initialBuiltInUnit = resolveUnitOnMetricSelect(target?.unit);
            setCalculationUnit(initialBuiltInUnit);
            // 计算完整的分组维度选项列表并设置为所有选项
            const fixedList =
              getGroupIds(monitorName as string)?.list || defaultGroup;
            const allGroupByOptions = [...new Set([...fixedList, ..._labels])];
            setGroupBy(allGroupByOptions);
            setMetricRows([
              createMetricRow(0, {
                metricId: target.id,
                metricName: target.name,
                groupAlgorithm: initForm.group_algorithm || 'avg',
                groupBy: allGroupByOptions
              })
            ]);
            setMetricExpressionMode('metric');
          }
        }
      } else if (!_metricId) {
        setMetric(null);
        // 新增模式下没有指标时，设置分组维度为固定列表（全选）
        const fixedList =
          getGroupIds(monitorName as string)?.list || defaultGroup;
        setGroupBy(fixedList);
        setMetricRows([
          createMetricRow(0, {
            groupAlgorithm: initForm.group_algorithm || 'avg',
            groupBy: fixedList
          })
        ]);
        setMetricExpressionMode('metric');
      }
      const instanceIdStr = searchParams.get('instanceId');
      let instanceIds: string[] = [];
      if (instanceIdStr) {
        const matches = instanceIdStr.match(/\('[^']*',?\)/g);
        instanceIds = matches || [];
      }
      setSource({
        type: 'instance',
        values: instanceIds
      });
    } else if (formData?.id != null) {
      // 等详情接口回填后再 dealDetail，避免空 formData 把频率/组织等字段冲成空值
      dealDetail(formData);
    }
  }, [type, formData, pluginList, channelList, initMetricData]);

  useEffect(() => {
    if (
      initMetricData.length > 0 &&
      formData &&
      !['builtIn', 'add'].includes(type)
    ) {
      processMetricData(formData);
    }
  }, [initMetricData]);

  useEffect(() => {
    const nextLabelsByRef: Record<string, string[]> = {};
    metricRows.forEach((row) => {
      const target = metrics.find(
        (item) =>
          (row.metricId != null && String(item.id) === String(row.metricId)) ||
          (!!row.metricName && item.name === row.metricName)
      );
      nextLabelsByRef[row.ref] = getMetricDimensionNames(target?.dimensions);
    });
    setLabelsByRef(nextLabelsByRef);

    if (metricRows.length === 1) {
      const row = metricRows[0];
      const target = metrics.find(
        (item) =>
          (row.metricId != null && String(item.id) === String(row.metricId)) ||
          (!!row.metricName && item.name === row.metricName)
      );
      setMetric(row.metricName || target?.name || null);
      setConditions(row.filters || []);
      setGroupBy(sanitizeGroupBy(row.groupBy || []));
      setGroupAlgorithm(row.groupAlgorithm || 'avg');
    }
  }, [metricRows, metrics]);

  useEffect(() => {
    const targetPluginId = resolveInitialMetricPluginId({
      type,
      pluginList,
      policyCollectType: formData?.collect_type
    });
    if (!monitorObjId || !targetPluginId) return;
    if (initialMetricPluginIdRef.current === targetPluginId) return;
    initialMetricPluginIdRef.current = targetPluginId;
    getMetrics(
      {
        monitor_object_id: monitorObjId,
        monitor_plugin_id: targetPluginId
      },
      'init'
    );
  }, [type, pluginList, formData?.collect_type, monitorObjId]);

  const getObjects = async () => {
    const data = await getMonitorObject();
    setObjects(data);
  };

  const changeCollectType = (id: string | number) => {
    getMetrics({
      monitor_object_id: monitorObjId,
      monitor_plugin_id: id
    });
  };

  const getChannelList = async () => {
    const data = await getSystemChannelList();
    setChannelList(data);
  };

  const getPlugins = async () => {
    const plugins = await loadMonitorPluginsByObjectCached(monitorObjId, () =>
      getMonitorPlugin({
        monitor_object_id: monitorObjId
      })
    );
    const options = plugins
      .sort((a: PluginItem, b: PluginItem) => {
        const order = (item: PluginItem) =>
          item.is_pre ? 0 : !item.is_custom ? 1 : 2;
        return order(a) - order(b);
      })
      .map((item: PluginItem) => ({
        label: item.display_name || item.name || '--',
        value: item.id,
        name: item.name
      }));
    setPluginList(options);
  };

  const dealDetail = (data: StrategyFields) => {
    const {
      source,
      schedule,
      period,
      threshold: thresholdList,
      no_data_period,
      recovery_condition,
      trigger_count,
      group_by,
      query_condition,
      collect_type,
      enable_alerts,
      no_data_recovery_period,
      calculation_unit,
      threshold_unit,
      no_data_level,
      no_data_alert_name
    } = data;
    form.setFieldsValue({
      ...data,
      collect_type: collect_type ? +collect_type : '',
      trigger_count: trigger_count || 1,
      recovery_condition: recovery_condition || null,
      schedule: schedule?.value || null,
      period: period?.value || null,
      query: query_condition?.query || null
    });
    setGroupBy(sanitizeGroupBy(group_by || []));
    feedbackThreshold(thresholdList);
    const initialUnit = restoreCalculationUnitState(calculation_unit);
    setCalculationUnit(initialUnit);
    setThresholdUnit(restoreCalculationUnitState(threshold_unit) || initialUnit);
    setPeriod(period?.value || null);
    setPeriodUnit(period?.type || 'min');
    setGroupAlgorithm(data.group_algorithm || 'avg');
    setAlgorithm(data.algorithm || null);
    if (source?.type) {
      setSource(source);
    } else {
      setSource({
        type: '',
        values: []
      });
    }
    setNoDataAlert(no_data_period?.value || null);
    setNodataUnit(no_data_period?.type || 'min');
    setNoDataRecovery(no_data_recovery_period?.value || null);
    setNoDataRecoveryUnit(no_data_recovery_period?.type || '');
    setUnit(schedule?.type || 'min');
    setEnableAlerts(enable_alerts?.length ? enable_alerts : ['threshold']);
    // 设置无数据告警级别和名称
    if (enable_alerts?.includes('no_data') && no_data_level) {
      setNoDataAlertLevel(no_data_level as string);
    } else {
      setNoDataAlertLevel('none');
    }
    // 如果无数据告警名称为空，使用默认值
    const defaultNoDataAlertName = t('monitor.events.noDataAlertNameDefault');
    const finalNoDataAlertName =
      (no_data_alert_name as string) || defaultNoDataAlertName;
    setNoDataAlertName(finalNoDataAlertName);
    // 同步更新 form 字段
    if (!no_data_alert_name) {
      form.setFieldsValue({
        no_data_alert_name: defaultNoDataAlertName
      });
    }
  };

  const processMetricData = (data: StrategyFields) => {
    const { query_condition } = data;
    if (query_condition?.type === 'metric' && initMetricData.length > 0) {
      const _metrics = initMetricData.find(
        (item) => query_condition?.metric_id != null && String(item.id) === String(query_condition.metric_id)
      );
      if (_metrics) {
        setMetric(_metrics?.name || '');
        setConditions(query_condition?.filter || []);
        setMetricRows([
          createMetricRow(0, {
            metricId: _metrics.id,
            metricName: _metrics.name,
            filters: query_condition?.filter || [],
            groupAlgorithm: data.group_algorithm || 'avg',
            groupBy: sanitizeGroupBy(data.group_by || [])
          })
        ]);
        setMetricExpressionMode('metric');
        const isEnumMetric = isStringArray(_metrics?.unit || '');
        const comparisonMethods = isEnumMetric
          ? ENUM_COMPARISON_METHOD
          : COMPARISON_METHOD;
        const defaultMethod = comparisonMethods[0].value;
        // 更新阈值：对于未填写的项，如果当前操作符不在当前指标类型的操作符列表中，则设置为默认值
        setThreshold((prevThreshold: any) =>
          prevThreshold.map((item) => {
            const methodExists = comparisonMethods.some(
              (m) => m.value === item.method
            );
            if (item.value === null && !methodExists) {
              return { ...item, method: defaultMethod };
            }
            return item;
          })
        );
      }
    } else if (query_condition?.type === 'formula' && initMetricData.length > 0) {
      const restoredState = toMetricExpressionStateFromQueryCondition(
        query_condition
      );
      const rows = restoredState.rows.map((row) => {
        const target = initMetricData.find((item) => row.metricId != null && String(item.id) === String(row.metricId));
        return {
          ...row,
          metricName: target?.name || row.metricName
        };
      });
      setMetricRows(rows);
      setMetricExpressionMode('formula');
      setCalculationUnit(
        restoreCalculationUnitState(data.calculation_unit as string | null)
      );
      setThresholdUnit(
        restoreCalculationUnitState(data.threshold_unit as string | null) ||
          restoreCalculationUnitState(data.calculation_unit as string | null)
      );
      setFormulaResultName(restoredState.resultName);
      setFormulaExpression(restoredState.expression);
      setMetric(rows[0]?.metricName || null);
      setConditions(rows[0]?.filters || []);
      setGroupBy(sanitizeGroupBy(rows[0]?.groupBy || []));
      setGroupAlgorithm(rows[0]?.groupAlgorithm || 'avg');
    }
  };

  const feedbackThreshold = (data: TableDataItem) => {
    const _threshold = cloneDeep(threshold);
    _threshold.forEach((item: ThresholdField) => {
      const target = data.find(
        (tex: TableDataItem) => tex.level === item.level
      );
      if (target) {
        item.value = target.value;
        item.method = target.method;
      }
    });
    setThreshold(_threshold || []);
  };

  const openInstModal = () => {
    const title = `${t('common.select')} ${t('monitor.asset')}`;
    instRef.current?.showModal({
      title,
      type: 'add',
      form: {
        ...source,
        id: detailId
      }
    });
  };

  const onChooseAssets = (assets: SourceFeild) => {
    setSource(assets);
    form.validateFields(['source']);
  };

  const handleMetricChange = (val: string) => {
    setMetric(val);
    const target = metrics.find((item) => item.name === val);
    const _labels = getMetricDimensionNames(target?.dimensions);
    // 计算完整的分组维度选项列表（固定列表 + 标签列表，去重）
    const fixedList = getGroupIds(monitorName as string)?.list || defaultGroup;
    const allGroupByOptions = [...new Set([...fixedList, ..._labels])];
    // 设置分组维度为所有可用选项（如果没有则为空数组）
    setGroupBy(allGroupByOptions);
    setConditions([]);

    // 判断新指标是否为枚举类型，并处理阈值的操作符和值
    const newIsEnumMetric = isStringArray(target?.unit || '');
    const newComparisonMethods = newIsEnumMetric
      ? ENUM_COMPARISON_METHOD
      : COMPARISON_METHOD;

    // 重置阈值：切换指标时，操作符选中下拉列表的第一个值，并清空值
    const newThreshold = threshold.map((item) => {
      return {
        ...item,
        method: newComparisonMethods[0].value,
        value: null // 切换指标时清空值
      };
    });
    setThreshold(newThreshold as any);

    // 选择指标后触发验证，清除错误信息（包括指标、条件维度和告警阈值）
    form.validateFields(['metric', 'threshold']);
    // none/short/枚举 → null，禁止再按 system===null 回落到 cps 等独立单位
    const nextUnit = resolveUnitOnMetricSelect(target?.unit);
    setCalculationUnit(nextUnit);
    setThresholdUnit(nextUnit);
  };

  const getMetrics = async (params = {}, type = '') => {
    try {
      setMetricsLoading(true);
      const getGroupList = fetchAllMetricsGroups(getMetricsGroup, params);
      const getMetrics = fetchAllMonitorMetrics(getMonitorMetrics, params);
      Promise.all([getGroupList, getMetrics])
        .then((res) => {
          const metricData = cloneDeep(res[1].items);
          setMetrics(res[1].items);
          const groupData: IndexViewItem[] = res[0].items.map((item) => ({
            ...item,
            id: Number(item.id),
            child: []
          }));
          metricData.forEach((metric: MetricItem) => {
            const target = groupData.find(
              (item) => item.id === metric.metric_group
            );
            if (target) {
              target.child?.push(metric);
            }
          });
          const _groupData = groupData.filter((item) => !!item.child?.length);
          setOriginMetricData(_groupData);
          if (type === 'init') {
            setInitMetricData(res[1].items);
          }
        })
        .finally(() => {
          setMetricsLoading(false);
        });
    } catch {
      setMetricsLoading(false);
    }
  };

  const getStragyDetail = async () => {
    const data = await getMonitorPolicy(detailId);
    setFormData(data);
  };

  const handleMetricRowsChange = (rows: MetricExpressionRow[]) => {
    const previousPrimaryMetricName = metricRows[0]?.metricName;
    const nextPrimaryMetricName = rows[0]?.metricName;
    const previousMode = metricExpressionMode;
    const nextMode = getMetricExpressionModeForRows(rows);
    setMetricExpressionMode(nextMode);
    setMetricRows(rows);

    if (nextMode === 'formula') {
      setCalculationUnit((current) =>
        getCalculationUnitOnMetricRowsChange({
          previousMode,
          nextMode,
          currentCalculationUnit: current,
          unitList
        })
      );
    } else {
      // 从公式切回单指标时,阈值单位回退到主指标的单位
      const primaryMetric = metrics.find(
        (item) => item.name === nextPrimaryMetricName
      );
      const retracted = getReverseModeCalculationUnit({
        previousMode,
        nextMode,
        primaryMetricUnit: primaryMetric?.unit ?? null
      });
      if (retracted !== undefined) {
        setCalculationUnit(retracted);
      }
    }

    if (
      rows.length === 1 &&
      nextPrimaryMetricName &&
      nextPrimaryMetricName !== previousPrimaryMetricName
    ) {
      handleMetricChange(nextPrimaryMetricName);
    }

    form.validateFields(['metric']).catch(() => undefined);
  };

  const handleUnitChange = (val: string) => {
    setUnit(val);
    form.setFieldsValue({
      schedule: null
    });
  };

  const handlePeriodUnitChange = (val: string) => {
    setPeriodUnit(val);
    setPeriod(null);
    form.setFieldsValue({
      period: null
    });
  };

  const handlePeriodChange = (val: number | null) => {
    setPeriod(val);
  };

  const handleAlgorithmChange = (val: string) => {
    setAlgorithm(val);
  };

  const handleNodataUnitChange = (val: string) => {
    setNodataUnit(val);
    setNoDataAlert(null);
  };

  const handleNoDataAlertChange = (e: number | null) => {
    setNoDataAlert(e);
  };

  const handleNodataRecoveryUnitChange = (val: string) => {
    setNoDataRecoveryUnit(val);
    setNoDataRecovery(null);
  };

  const handleNoDataRecoveryChange = (e: number | null) => {
    setNoDataRecovery(e);
  };

  const handleNoDataAlertLevelChange = (val: string) => {
    setNoDataAlertLevel(val);
  };

  const handleNoDataAlertNameChange = (val: string) => {
    setNoDataAlertName(val);
  };

  const handleThresholdChange = (value: ThresholdField[]) => {
    setThreshold(value);
  };

  const handleThresholdUnitChange = (unit: string) => {
    setThreshold((current) =>
      scaleThresholdValuesForUnitChange(current, thresholdUnit, unit)
    );
    setThresholdUnit(unit);
    form.validateFields(['threshold']);
  };

  const handleFormulaResultUnitChange = (unit: string) => {
    setCalculationUnit(unit);
    form.validateFields(['threshold']);
  };

  const goBack = () => {
    const targetUrl = `/monitor/event/${
      type === 'builtIn' ? 'template' : 'strategy'
    }?objId=${monitorObjId}`;
    router.push(targetUrl);
  };

  const linkToSystemManage = () => {
    const url = '/system-manager/channel';
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const buildStrategyParams = (values: any): StrategyFields | null => {
      const params: any = cloneDeep(values);
      delete params._conditions_validator;
      delete params.no_data_level;
      delete params.no_data_alert_name;
      const target: any = pluginList.find(
        (item) => item.value === params.collect_type
      );
      const isTrapPlugin = target?.name === 'SNMP Trap';
      let selectedMetricSourceUnit: string | null | undefined = null;
      if (isTrapPlugin) {
        params.query_condition = {
          type: 'pmq',
          query: params.query
        };
        params.source = {};
        params.group_algorithm = 'avg';
        params.algorithm = 'last_over_time';
      } else {
        try {
          params.query_condition = buildMetricExpressionQueryCondition({
            mode: metricExpressionMode,
            resultName: formulaResultName,
            expression: formulaExpression,
            rows: metricRows
          });
        } catch (error) {
          message.error(
            error instanceof Error
              ? error.message
              : t('monitor.events.metricValidate')
          );
          return null;
        }
        const primaryMetric = metricRows[0];
        const mertricTarget = metrics.find(
          (item) =>
            (primaryMetric?.metricId != null &&
              String(item.id) === String(primaryMetric.metricId)) ||
            item.name === primaryMetric?.metricName
        );
        selectedMetricSourceUnit = mertricTarget?.unit;
        params.source = source;
      }
      params.group_algorithm =
        params.group_algorithm ||
        metricRows[0]?.groupAlgorithm ||
        groupAlgorithm ||
        'avg';
      params.algorithm = params.algorithm || algorithm || 'avg_over_time';
      params.threshold = threshold.filter(
        (item) => !!item.value || item.value === 0
      );
      const policyUnits = isTrapPlugin
        ? { metricUnit: '', calculationUnit: '', thresholdUnit: '' }
        : resolveMetricExpressionUnits({
          queryType:
            metricExpressionMode === 'formula' || metricRows.length > 1
              ? 'formula'
              : 'metric',
          metricUnit: selectedMetricSourceUnit,
          calculationUnit: effectiveCalculationUnit,
          thresholdUnit: effectiveThresholdUnit
        });
      params.metric_unit = policyUnits.metricUnit;
      params.calculation_unit = policyUnits.calculationUnit;
      params.threshold_unit = policyUnits.thresholdUnit;
      params.monitor_object = monitorObjId;
      params.schedule = {
        type: unit,
        value: values.schedule
      };
      params.period = {
        type: periodUnit,
        value: values.period
      };
      // 根据无数据告警级别设置 enable_alerts 和相关参数
      const isNoDataEnabled = noDataAlertLevel && noDataAlertLevel !== 'none';
      const _enableAlerts = isNoDataEnabled
        ? [...new Set([...enableAlerts, 'no_data'])]
        : enableAlerts.filter((item) => item !== 'no_data');

      if (isNoDataEnabled) {
        params.no_data_recovery_period = params.no_data_period = {
          type: nodataUnit,
          value: noDataAlert
        };
        params.no_data_level = noDataAlertLevel;
        params.no_data_alert_name = noDataAlertName;
      } else {
        const periodValue = noDataAlert
          ? { type: nodataUnit, value: noDataAlert }
          : {};
        params.no_data_period = params.no_data_recovery_period = periodValue;
      }
      if (params.notice_type_ids?.length) {
        const firstChannel = channelList.find((item) => item.id === params.notice_type_ids![0]);
        params.notice_type = firstChannel?.channel_type || '';
      }
      params.enable_alerts = _enableAlerts;
      params.recovery_condition = params.recovery_condition || 0;
      params.group_by = sanitizeGroupBy(metricRows[0]?.groupBy || groupBy);
      params.enable = true;
      return params;
  };

  const createStrategy = () => {
    form
      ?.validateFields()
      .then((values) => {
        const params = buildStrategyParams(values);
        if (params) void operateStrategy(params);
      })
      .catch(() => {
        // 校验失败（含通知开启且通知人为空）时阻止创建/保存
      });
  };

  const saveTemplate = async () => {
    if (templateSubmittingRef.current || templateSaving) return;
    if (isCreateFlow && (templateSavedOnce || templateSavedOnceRef.current)) {
      message.info(t('monitor.events.templateAlreadySaved', '当前策略已保存为模版'));
      return;
    }
    const trapTemplate = isTrap(form.getFieldValue);
    const templateFields = [
      'name',
      'alert_name',
      'collect_type',
      'schedule',
      'period',
      'threshold',
      'trigger_count',
      'recovery_condition',
      'no_data_alert_name',
      ...(trapTemplate ? ['query'] : ['metric', 'algorithm']),
    ];
    let validated: Record<string, unknown>;
    try {
      validated = await form.validateFields(templateFields);
    } catch {
      return;
    }
    const params = buildStrategyParams({
      ...form.getFieldsValue(true),
      ...validated,
    });
    if (!params) return;
    pendingTemplateConfigRef.current = params;
    const defaultName = String(params.name || validated.name || '').trim();
    setTemplateMetaDefaults({
      name: defaultName,
      description: defaultName,
    });
    setTemplateConfirmVisible(true);
  };

  const resetTemplateConfirm = () => {
    setTemplateConfirmVisible(false);
    pendingTemplateConfigRef.current = null;
    templateMetaForm.resetFields();
  };

  const closeTemplateConfirm = () => {
    if (templateSubmittingRef.current) return;
    resetTemplateConfirm();
  };

  const confirmSaveTemplate = async (options?: { exitAfterSave?: boolean }) => {
    if (templateSubmittingRef.current || templateSaving) return;
    if (isCreateFlow && (templateSavedOnce || templateSavedOnceRef.current)) {
      message.info(t('monitor.events.templateAlreadySaved', '当前策略已保存为模版'));
      return;
    }
    const config = pendingTemplateConfigRef.current;
    if (!config) return;
    let meta: { name: string; description: string };
    try {
      meta = await templateMetaForm.validateFields();
    } catch {
      return;
    }
    const name = String(meta.name || '').trim();
    if (!name) {
      templateMetaForm.setFields([
        {
          name: 'name',
          errors: [t('common.required')],
        },
      ]);
      return;
    }
    templateSubmittingRef.current = true;
    setTemplateSaving(true);
    try {
      await savePolicyTemplate({
        monitor_object: monitorObjId,
        plugin: config.collect_type,
        name,
        description: String(meta.description ?? ''),
        config,
      });
      message.success(t('monitor.events.saveTemplateSuccess', '模版保存成功'));
      if (isCreateFlow) {
        templateSavedOnceRef.current = true;
        setTemplateSavedOnce(true);
      }
      resetTemplateConfirm();
      if (options?.exitAfterSave) {
        goBack();
      }
    } finally {
      templateSubmittingRef.current = false;
      setTemplateSaving(false);
    }
  };

  const operateStrategy = async (params: StrategyFields) => {
    try {
      setConfirmLoading(true);
      const msg: string = t(
        ['builtIn', 'add'].includes(type)
          ? 'common.successfullyAdded'
          : 'common.successfullyModified'
      );
      const url: string = ['builtIn', 'add'].includes(type)
        ? '/monitor/api/monitor_policy/'
        : `/monitor/api/monitor_policy/${detailId}/`;
      const requestType = ['builtIn', 'add'].includes(type) ? post : put;
      await requestType(url, params);
      message.success(msg);
      goBack();
    } finally {
      setConfirmLoading(false);
    }
  };

  const isTrap = (callBack: any) => {
    const target: any = pluginList.find(
      (item) => item.value === callBack('collect_type')
    );
    return target?.name === 'SNMP Trap';
  };

  return (
    <Spin spinning={pageLoading} className="w-full">
      <div className={strategyStyle.strategy}>
        <div className={strategyStyle.title}>
          <ArrowLeftOutlined
            className="text-[var(--color-primary)] text-[20px] cursor-pointer mr-[10px]"
            onClick={goBack}
          />
          {['builtIn', 'add'].includes(type) ? (
            t('monitor.events.createPolicy')
          ) : (
            <span>
              {t('monitor.events.editPolicy')} -{' '}
              <span className="text-[var(--color-text-3)] text-[12px]">
                {detailName}
              </span>
            </span>
          )}
        </div>
        <div className={strategyStyle.form} ref={formContainerRef}>
          <div className="flex gap-6">
            <div className="w-[820px] flex-shrink-0">
              <Form form={form} name="basic" scrollToFirstError>
                <Steps
                  direction="vertical"
                  items={[
                    {
                      title: t('monitor.events.basicInformation'),
                      description: (
                        <div ref={basicInfoRef}>
                          <BasicInfoForm
                            ref={basicInfoFormRef}
                            source={source}
                            unit={unit}
                            onOpenInstModal={openInstModal}
                            onUnitChange={handleUnitChange}
                            isTrap={isTrap}
                          />
                        </div>
                      ),
                      status: 'process'
                    },
                    {
                      title: t('monitor.events.defineTheMetric'),
                      description: (
                        <MetricDefinitionForm
                          form={form}
                          pluginList={pluginList}
                          metricsLoading={metricsLoading}
                          period={period}
                          periodUnit={periodUnit}
                          originMetricData={originMetricData}
                          monitorName={monitorName as string}
                          metricRows={metricRows}
                          metricExpressionMode={metricExpressionMode}
                          resultName={formulaResultName}
                          expression={formulaExpression}
                          resultUnit={
                            metricExpressionMode === 'formula'
                              ? effectiveCalculationUnit
                              : null
                          }
                          labelsByRef={labelsByRef}
                          groupedUnitOptions={groupedUnitOptions}
                          unitList={unitList}
                          onCollectTypeChange={changeCollectType}
                          onMetricRowsChange={handleMetricRowsChange}
                          onResultNameChange={setFormulaResultName}
                          onExpressionChange={setFormulaExpression}
                          onResultUnitChange={handleFormulaResultUnitChange}
                          onPeriodChange={handlePeriodChange}
                          onPeriodUnitChange={handlePeriodUnitChange}
                          onAlgorithmChange={handleAlgorithmChange}
                          isTrap={isTrap}
                        />
                      ),
                      status: 'process'
                    },
                    {
                      title: t('monitor.events.alertConditions'),
                      description: (
                        <AlertConditionsForm
                          enableAlerts={enableAlerts}
                          threshold={threshold}
                          calculationUnit={effectiveCalculationUnit}
                          thresholdUnit={effectiveThresholdUnit}
                          noDataAlert={noDataAlert}
                          nodataUnit={nodataUnit}
                          noDataRecovery={noDataRecovery}
                          noDataRecoveryUnit={noDataRecoveryUnit}
                          noDataAlertLevel={noDataAlertLevel}
                          noDataAlertName={noDataAlertName}
                          metricUnit={
                            metrics.find((item) => item.name === metric)
                              ?.unit || null
                          }
                          isFormulaMode={metricExpressionMode === 'formula'}
                          onEnableAlertsChange={setEnableAlerts}
                          onThresholdChange={handleThresholdChange}
                          onThresholdUnitChange={handleThresholdUnitChange}
                          onNodataUnitChange={handleNodataUnitChange}
                          onNoDataAlertChange={handleNoDataAlertChange}
                          onNodataRecoveryUnitChange={
                            handleNodataRecoveryUnitChange
                          }
                          onNoDataRecoveryChange={handleNoDataRecoveryChange}
                          onNoDataAlertLevelChange={
                            handleNoDataAlertLevelChange
                          }
                          onNoDataAlertNameChange={handleNoDataAlertNameChange}
                          isTrap={isTrap}
                        />
                      ),
                      status: 'process'
                    },
                    {
                      title: t('monitor.events.configureNotifications'),
                      description: (
                        <NotificationForm
                          channelList={channelList}
                          userList={noticeUserList}
                          onLinkToSystemManage={linkToSystemManage}
                        />
                      ),
                      status: 'process'
                    }
                  ]}
                />
              </Form>
            </div>
            <div className="flex flex-col flex-1 min-w-[400px]">
              <VariablesTable
                displayFields={currentMonitorObject?.display_fields}
                groupBy={sanitizeGroupBy(metricRows[0]?.groupBy || groupBy)}
                onVariableSelect={(variable: string) => {
                  basicInfoFormRef.current?.insertVariable(variable);
                }}
              />
              <MetricPreview
                monitorObjId={monitorObjId}
                source={source}
                metric={metric}
                metrics={metrics}
                groupBy={groupBy}
                groupAlgorithm={groupAlgorithm}
                conditions={conditions}
                period={period}
                periodUnit={periodUnit}
                algorithm={algorithm}
                threshold={threshold}
                calculationUnit={effectiveCalculationUnit}
                thresholdUnit={effectiveThresholdUnit}
                metricRows={metricRows}
                metricExpressionMode={metricExpressionMode}
                resultName={formulaResultName}
                expression={formulaExpression}
                scrollContainerRef={formContainerRef}
                anchorRef={basicInfoRef}
                fixedGroupByList={
                  getGroupIds(monitorName as string)?.list || defaultGroup
                }
              />
            </div>
          </div>
        </div>
        <div className={`${strategyStyle.footer} flex gap-2`}>
          <Button
            type="primary"
            loading={confirmLoading}
            onClick={createStrategy}
          >
            {t('common.confirm')}
          </Button>
            {isCreateFlow && templateSavedOnce ? (
            <Button onClick={goBack}>{t('common.back')}</Button>
            ) : (
            <>
              <Button loading={templateSaving} onClick={() => void saveTemplate()}>
                {t('monitor.events.saveTemplate', '保存模版')}
              </Button>
              <Button onClick={goBack}>{t('common.cancel')}</Button>
            </>
            )}
        </div>
      </div>
      <SelectAssets
        ref={instRef}
        monitorObject={monitorObjId}
        objects={objects}
        onSuccess={onChooseAssets}
      />
      <OperateModal
        title={t('monitor.events.saveTemplate', '保存模版')}
        open={templateConfirmVisible}
        onCancel={closeTemplateConfirm}
        maskClosable={!templateSaving}
        closable={!templateSaving}
        footer={
          <div>
            {isCreateFlow ? (
              <Button
                className="mr-[10px]"
                loading={templateSaving}
                disabled={templateSaving}
                onClick={() => void confirmSaveTemplate({ exitAfterSave: true })}
              >
                {t('monitor.events.saveAndExit', '保存并退出')}
              </Button>
            ) : null}
            <Button
              className="mr-[10px]"
              type="primary"
              loading={templateSaving}
              disabled={templateSaving}
              onClick={() => void confirmSaveTemplate()}
            >
              {isCreateFlow ? t('monitor.events.saveAndContinue', '保存并继续') : t('common.confirm')}
            </Button>
            <Button disabled={templateSaving} onClick={closeTemplateConfirm}>
              {t('common.cancel')}
            </Button>
          </div>
        }
      >
        <Form
          form={templateMetaForm}
          layout="vertical"
          preserve={false}
          initialValues={templateMetaDefaults}
        >
          <Form.Item
            label={t('monitor.integrations.templateName')}
            name="name"
            rules={[{ required: true, whitespace: true, message: t('common.required') }]}
          >
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item
            label={t('monitor.integrations.templateDescription')}
            name="description"
          >
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </OperateModal>
    </Spin>
  );
};

export default StrategyOperation;
