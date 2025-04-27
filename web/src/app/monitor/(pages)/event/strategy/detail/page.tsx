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
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  Organization,
  ListItem,
  UserItem,
  SegmentedItem,
  TableDataItem,
} from '@/app/monitor/types';
import CustomCascader from '@/components/custom-cascader';
import {
  StrategyFields,
  SourceFeild,
  MetricItem,
  FilterItem,
  ThresholdField,
  PluginItem,
  IndexViewItem,
  GroupInfo,
  ChannelItem,
} from '@/app/monitor/types/monitor';
import { useCommon } from '@/app/monitor/context/common';
import { deepClone } from '@/app/monitor/utils/common';
import strategyStyle from '../index.module.scss';
import {
  PlusOutlined,
  CloseOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import SelectAssets from '../selectAssets';
import { useSearchParams, useRouter } from 'next/navigation';
import { useConditionList } from '@/app/monitor/constants/monitor';
import { useUserInfoContext } from '@/context/userInfo';
import {
  useScheduleList,
  COMPARISON_METHOD,
  useMethodList,
  LEVEL_MAP,
  useLevelList,
  SCHEDULE_UNIT_MAP,
  MONITOR_GROUPS_MAP,
  OBJECT_ICON_MAP,
  COLLECT_TYPE_MAP,
} from '@/app/monitor/constants/monitor';
const { Option } = Select;
import Icon from '@/components/icon';
const defaultGroup = ['instance_id'];
const { TextArea } = Input;

const StrategyOperation = () => {
  const { t } = useTranslation();
  const { get, post, put, isLoading } = useApiClient();
  const CONDITION_LIST = useConditionList();
  const METHOD_LIST = useMethodList();
  const LEVEL_LIST = useLevelList();
  const SCHEDULE_LIST = useScheduleList();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const router = useRouter();
  const authList = useRef(commonContext?.authOrganizations || []);
  const users = useRef(commonContext?.userList || []);
  const organizationList: Organization[] = authList.current;
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
  const [openNoData, setOpenNoData] = useState<boolean>(false);
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
  const [conditions, setConditions] = useState<FilterItem[]>([]);
  const [noDataAlert, setNoDataAlert] = useState<number | null>(null);
  const [noDataLevel, setNoDataLevel] = useState<string>();
  const [groupBy, setGroupBy] = useState<string[]>(
    MONITOR_GROUPS_MAP[monitorName as string]?.default || defaultGroup
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

  useEffect(() => {
    if (!isLoading) {
      setPageLoading(true);
      Promise.all([
        getPlugins(),
        getChannelList(),
        detailId && getStragyDetail(),
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
    const data = await get('/monitor/api/system_mgmt/search_channel_list/');
    setChannelList(data);
  };

  const getPlugins = async () => {
    const data = await get('/monitor/api/monitor_plugin/', {
      params: {
        monitor_object_id: monitorObjId,
      },
    });
    const plugins = data.map((item: PluginItem) => ({
      label: COLLECT_TYPE_MAP[item.name || ''],
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
      no_data_level,
      recovery_condition,
      group_by,
      query_condition,
      collect_type,
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
    setNoDataLevel(no_data_level || '');
    setOpenNoData(!!no_data_period?.value);
    setUnit(schedule?.type || '');
    setPeriodUnit(period?.type || '');
  };

  const feedbackThreshold = (data: TableDataItem) => {
    const _threshold = deepClone(threshold);
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
      form: {},
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
    if (
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

  const validateNoData = async () => {
    if (openNoData && (!noDataAlert || !noDataLevel)) {
      return Promise.reject(new Error(t('monitor.events.conditionValidate')));
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
      const getGroupList = get(`/monitor/api/metrics_group/`, { params });
      const getMetrics = get('/monitor/api/metrics/', { params });
      Promise.all([getGroupList, getMetrics])
        .then((res) => {
          const metricData = deepClone(res[1] || []);
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
    const data = await get(`/monitor/api/monitor_policy/${detailId}/`);
    setFormData(data);
  };

  const handleLabelChange = (val: string, index: number) => {
    const _conditions = deepClone(conditions);
    _conditions[index].name = val;
    setConditions(_conditions);
  };

  const handleGroupByChange = (val: string[]) => {
    setGroupBy(val);
  };

  const handleConditionChange = (val: string, index: number) => {
    const _conditions = deepClone(conditions);
    _conditions[index].method = val;
    setConditions(_conditions);
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

  const handleThresholdMethodChange = (val: string, index: number) => {
    const _conditions = deepClone(threshold);
    _conditions[index].method = val;
    setThreshold(_conditions);
  };

  const handleValueChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    index: number
  ) => {
    const _conditions = deepClone(conditions);
    _conditions[index].value = e.target.value;
    setConditions(_conditions);
  };

  const handleNoDataAlertChange = (e: number | null) => {
    setNoDataAlert(e);
  };

  const handleThresholdValueChange = (e: number | null, index: number) => {
    const _conditions = deepClone(threshold);
    _conditions[index].value = e;
    setThreshold(_conditions);
  };

  const addConditionItem = () => {
    const _conditions = deepClone(conditions);
    _conditions.push({
      name: null,
      method: null,
      value: '',
    });
    setConditions(_conditions);
  };

  const deleteConditionItem = (index: number) => {
    const _conditions = deepClone(conditions);
    _conditions.splice(index, 1);
    setConditions(_conditions);
  };

  const handleNoDataChange = (bool: boolean) => {
    setOpenNoData(bool);
    setNoDataAlert(null);
    setNoDataLevel('');
  };

  const goBack = () => {
    const targetUrl = `/monitor/event/${type === 'builtIn' ? 'template' : 'strategy'}?objId=${monitorObjId}`;
    router.push(targetUrl);
  };

  const createStrategy = () => {
    form?.validateFields().then((values) => {
      const _values = deepClone(values);
      const target: any = pluginList.find(
        (item) => item.value === _values.collect_type
      );
      const isTrapPlugin = target?.name === 'SNMP Trap';
      if (isTrapPlugin) {
        _values.query_condition = {
          type: 'pmq',
          query: _values.query,
        };
        _values.source = {};
        _values.algorithm = 'last_over_time';
      } else {
        _values.query_condition = {
          type: 'metric',
          metric_id: metrics.find((item) => item.name === metric)?.id,
          filter: conditions,
        };
        _values.source = source;
      }
      _values.threshold = threshold.filter(
        (item) => !!item.value || item.value === 0
      );
      _values.monitor_object = monitorObjId;
      _values.schedule = {
        type: unit,
        value: values.schedule,
      };
      _values.period = {
        type: periodUnit,
        value: values.period,
      };
      if (openNoData) {
        _values.no_data_period = _values.no_data_recovery_period = {
          type: nodataUnit,
          value: noDataAlert,
        };
        _values.no_data_level = noDataLevel;
      } else {
        _values.no_data_period = _values.no_data_recovery_period = {};
      }
      if (_values.notice_type_id) {
        _values.notice_type =
          channelList.find((item) => item.id === _values.notice_type_id)
            ?.channel_type || '';
      }
      _values.recovery_condition = _values.recovery_condition || 0;
      _values.group_by = groupBy;
      _values.enable = true;
      operateStrategy(_values);
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
                          className="w-[300px]"
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
                            className="w-[300px]"
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
                        <CustomCascader
                          style={{
                            width: '300px',
                          }}
                          multiple
                          placeholder={t('common.group')}
                          className="mr-[8px]"
                          showSearch
                          maxTagCount="responsive"
                          options={organizationList}
                          allowClear
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
                                <div className={strategyStyle.condition}>
                                  <Select
                                    allowClear
                                    style={{
                                      width: '300px',
                                      margin: '0 20px 10px 0',
                                    }}
                                    placeholder={t('monitor.metric')}
                                    showSearch
                                    value={metric}
                                    loading={metricsLoading}
                                    options={originMetricData.map((item) => ({
                                      label: item.display_name,
                                      title: item.name,
                                      options: (item.child || []).map(
                                        (tex) => ({
                                          label: tex.display_name,
                                          value: tex.name,
                                        })
                                      ),
                                    }))}
                                    onChange={handleMetricChange}
                                  />
                                  <div className={strategyStyle.conditionItem}>
                                    {conditions.length ? (
                                      <ul className={strategyStyle.conditions}>
                                        <li
                                          className={
                                            strategyStyle.conditionTitle
                                          }
                                        >
                                          <span>{t('monitor.filter')}</span>
                                        </li>
                                        {conditions.map(
                                          (conditionItem, index) => (
                                            <li
                                              className={`${strategyStyle.itemOption} ${strategyStyle.filter}`}
                                              key={index}
                                            >
                                              <Select
                                                className={
                                                  strategyStyle.filterLabel
                                                }
                                                placeholder={t('monitor.label')}
                                                showSearch
                                                value={conditionItem.name}
                                                onChange={(val) =>
                                                  handleLabelChange(val, index)
                                                }
                                              >
                                                {labels.map((item) => (
                                                  <Option
                                                    value={item}
                                                    key={item}
                                                  >
                                                    {item}
                                                  </Option>
                                                ))}
                                              </Select>
                                              <Select
                                                style={{
                                                  width: '100px',
                                                }}
                                                placeholder={t('monitor.term')}
                                                value={conditionItem.method}
                                                onChange={(val) =>
                                                  handleConditionChange(
                                                    val,
                                                    index
                                                  )
                                                }
                                              >
                                                {CONDITION_LIST.map(
                                                  (item: ListItem) => (
                                                    <Option
                                                      value={item.id}
                                                      key={item.id}
                                                    >
                                                      {item.name}
                                                    </Option>
                                                  )
                                                )}
                                              </Select>
                                              <Input
                                                style={{
                                                  width: '150px',
                                                }}
                                                placeholder={t('monitor.value')}
                                                value={conditionItem.value}
                                                onChange={(e) =>
                                                  handleValueChange(e, index)
                                                }
                                              ></Input>
                                              <Button
                                                icon={<CloseOutlined />}
                                                onClick={() =>
                                                  deleteConditionItem(index)
                                                }
                                              />
                                              <Button
                                                icon={<PlusOutlined />}
                                                onClick={addConditionItem}
                                              />
                                            </li>
                                          )
                                        )}
                                      </ul>
                                    ) : (
                                      <div className="flex items-center mr-[20px]">
                                        <span className="mr-[10px]">
                                          {t('monitor.filter')}
                                        </span>
                                        <Button
                                          disabled={!metric}
                                          icon={<PlusOutlined />}
                                          onClick={addConditionItem}
                                        />
                                      </div>
                                    )}
                                  </div>
                                  <div>
                                    <span className="mr-[10px]">
                                      {t('common.group')}
                                    </span>
                                    <Select
                                      allowClear
                                      style={{
                                        width: '300px',
                                        margin: '0 10px 10px 0',
                                      }}
                                      mode="tags"
                                      maxTagCount="responsive"
                                      placeholder={t('common.group')}
                                      value={groupBy}
                                      onChange={handleGroupByChange}
                                    >
                                      {(
                                        MONITOR_GROUPS_MAP[
                                          monitorName as string
                                        ]?.list || defaultGroup
                                      ).map((item) => (
                                        <Option value={item} key={item}>
                                          {item}
                                        </Option>
                                      ))}
                                    </Select>
                                  </div>
                                </div>
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
                        <div className="w-[220px] bg-[var(--color-bg-1)] border-2 border-blue-300 shadow-md transition-shadow duration-300 ease-in-out rounded-lg p-3 relative cursor-pointer group">
                          <div className="flex items-center space-x-4 my-1">
                            <Icon
                              type={OBJECT_ICON_MAP[monitorName as string]}
                              className="text-2xl"
                            />
                            <h2 className="text-[16px] font-bold m-0">
                              {t('monitor.events.threshold')}
                            </h2>
                          </div>
                          <p
                            className={`text-[var(--color-text-3)] text-[13px]`}
                          >
                            {t('monitor.events.setThreshold')}
                          </p>
                        </div>
                        {threshold.map((item, index) => (
                          <div
                            key={item.level}
                            className="bg-[var(--color-bg-1)] border shadow-sm p-3 mt-[10px] w-[800px]"
                          >
                            <div
                              className="flex items-center space-x-4 my-1 font-[800]"
                              style={{
                                borderLeft: `4px solid ${
                                  LEVEL_MAP[item.level]
                                }`,
                                paddingLeft: '10px',
                              }}
                            >
                              {t(`monitor.events.${item.level}`)}
                            </div>
                            <div className="flex items-center">
                              <span className="mr-[10px]">
                                {t('monitor.events.whenResultIs')}
                              </span>
                              <Select
                                className={strategyStyle.filterLabel}
                                style={{
                                  width: '100px',
                                }}
                                value={item.method}
                                placeholder={t('monitor.events.method')}
                                onChange={(val) => {
                                  handleThresholdMethodChange(val, index);
                                }}
                              >
                                {COMPARISON_METHOD.map((item: ListItem) => (
                                  <Option value={item.value} key={item.value}>
                                    {item.label}
                                  </Option>
                                ))}
                              </Select>
                              <InputNumber
                                style={{
                                  width: '200px',
                                  borderRadius: '0 6px 6px 0',
                                }}
                                min={0}
                                value={item.value}
                                onChange={(e) =>
                                  handleThresholdValueChange(e, index)
                                }
                              />
                            </div>
                          </div>
                        ))}
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
                              <Form.Item<StrategyFields>
                                name="no_data_period"
                                label={
                                  <span className="w-[100px]">
                                    {t('monitor.events.nodata')}
                                  </span>
                                }
                                rules={[
                                  { required: true, validator: validateNoData },
                                ]}
                              >
                                <Switch
                                  checked={openNoData}
                                  onChange={handleNoDataChange}
                                />
                                {openNoData && (
                                  <div className="mt-[10px]">
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
                                    <Select
                                      value={noDataLevel}
                                      style={{
                                        width: '100px',
                                        margin: '0 10px',
                                      }}
                                      placeholder={t('monitor.events.level')}
                                      onChange={(val: string) =>
                                        setNoDataLevel(val)
                                      }
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
                                    {t('monitor.events.nodataRecoverCondition')}
                                    {` ${noDataAlert || ''} ${SCHEDULE_LIST.find((item) => item.value === nodataUnit)?.label} `}
                                    {t('monitor.events.nodataRecover')}
                                  </div>
                                )}
                              </Form.Item>
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
                        rules={[
                          { required: true, message: t('common.required') },
                        ]}
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
                                <Radio.Group>
                                  {channelList.map((item) => (
                                    <Radio key={item.id} value={item.id}>
                                      {`${item.name}（${item.channel_type}）`}
                                    </Radio>
                                  ))}
                                </Radio.Group>
                              </Form.Item>
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
                                    width: '300px',
                                  }}
                                  showSearch
                                  allowClear
                                  mode="tags"
                                  maxTagCount="responsive"
                                  placeholder={t('monitor.events.notifier')}
                                >
                                  {userList.map((item) => (
                                    <Option value={item.id} key={item.id}>
                                      {item.username}
                                    </Option>
                                  ))}
                                </Select>
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
        organizationList={organizationList}
        form={source}
        monitorObject={monitorObjId}
        onSuccess={onChooseAssets}
      />
    </Spin>
  );
};

export default StrategyOperation;
