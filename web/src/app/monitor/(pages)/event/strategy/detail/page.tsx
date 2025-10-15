'use client';
import React, { useEffect, useState, useRef } from 'react';
import {
  Spin,
  Input,
  Button,
  Form,
  Select,
  message,
  Steps,
  Switch,
  Radio,
  InputNumber,
  Segmented,
  Tooltip,
} from 'antd';
import useApiClient from '@/utils/request';
import useMonitorApi from '@/app/monitor/api';
import useEventApi from '@/app/monitor/api/event';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ListItem,
  UserItem,
  SegmentedItem,
  TableDataItem,
  GroupInfo,
  ObjectItem,
  MetricItem,
  IndexViewItem,
  ThresholdField,
  FilterItem,
} from '@/app/monitor/types';
import GroupTreeSelector from '@/components/group-tree-select';
import {
  PluginItem,
  SourceFeild,
  StrategyFields,
  ChannelItem,
} from '@/app/monitor/types/event';
import { useCommon } from '@/app/monitor/context/common';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import strategyStyle from '../index.module.scss';
import { PlusOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import SelectAssets from '../selectAssets';
import SelectCards from './selectCard';
import { useSearchParams, useRouter } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import { useScheduleList, useMethodList } from '@/app/monitor/hooks/event';
import { useLevelList } from '@/app/monitor/hooks';
import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';
import ThresholdList from './thresholdList';
import ConditionSelector from './conditionSelector';
import { cloneDeep } from 'lodash';
const { Option } = Select;
const defaultGroup = ['instance_id'];
const { TextArea } = Input;

const StrategyOperation = () => {
  const { t } = useTranslation();
  const { post, put, isLoading } = useApiClient();
  const {
    getMetricsGroup,
    getMonitorMetrics,
    getMonitorPlugin,
    getMonitorObject,
  } = useMonitorApi();
  const { getMonitorPolicy, getSystemChannelList } = useEventApi();
  const METHOD_LIST = useMethodList();
  const LEVEL_LIST = useLevelList();
  const SCHEDULE_LIST = useScheduleList();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const router = useRouter();
  const { getCollectType, getGroupIds } = useObjectConfigInfo();
  const users = useRef(commonContext?.userList || []);
  const userList: UserItem[] = users.current;
  const instRef = useRef<ModalRef>(null);
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
    values: [],
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
  const [objects, setObjects] = useState<ObjectItem[]>([]);
  const [groupBy, setGroupBy] = useState<string[]>(
    getGroupIds(monitorName as string).default || defaultGroup
  );
  const [formData, setFormData] = useState<StrategyFields>({
    threshold: [],
    source: { type: '', values: [] },
  });
  const [threshold, setThreshold] = useState<ThresholdField[]>([
    {
      level: 'critical',
      method: '>',
      value: null,
    },
    {
      level: 'error',
      method: '>',
      value: null,
    },
    {
      level: 'warning',
      method: '>',
      value: null,
    },
  ]);
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
        detailId && getStragyDetail(),
      ]).finally(() => {
        setPageLoading(false);
      });
    }
  }, [isLoading]);

  const getObjects = async () => {
    const data = await getMonitorObject();
    setObjects(data);
  };

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
        collect_type: pluginList[0]?.value,
      };
      let _metricId = searchParams.get('metricId') || null;
      if (type === 'builtIn') {
        ['name', 'alert_name', 'algorithm'].forEach((item) => {
          initForm[item] = strategyInfo[item] || null;
        });
        feedbackThreshold(strategyInfo.threshold || []);
        _metricId = strategyInfo.metric_name || null;
      }
      form.setFieldsValue(initForm);
      setMetric(_metricId);
      setSource({
        type: 'instance',
        values: searchParams.get('instanceId')
          ? (searchParams.get('instanceId')?.split(',') as string[])
          : [],
      });
    } else {
      dealDetail(formData);
    }
  }, [type, formData, pluginList, initMetricData, channelList]);

  const changeCollectType = (id: string) => {
    getMetrics({
      monitor_object_id: monitorObjId,
      monitor_plugin_id: id,
    });
  };

  const getChannelList = async () => {
    const data = await getSystemChannelList();
    setChannelList(data);
  };

  const getPlugins = async () => {
    const data = await getMonitorPlugin({
      monitor_object_id: monitorObjId,
    });
    const plugins = data.map((item: PluginItem) => ({
      label: getCollectType(monitorName as string, item.name),
      value: item.id,
      name: item.name,
    }));
    setPluginList(plugins);
    getMetrics(
      {
        monitor_object_id: monitorObjId,
        monitor_plugin_id: plugins[0]?.value,
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
    } = data;
    form.setFieldsValue({
      ...data,
      collect_type: collect_type ? +collect_type : '',
      recovery_condition: recovery_condition || null,
      schedule: schedule?.value || null,
      period: period?.value || null,
      query: query_condition?.query || null,
    });
    if (query_condition?.type === 'metric') {
      const _metrics = initMetricData.find(
        (item) => item.id === query_condition?.metric_id
      );
      const _labels = (_metrics?.dimensions || []).map((item) => item.name);
      setMetric(_metrics?.name || '');
      setLabels(_labels);
      setConditions(query_condition?.filter || []);
    }
    setGroupBy(group_by || []);
    feedbackThreshold(thresholdList);
    if (source?.type) {
      setSource(source);
    } else {
      setSource({
        type: '',
        values: [],
      });
    }
    setNoDataAlert(no_data_period?.value || null);
    setNodataUnit(no_data_period?.type || '');
    setNoDataRecovery(no_data_recovery_period?.value || null);
    setNoDataRecoveryUnit(no_data_recovery_period?.type || '');
    setUnit(schedule?.type || '');
    setPeriodUnit(period?.type || '');
    setEnableAlerts(enable_alerts?.length ? enable_alerts : ['threshold']);
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
        id: detailId,
      },
    });
  };

  const validateAssets = async () => {
    if (!source.values.length) {
      return Promise.reject(new Error(t('monitor.assetValidate')));
    }
    return Promise.resolve();
  };

  const validateMetric = async () => {
    if (!metric) {
      return Promise.reject(new Error(t('monitor.events.metricValidate')));
    }
    if (
      conditions.length &&
      conditions.some((item) => {
        return Object.values(item).some((tex) => !tex);
      })
    ) {
      return Promise.reject(new Error(t('monitor.events.conditionValidate')));
    }
    return Promise.resolve();
  };

  const validateThreshold = async () => {
    if (!enableAlerts.length) {
      return Promise.reject(new Error(t('common.required')));
    }
    if (
      enableAlerts.includes('threshold') &&
      threshold.length &&
      (threshold.some((item) => {
        return !item.method;
      }) ||
        !threshold.some((item) => {
          return !!item.value || item.value === 0;
        }))
    ) {
      return Promise.reject(new Error(t('monitor.events.conditionValidate')));
    }
    return Promise.resolve();
  };

  const validateNoDataAlert = async () => {
    if (!noDataAlert || !nodataUnit) {
      return Promise.reject(new Error(t('common.required')));
    }
    return Promise.resolve();
  };

  const validateNoDataRecoveryAlert = async () => {
    if (!noDataRecovery || !noDataRecoveryUnit) {
      return Promise.reject(new Error(t('common.required')));
    }
    return Promise.resolve();
  };

  const onChooseAssets = (assets: SourceFeild) => {
    setSource(assets);
  };

  const handleMetricChange = (val: string) => {
    setMetric(val);
    const target = metrics.find((item) => item.name === val);
    const _labels = (target?.dimensions || []).map((item) => item.name);
    setLabels(_labels);
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
            child: [],
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
      schedule: null,
    });
  };

  const handlePeriodUnitChange = (val: string) => {
    setPeriodUnit(val);
    form.setFieldsValue({
      period: null,
    });
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

  const handleThresholdChange = (value: ThresholdField[]) => {
    setThreshold(value);
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
      const target: any = pluginList.find(
        (item) => item.value === params.collect_type
      );
      const isTrapPlugin = target?.name === 'SNMP Trap';
      if (isTrapPlugin) {
        params.query_condition = {
          type: 'pmq',
          query: params.query,
        };
        params.source = {};
        params.algorithm = 'last_over_time';
      } else {
        params.query_condition = {
          type: 'metric',
          metric_id: metrics.find((item) => item.name === metric)?.id,
          filter: conditions,
        };
        params.source = source;
      }
      params.threshold = threshold.filter(
        (item) => !!item.value || item.value === 0
      );
      params.monitor_object = monitorObjId;
      params.schedule = {
        type: unit,
        value: values.schedule,
      };
      params.period = {
        type: periodUnit,
        value: values.period,
      };
      if (enableAlerts.includes('no_data')) {
        params.no_data_period = {
          type: nodataUnit,
          value: noDataAlert,
        };
        params.no_data_recovery_period = {
          type: noDataRecoveryUnit,
          value: noDataRecovery,
        };
      } else {
        params.no_data_period = params.no_data_recovery_period = {};
      }
      if (params.notice_type_id) {
        params.notice_type =
          channelList.find((item) => item.id === params.notice_type_id)
            ?.channel_type || '';
      }
      params.enable_alerts = enableAlerts;
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
    } catch (error) {
      console.log(error);
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
        <div className={strategyStyle.form}>
          <Form form={form} name="basic">
            <Steps
              direction="vertical"
              items={[
                {
                  title: t('monitor.events.basicInformation'),
                  description: (
                    <>
                      <Form.Item<StrategyFields>
                        label={
                          <span className="w-[100px]">
                            {t('monitor.events.strategyName')}
                          </span>
                        }
                        name="name"
                        rules={[
                          { required: true, message: t('common.required') },
                        ]}
                      >
                        <Input
                          placeholder={t('monitor.events.strategyName')}
                          className="w-[800px]"
                        />
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('monitor.events.alertName')}
                          </span>
                        }
                      >
                        <Form.Item
                          name="alert_name"
                          noStyle
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Input
                            placeholder={t('monitor.events.alertName')}
                            className="w-[800px]"
                          />
                        </Form.Item>
                        <div className="text-[var(--color-text-3)] mt-[10px]">
                          {t('monitor.events.alertNameTitle')}
                        </div>
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        label={
                          <span className="w-[100px]">
                            {t('monitor.group')}
                          </span>
                        }
                        name="organizations"
                        rules={[
                          { required: true, message: t('common.required') },
                        ]}
                      >
                        <GroupTreeSelector
                          style={{
                            width: '800px',
                            marginRight: '8px',
                          }}
                          placeholder={t('common.group')}
                        />
                      </Form.Item>
                    </>
                  ),
                  status: 'process',
                },
                {
                  title: t('monitor.events.defineTheMetric'),
                  description: (
                    <>
                      <Form.Item
                        className={strategyStyle.clusterLabel}
                        name="collect_type"
                        label={<span className={strategyStyle.label}></span>}
                        rules={[
                          { required: true, message: t('common.required') },
                        ]}
                      >
                        <Segmented
                          className="custom-tabs"
                          options={pluginList}
                          onChange={changeCollectType}
                        />
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(prevValues, currentValues) =>
                          prevValues.collect_type !== currentValues.collect_type
                        }
                      >
                        {({ getFieldValue }) =>
                          isTrap(getFieldValue) ? (
                            <Form.Item<StrategyFields>
                              label={<span className="w-[100px]">PromQL</span>}
                              name="query"
                              rules={[
                                {
                                  required: true,
                                  message: t('common.required'),
                                },
                              ]}
                            >
                              <TextArea
                                placeholder={t(
                                  'monitor.events.promQLPlaceholder'
                                )}
                                className="w-[800px]"
                                allowClear
                                rows={4}
                              />
                            </Form.Item>
                          ) : (
                            <>
                              <Form.Item<StrategyFields>
                                label={
                                  <span className="w-[100px]">
                                    {t('monitor.source')}
                                  </span>
                                }
                                name="source"
                                rules={[
                                  { required: true, validator: validateAssets },
                                ]}
                              >
                                <div>
                                  <div className="flex">
                                    {t('common.select')}
                                    <span className="text-[var(--color-primary)] px-[4px]">
                                      {source.values.length}
                                    </span>
                                    {t('monitor.assets')}
                                    <Button
                                      className="ml-[10px]"
                                      icon={<PlusOutlined />}
                                      size="small"
                                      onClick={openInstModal}
                                    ></Button>
                                  </div>
                                  <div className="text-[var(--color-text-3)] mt-[10px]">
                                    {t('monitor.events.setAssets')}
                                  </div>
                                </div>
                              </Form.Item>
                              <Form.Item<StrategyFields>
                                name="metric"
                                label={
                                  <span className="w-[100px]">
                                    {t('monitor.metric')}
                                  </span>
                                }
                                rules={[
                                  { validator: validateMetric, required: true },
                                ]}
                              >
                                <ConditionSelector
                                  data={{
                                    metric,
                                    filters: conditions,
                                    group: groupBy,
                                  }}
                                  metricData={originMetricData}
                                  labels={labels}
                                  loading={metricsLoading}
                                  monitorName={monitorName as string}
                                  onMetricChange={handleMetricChange}
                                  onFiltersChange={setConditions}
                                  onGroupChange={handleGroupByChange}
                                />
                                <div className="text-[var(--color-text-3)]">
                                  {t('monitor.events.setDimensions')}
                                </div>
                              </Form.Item>
                            </>
                          )
                        }
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(prevValues, currentValues) =>
                          prevValues.collect_type !== currentValues.collect_type
                        }
                      >
                        {({ getFieldValue }) =>
                          isTrap(getFieldValue) ? null : (
                            <Form.Item<StrategyFields>
                              required
                              label={
                                <span className="w-[100px]">
                                  {t('monitor.events.method')}
                                </span>
                              }
                            >
                              <Form.Item
                                name="algorithm"
                                noStyle
                                rules={[
                                  {
                                    required: true,
                                    message: t('common.required'),
                                  },
                                ]}
                              >
                                <Select
                                  style={{
                                    width: '300px',
                                  }}
                                  placeholder={t('monitor.events.method')}
                                  showSearch
                                >
                                  {METHOD_LIST.map((item: ListItem) => (
                                    <Option value={item.value} key={item.value}>
                                      <Tooltip
                                        overlayInnerStyle={{
                                          whiteSpace: 'pre-line',
                                          color: 'var(--color-text-1)',
                                        }}
                                        placement="rightTop"
                                        arrow={false}
                                        color="var(--color-bg-1)"
                                        title={item.title}
                                      >
                                        <span className="w-full flex">
                                          {item.label}
                                        </span>
                                      </Tooltip>
                                    </Option>
                                  ))}
                                </Select>
                              </Form.Item>
                              <div className="text-[var(--color-text-3)] mt-[10px]">
                                {t('monitor.events.setMethod')}
                              </div>
                            </Form.Item>
                          )
                        }
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('monitor.events.frequency')}
                          </span>
                        }
                      >
                        <Form.Item
                          name="schedule"
                          noStyle
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <InputNumber
                            min={SCHEDULE_UNIT_MAP[`${unit}Min`]}
                            max={SCHEDULE_UNIT_MAP[`${unit}Max`]}
                            precision={0}
                            addonAfter={
                              <Select
                                value={unit}
                                style={{ width: 120 }}
                                onChange={handleUnitChange}
                              >
                                {SCHEDULE_LIST.map((item) => (
                                  <Option key={item.value} value={item.value}>
                                    {item.label}
                                  </Option>
                                ))}
                              </Select>
                            }
                          />
                        </Form.Item>
                        <div className="text-[var(--color-text-3)] mt-[10px]">
                          {t('monitor.events.setFrequency')}
                        </div>
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('monitor.events.period')}
                          </span>
                        }
                      >
                        <Form.Item
                          name="period"
                          noStyle
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <InputNumber
                            min={SCHEDULE_UNIT_MAP[`${periodUnit}Min`]}
                            max={SCHEDULE_UNIT_MAP[`${periodUnit}Max`]}
                            precision={0}
                            addonAfter={
                              <Select
                                value={periodUnit}
                                style={{ width: 120 }}
                                onChange={handlePeriodUnitChange}
                              >
                                {SCHEDULE_LIST.map((item) => (
                                  <Option key={item.value} value={item.value}>
                                    {item.label}
                                  </Option>
                                ))}
                              </Select>
                            }
                          />
                        </Form.Item>
                        <div className="text-[var(--color-text-3)] mt-[10px]">
                          {t('monitor.events.setPeriod')}
                        </div>
                      </Form.Item>
                    </>
                  ),
                  status: 'process',
                },
                {
                  title: t('monitor.events.setAlertConditions'),
                  description: (
                    <>
                      <Form.Item<StrategyFields>
                        name="threshold"
                        label={
                          <span className="w-[100px]">
                            {t('monitor.events.algorithm')}
                          </span>
                        }
                        rules={[
                          { validator: validateThreshold, required: true },
                        ]}
                      >
                        <SelectCards
                          value={enableAlerts}
                          onChange={(val) => setEnableAlerts(val)}
                          data={[
                            {
                              value: 'threshold',
                              icon: 'yuzhiguanli',
                              title: t('monitor.events.threshold'),
                              content: t('monitor.events.setThreshold'),
                            },
                            {
                              value: 'no_data',
                              icon: 'yuzhiguanli',
                              title: t('monitor.events.nodata'),
                              content: t('monitor.events.setThreshold'),
                            },
                          ]}
                        />
                        <div>
                          {enableAlerts.includes('threshold') && (
                            <ThresholdList
                              data={threshold}
                              onChange={handleThresholdChange}
                            />
                          )}
                        </div>
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(prevValues, currentValues) =>
                          prevValues.collect_type !== currentValues.collect_type
                        }
                      >
                        {({ getFieldValue }) =>
                          isTrap(getFieldValue) ? null : (
                            <>
                              {enableAlerts.includes('threshold') && (
                                <Form.Item<StrategyFields>
                                  label={
                                    <span className="w-[100px]">
                                      {t('monitor.events.recovery')}
                                    </span>
                                  }
                                >
                                  {t('monitor.events.recoveryCondition')}
                                  <Form.Item
                                    name="recovery_condition"
                                    noStyle
                                    rules={[
                                      {
                                        required: false,
                                        message: t('common.required'),
                                      },
                                    ]}
                                  >
                                    <InputNumber
                                      className="mx-[10px] w-[100px]"
                                      min={1}
                                      precision={0}
                                    />
                                  </Form.Item>
                                  {t('monitor.events.consecutivePeriods')}
                                  <div className="text-[var(--color-text-3)] mt-[10px]">
                                    {t('monitor.events.setRecovery')}
                                  </div>
                                </Form.Item>
                              )}
                              {enableAlerts.includes('no_data') && (
                                <>
                                  <Form.Item<StrategyFields>
                                    name="no_data_period"
                                    label={
                                      <span className="w-[100px]">
                                        {t('monitor.integrations.condition')}
                                      </span>
                                    }
                                    rules={[
                                      {
                                        required: true,
                                        validator: validateNoDataAlert,
                                      },
                                    ]}
                                  >
                                    <div className="flex items-center">
                                      {t('monitor.events.reportedFor')}
                                      <InputNumber
                                        className="mx-[10px]"
                                        min={
                                          SCHEDULE_UNIT_MAP[`${nodataUnit}Min`]
                                        }
                                        max={
                                          SCHEDULE_UNIT_MAP[`${nodataUnit}Max`]
                                        }
                                        value={noDataAlert}
                                        precision={0}
                                        addonAfter={
                                          <Select
                                            value={nodataUnit}
                                            style={{ width: 120 }}
                                            onChange={handleNodataUnitChange}
                                          >
                                            {SCHEDULE_LIST.map((item) => (
                                              <Option
                                                key={item.value}
                                                value={item.value}
                                              >
                                                {item.label}
                                              </Option>
                                            ))}
                                          </Select>
                                        }
                                        onChange={handleNoDataAlertChange}
                                      />
                                      {t('monitor.events.nodataPeriods')}
                                    </div>
                                  </Form.Item>
                                  <Form.Item<StrategyFields>
                                    name="no_data_level"
                                    label={
                                      <span className="w-[100px]">
                                        {t('monitor.events.alarmLevel')}
                                      </span>
                                    }
                                    rules={[
                                      {
                                        required: true,
                                        message: t('common.required'),
                                      },
                                    ]}
                                  >
                                    <Select
                                      style={{
                                        width: '100px',
                                      }}
                                      placeholder={t('monitor.events.level')}
                                    >
                                      {LEVEL_LIST.map((item: ListItem) => (
                                        <Option
                                          value={item.value}
                                          key={item.value}
                                        >
                                          {item.label}
                                        </Option>
                                      ))}
                                    </Select>
                                  </Form.Item>
                                  <Form.Item<StrategyFields>
                                    name="no_data_recovery_period"
                                    label={
                                      <span className="w-[100px]">
                                        {t('monitor.events.noDataRecovery')}
                                      </span>
                                    }
                                    rules={[
                                      {
                                        required: true,
                                        validator: validateNoDataRecoveryAlert,
                                      },
                                    ]}
                                  >
                                    <div className="flex items-center">
                                      {t(
                                        'monitor.events.nodataRecoverCondition'
                                      )}
                                      <InputNumber
                                        className="mx-[10px]"
                                        min={
                                          SCHEDULE_UNIT_MAP[
                                            `${noDataRecoveryUnit}Min`
                                          ]
                                        }
                                        max={
                                          SCHEDULE_UNIT_MAP[
                                            `${noDataRecoveryUnit}Max`
                                          ]
                                        }
                                        value={noDataRecovery}
                                        precision={0}
                                        addonAfter={
                                          <Select
                                            value={noDataRecoveryUnit}
                                            style={{ width: 120 }}
                                            onChange={
                                              handleNodataRecoveryUnitChange
                                            }
                                          >
                                            {SCHEDULE_LIST.map((item) => (
                                              <Option
                                                key={item.value}
                                                value={item.value}
                                              >
                                                {item.label}
                                              </Option>
                                            ))}
                                          </Select>
                                        }
                                        onChange={handleNoDataRecoveryChange}
                                      />
                                      {t('monitor.events.nodataRecover')}
                                    </div>
                                  </Form.Item>
                                </>
                              )}
                            </>
                          )
                        }
                      </Form.Item>
                    </>
                  ),
                  status: 'process',
                },
                {
                  title: t('monitor.events.configureNotifications'),
                  description: (
                    <>
                      <Form.Item<StrategyFields>
                        label={
                          <span className="w-[100px]">
                            {t('monitor.events.notification')}
                          </span>
                        }
                        name="notice"
                      >
                        <Switch />
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(prevValues, currentValues) =>
                          prevValues.notice !== currentValues.notice
                        }
                      >
                        {({ getFieldValue }) =>
                          getFieldValue('notice') ? (
                            <>
                              <Form.Item<StrategyFields>
                                label={
                                  <span className="w-[100px]">
                                    {t('monitor.events.method')}
                                  </span>
                                }
                                name="notice_type_id"
                                rules={[
                                  {
                                    required: true,
                                    message: t('common.required'),
                                  },
                                ]}
                              >
                                {channelList.length ? (
                                  <Radio.Group>
                                    {channelList.map((item) => (
                                      <Radio key={item.id} value={item.id}>
                                        {`${item.name}（${item.channel_type}）`}
                                      </Radio>
                                    ))}
                                  </Radio.Group>
                                ) : (
                                  <span>
                                    {t('monitor.events.noticeWay')}
                                    <Button
                                      type="link"
                                      className="p-0 mx-[4px]"
                                      onClick={linkToSystemManage}
                                    >
                                      {t('monitor.events.systemManage')}
                                    </Button>
                                    {t('monitor.events.config')}
                                  </span>
                                )}
                              </Form.Item>
                              <Form.Item
                                noStyle
                                shouldUpdate={(prevValues, currentValues) =>
                                  prevValues.notice_type_id !==
                                  currentValues.notice_type_id
                                }
                              >
                                {({ getFieldValue }) =>
                                  channelList.find(
                                    (item) =>
                                      item.id ===
                                      getFieldValue('notice_type_id')
                                  )?.channel_type === 'email' ? (
                                      <Form.Item<StrategyFields>
                                        label={
                                          <span className="w-[100px]">
                                            {t('monitor.events.notifier')}
                                          </span>
                                        }
                                        name="notice_users"
                                        rules={[
                                          {
                                            required: true,
                                            message: t('common.required'),
                                          },
                                        ]}
                                      >
                                        <Select
                                          style={{
                                            width: '800px',
                                          }}
                                          showSearch
                                          allowClear
                                          mode="tags"
                                          maxTagCount="responsive"
                                          placeholder={t(
                                            'monitor.events.notifier'
                                          )}
                                        >
                                          {userList.map((item) => (
                                            <Option value={item.id} key={item.id}>
                                              {item.username}
                                            </Option>
                                          ))}
                                        </Select>
                                      </Form.Item>
                                    ) : (
                                      <Form.Item<StrategyFields>
                                        label={
                                          <span className="w-[100px]">
                                            {t('monitor.events.notifier')}
                                          </span>
                                        }
                                        name="notice_users"
                                        rules={[
                                          {
                                            required: true,
                                            message: t('common.required'),
                                          },
                                        ]}
                                      >
                                        <Input
                                          style={{
                                            width: '800px',
                                          }}
                                          placeholder={t(
                                            'monitor.events.notifier'
                                          )}
                                        />
                                      </Form.Item>
                                    )
                                }
                              </Form.Item>
                            </>
                          ) : null
                        }
                      </Form.Item>
                    </>
                  ),
                  status: 'process',
                },
              ]}
            />
          </Form>
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
