'use client';
import { useEffect, useState, useRef } from 'react';
import { Spin, Button, Form, message, Steps } from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  UserItem,
  SegmentedItem,
  TableDataItem,
  GroupInfo,
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
const defaultGroup = ['instance_id'];

const StrategyOperation = () => {
  const { t } = useTranslation();
  const { post, put, isLoading } = useApiClient();
  const {
    getMetricsGroup,
    getMonitorMetrics,
    getMonitorPlugin,
    getMonitorObject
  } = useMonitorApi();
  const { getMonitorPolicy, getSystemChannelList } = useEventApi();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const router = useRouter();
  const { getCollectType, getGroupIds } = useObjectConfigInfo();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
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
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [source, setSource] = useState<SourceFeild>({
    type: '',
    values: []
  });
  const [metric, setMetric] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [metricsLoading, setMetricsLoading] = useState<boolean>(false);
  const [labels, setLabels] = useState<string[]>([]);
  const [unit, setUnit] = useState<string>('min');
  const [periodUnit, setPeriodUnit] = useState<string>('min');
  const [nodataUnit, setNodataUnit] = useState<string>('min');
  const [noDataRecoveryUnit, setNoDataRecoveryUnit] = useState<string>('min');
  const [conditions, setConditions] = useState<FilterItem[]>([]);
  const [noDataAlert, setNoDataAlert] = useState<number | null>(null);
  const [noDataRecovery, setNoDataRecovery] = useState<number | null>(null);
  const [noDataAlertLevel, setNoDataAlertLevel] = useState<string>('none');
  const [noDataAlertName, setNoDataAlertName] = useState<string>('');
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [groupBy, setGroupBy] = useState<string[]>(
    getGroupIds(monitorName as string)?.default || defaultGroup
  );
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
  const [pluginList, setPluginList] = useState<SegmentedItem[]>([]);
  const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>([]);
  const [initMetricData, setInitMetricData] = useState<MetricItem[]>([]);
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [enableAlerts, setEnableAlerts] = useState<string[]>(['threshold']);

  useEffect(() => {
    if (!isLoading) {
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

  useEffect(() => {
    form.resetFields();
    if (['builtIn', 'add'].includes(type)) {
      const strategyInfo = JSON.parse(
        sessionStorage.getItem('strategyInfo') || '{}'
      );
      const channelItem = channelList[0];
      const initForm: TableDataItem = {
        organizations: groupId,
        notice_type_id: channelItem?.id,
        notice_type: channelItem?.channel_type,
        notice: false,
        period: 5,
        schedule: 5,
        recovery_condition: 5,
        collect_type: pluginList[0]?.value
      };
      let _metricId = searchParams.get('metricId') || null;
      if (type === 'builtIn') {
        ['name', 'alert_name', 'algorithm'].forEach((item) => {
          initForm[item] = strategyInfo[item] || null;
        });
        feedbackThreshold(strategyInfo.threshold || []);
        _metricId = strategyInfo.metric_name || null;
      }
      // 设置无数据告警名称默认值
      const defaultNoDataAlertName = t('monitor.events.noDataAlertNameDefault');
      setNoDataAlertName(defaultNoDataAlertName);
      form.setFieldsValue({
        ...initForm,
        no_data_alert_name: defaultNoDataAlertName
      });
      setMetric(_metricId);
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
    } else {
      dealDetail(formData);
    }
  }, [type, formData, pluginList, channelList]);

  useEffect(() => {
    if (
      initMetricData.length > 0 &&
      formData &&
      !['builtIn', 'add'].includes(type)
    ) {
      processMetricData(formData);
    }
  }, [initMetricData]);

  const getObjects = async () => {
    const data = await getMonitorObject();
    setObjects(data);
  };

  const changeCollectType = (id: string) => {
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
    const data = await getMonitorPlugin({
      monitor_object_id: monitorObjId
    });
    const plugins = data.map((item: PluginItem) => ({
      label: getCollectType(monitorName as string, item.name),
      value: item.id,
      name: item.name
    }));
    setPluginList(plugins);
    getMetrics(
      {
        monitor_object_id: monitorObjId,
        monitor_plugin_id: plugins[0]?.value
      },
      'init'
    );
  };

  const dealDetail = (data: StrategyFields) => {
    const {
      source,
      schedule,
      period,
      threshold: thresholdList,
      no_data_period,
      recovery_condition,
      group_by,
      query_condition,
      collect_type,
      enable_alerts,
      no_data_recovery_period,
      calculation_unit,
      no_data_level,
      no_data_alert_name
    } = data;
    form.setFieldsValue({
      ...data,
      collect_type: collect_type ? +collect_type : '',
      recovery_condition: recovery_condition || null,
      schedule: schedule?.value || null,
      period: period?.value || null,
      query: query_condition?.query || null
    });
    setGroupBy(group_by || []);
    feedbackThreshold(thresholdList);
    setCalculationUnit(calculation_unit || null);
    setPeriod(period?.value || null);
    setPeriodUnit(period?.type || 'min');
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
    setUnit(schedule?.type || '');
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
        (item) => item.id === query_condition?.metric_id
      );
      if (_metrics) {
        const _labels = (_metrics?.dimensions || []).map((item) => item.name);
        setMetric(_metrics?.name || '');
        setLabels(_labels);
        setConditions(query_condition?.filter || []);
      }
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
  };

  const handleMetricChange = (val: string) => {
    setMetric(val);
    const target = metrics.find((item) => item.name === val);
    const _labels = (target?.dimensions || []).map((item) => item.name);
    setLabels(_labels);
    // 自动设置告警阈值单位为指标的默认单位
    setCalculationUnit(target?.unit || null);
  };

  const getMetrics = async (params = {}, type = '') => {
    try {
      setMetricsLoading(true);
      const getGroupList = getMetricsGroup(params);
      const getMetrics = getMonitorMetrics(params);
      Promise.all([getGroupList, getMetrics])
        .then((res) => {
          const metricData = cloneDeep(res[1] || []);
          setMetrics(res[1] || []);
          const groupData = res[0].map((item: GroupInfo) => ({
            ...item,
            child: []
          }));
          metricData.forEach((metric: MetricItem) => {
            const target = groupData.find(
              (item: GroupInfo) => item.id === metric.metric_group
            );
            if (target) {
              target.child.push(metric);
            }
          });
          const _groupData = groupData.filter(
            (item: any) => !!item.child?.length
          );
          setOriginMetricData(_groupData);
          if (type === 'init') {
            setInitMetricData(res[1] || []);
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

  const handleGroupByChange = (val: string[]) => {
    setGroupBy(val);
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

  const handleCalculationUnitChange = (unit: string) => {
    setCalculationUnit(unit);
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

  const createStrategy = () => {
    form?.validateFields().then((values) => {
      const params = cloneDeep(values);
      delete params._conditions_validator;
      delete params.no_data_level;
      delete params.no_data_alert_name;
      const target: any = pluginList.find(
        (item) => item.value === params.collect_type
      );
      const isTrapPlugin = target?.name === 'SNMP Trap';
      if (isTrapPlugin) {
        params.query_condition = {
          type: 'pmq',
          query: params.query
        };
        params.source = {};
        params.algorithm = 'last_over_time';
      } else {
        const mertricTarget = metrics.find((item) => item.name === metric);
        params.query_condition = {
          type: 'metric',
          metric_id: mertricTarget?.id,
          filter: conditions
        };
        params.source = source;
        params.metric_unit = mertricTarget?.unit;
      }
      params.threshold = threshold.filter(
        (item) => !!item.value || item.value === 0
      );
      params.calculation_unit = calculationUnit;
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
        params.no_data_period = params.no_data_recovery_period = {};
      }
      if (params.notice_type_id) {
        params.notice_type =
          channelList.find((item) => item.id === params.notice_type_id)
            ?.channel_type || '';
      }
      params.enable_alerts = _enableAlerts;
      params.recovery_condition = params.recovery_condition || 0;
      params.group_by = groupBy;
      params.enable = true;
      operateStrategy(params);
    });
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
            <div className="w-[800px] flex-shrink-0">
              <Form form={form} name="basic">
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
                          metric={metric}
                          metricsLoading={metricsLoading}
                          labels={labels}
                          conditions={conditions}
                          groupBy={groupBy}
                          period={period}
                          periodUnit={periodUnit}
                          originMetricData={originMetricData}
                          monitorName={monitorName as string}
                          onCollectTypeChange={changeCollectType}
                          onMetricChange={handleMetricChange}
                          onFiltersChange={setConditions}
                          onGroupChange={handleGroupByChange}
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
                          calculationUnit={calculationUnit}
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
                          onEnableAlertsChange={setEnableAlerts}
                          onThresholdChange={handleThresholdChange}
                          onCalculationUnitChange={handleCalculationUnitChange}
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
                          userList={userList}
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
                onVariableSelect={(variable: string) => {
                  const currentAlertName =
                    form.getFieldValue('alert_name') || '';
                  form.setFieldsValue({
                    alert_name: currentAlertName + variable
                  });
                  // 自动聚焦到告警名称输入框
                  basicInfoFormRef.current?.focusAlertName();
                }}
              />
              <MetricPreview
                monitorObjId={monitorObjId}
                source={source}
                metric={metric}
                metrics={metrics}
                groupBy={groupBy}
                conditions={conditions}
                period={period}
                periodUnit={periodUnit}
                algorithm={algorithm}
                threshold={threshold}
                calculationUnit={calculationUnit}
                scrollContainerRef={formContainerRef}
                anchorRef={basicInfoRef}
              />
            </div>
          </div>
        </div>
        <div className={strategyStyle.footer}>
          <Button
            type="primary"
            className="mr-[10px]"
            loading={confirmLoading}
            onClick={createStrategy}
          >
            {t('common.confirm')}
          </Button>
          <Button onClick={goBack}>{t('common.cancel')}</Button>
        </div>
      </div>
      <SelectAssets
        ref={instRef}
        monitorObject={monitorObjId}
        objects={objects}
        onSuccess={onChooseAssets}
      />
    </Spin>
  );
};

export default StrategyOperation;
