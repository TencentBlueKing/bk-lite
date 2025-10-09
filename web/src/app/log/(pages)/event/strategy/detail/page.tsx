'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
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
} from 'antd';
import useApiClient from '@/utils/request';
import useLogEventApi from '@/app/log/api/event';
import { useTranslation } from '@/utils/i18n';
import { useTermList } from '@/app/log/hooks/integration/common/other';
import GroupTreeSelector from '@/components/group-tree-select';
import ConditionSelector from './conditionSelector';
import { StrategyFields, ChannelItem } from '@/app/log/types/event';
import { FilterItem } from '@/app/log/types/integration';
import { useCommon } from '@/app/log/context/common';
import strategyStyle from '../index.module.scss';
import { ArrowLeftOutlined } from '@ant-design/icons';
import SelectCard from './selectCard';
import { useSearchParams, useRouter } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import { SCHEDULE_UNIT_MAP } from '@/app/log/constants';
import {
  useAlgorithmList,
  useScheduleList,
  useLevelList,
} from '@/app/log/hooks/event';
import { ListItem, TableDataItem, UserItem } from '@/app/log/types';
const { Option } = Select;
import useLogIntegrationApi from '@/app/log/api/integration';
import { cloneDeep } from 'lodash';

const StrategyOperation = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getSystemChannelList, getPolicy, createPolicy, updatePolicy } =
    useLogEventApi();
  const { getCollectTypesById, getLogStreams } = useLogIntegrationApi();
  const LEVEL_LIST = useLevelList();
  const SCHEDULE_LIST = useScheduleList();
  const ALGORITHM_LIST = useAlgorithmList();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const router = useRouter();
  const users = useRef(commonContext?.userList || []);
  const TERM_LIST = useTermList();
  const userList: UserItem[] = users.current;
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const objId = Number(searchParams.get('objId'));
  const type = searchParams.get('type') || '';
  const detailId = searchParams.get('id') || '';
  const detailName = searchParams.get('name') || '--';
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [unit, setUnit] = useState<string>('min');
  const [periodUnit, setPeriodUnit] = useState<string>('min');
  const [conditions, setConditions] = useState<FilterItem[]>([]);
  const [term, setTerm] = useState<string | null>(null);
  const [formData, setFormData] = useState<StrategyFields>({});
  const [channelList, setChannelList] = useState<ChannelItem[]>([]);
  const [fieldList, setFieldList] = useState<string[]>([]);
  const [streamList, setStreamList] = useState<ListItem[]>([]);

  const isEdit = useMemo(() => type === 'edit', [type]);

  useEffect(() => {
    if (!isLoading) {
      setPageLoading(true);
      Promise.all([
        getFields(),
        getChannelList(),
        getGroups(),
        detailId && getStragyDetail(),
      ]).finally(() => {
        setPageLoading(false);
      });
    }
  }, [isLoading]);

  useEffect(() => {
    form.resetFields();
    if (!isEdit) {
      const channelItem = channelList[0];
      const initForm: TableDataItem = {
        organizations: groupId,
        notice_type_id: channelItem?.id,
        notice_type: channelItem?.channel_type,
        notice: false,
        period: 5,
        schedule: 5,
        alert_type: 'keyword',
        collect_type: '',
      };
      form.setFieldsValue(initForm);
      setTerm('or');
      setConditions([{ op: null, field: null, value: '', func: null }]);
      return;
    }
    dealDetail(formData);
  }, [isEdit, formData, channelList]);

  const validateConidtion = async () => {
    if (!term || !conditions.length) {
      return Promise.reject(new Error(t('log.event.ruleValidate')));
    }
    if (
      conditions.length &&
      conditions.some((item) => {
        return Object.values(item).some((tex) => !tex);
      })
    ) {
      return Promise.reject(new Error(t('log.event.conditionValidate')));
    }
    return Promise.resolve();
  };

  const getChannelList = async () => {
    const data = await getSystemChannelList();
    setChannelList(data);
  };

  const getFields = async () => {
    const data = await getCollectTypesById({
      collect_type_id: objId,
    });
    const fields = data?.attrs || [];
    setFieldList(fields);
  };

  const getGroups = async () => {
    const data = await getLogStreams({
      page_size: -1,
      page: 1,
    });
    setStreamList(data || []);
  };

  const dealDetail = (data: StrategyFields) => {
    const { schedule, period, alert_condition = {}, alert_type } = data;
    const detailData = {
      ...data,
      period: period?.value || '',
      schedule: schedule?.value || '',
      query: alert_condition.query || '',
      group_by: alert_condition.group_by || null,
    };
    if (alert_type === 'aggregate') {
      setTerm(alert_condition.rule?.mode || '');
      setConditions(alert_condition.rule?.conditions || []);
    } else {
      setConditions([{ op: null, field: null, value: '', func: null }]);
    }
    form.setFieldsValue(detailData);
    setUnit(schedule?.type || '');
    setPeriodUnit(period?.type || '');
  };

  const getStragyDetail = async () => {
    const data = await getPolicy(detailId);
    setFormData(data);
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

  const goBack = () => {
    const targetUrl = `/log/event/strategy?objId=${objId}`;
    router.push(targetUrl);
  };

  const createStrategy = () => {
    form?.validateFields().then((values) => {
      const params = cloneDeep(values);
      params.collect_type = objId;
      params.schedule = {
        type: unit,
        value: values.schedule,
      };
      params.period = {
        type: periodUnit,
        value: values.period,
      };
      if (params.notice_type_id) {
        params.notice_type =
          channelList.find((item) => item.id === params.notice_type_id)
            ?.channel_type || '';
      }
      params.alert_condition = {
        query: params.query,
      };
      if (params.alert_type === 'aggregate') {
        params.alert_condition.group_by = params.group_by;
        params.alert_condition.rule = {
          mode: term,
          conditions,
        };
      }
      if (isEdit) {
        params.id = formData.id;
      } else {
        params.enable = true;
      }
      operateStrategy(params);
    });
  };

  const operateStrategy = async (params: StrategyFields) => {
    try {
      setConfirmLoading(true);
      const msg: string = t(
        isEdit ? 'common.successfullyModified' : 'common.successfullyAdded'
      );
      const request = isEdit ? updatePolicy : createPolicy;
      await request(params);
      message.success(msg);
      goBack();
    } catch (error) {
      console.log(error);
    } finally {
      setConfirmLoading(false);
    }
  };

  const linkToSystemManage = () => {
    const url = '/system-manager/channel';
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <Spin spinning={pageLoading} className="w-full">
      <div className={strategyStyle.strategy}>
        <div className={strategyStyle.title}>
          <ArrowLeftOutlined
            className="text-[var(--color-primary)] text-[20px] cursor-pointer mr-[10px]"
            onClick={goBack}
          />
          {isEdit ? (
            <span>
              {t('log.event.editPolicy')} -{' '}
              <span className="text-[var(--color-text-3)] text-[12px]">
                {detailName}
              </span>
            </span>
          ) : (
            t('log.event.createPolicy')
          )}
        </div>
        <div className={strategyStyle.form}>
          <Form form={form} name="basic">
            <Steps
              direction="vertical"
              items={[
                {
                  title: t('log.event.basicInformation'),
                  description: (
                    <>
                      <Form.Item<StrategyFields>
                        label={
                          <span className="w-[100px]">
                            {t('log.event.strategyName')}
                          </span>
                        }
                        name="name"
                        rules={[
                          { required: true, message: t('common.required') },
                        ]}
                      >
                        <Input
                          placeholder={t('log.event.strategyName')}
                          className="w-[800px]"
                        />
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        label={
                          <span className="w-[100px]">
                            {t('common.organizations')}
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
                          placeholder={t('common.organizations')}
                        />
                      </Form.Item>
                    </>
                  ),
                  status: 'process',
                },
                {
                  title: t('log.event.setAlertConditions'),
                  description: (
                    <>
                      <Form.Item<StrategyFields>
                        name="alert_type"
                        label={
                          <span className="w-[100px]">
                            {t('log.event.algorithm')}
                          </span>
                        }
                        rules={[
                          { required: true, message: t('common.required') },
                        ]}
                      >
                        <SelectCard data={ALGORITHM_LIST} />
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('log.event.alertName')}
                          </span>
                        }
                        shouldUpdate={(prevValues, currentValues) =>
                          prevValues.alert_type !== currentValues.alert_type
                        }
                      >
                        {({ getFieldValue }) => (
                          <>
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
                                placeholder={t('log.event.alertName')}
                                className="w-[800px]"
                              />
                            </Form.Item>
                            <div className="text-[var(--color-text-3)] mt-[10px]">
                              {getFieldValue('alert_type') === 'aggregate'
                                ? t('log.event.alertNameTitle')
                                : t('log.event.keyWordAlertNameTitle')}
                            </div>
                          </>
                        )}
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('log.integration.logGroup')}
                          </span>
                        }
                      >
                        <Form.Item
                          name="log_groups"
                          noStyle
                          rules={[
                            { required: true, message: t('common.required') },
                          ]}
                        >
                          <Select
                            style={{ width: 800 }}
                            showSearch
                            mode="multiple"
                            maxTagCount="responsive"
                            placeholder={t('log.integration.logGroup')}
                            options={streamList.map((item: ListItem) => ({
                              value: item.id,
                              label: item.name,
                            }))}
                          ></Select>
                        </Form.Item>
                        <div className="text-[var(--color-text-3)] mt-[10px]">
                          {t('log.integration.logGroupTips')}
                        </div>
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('log.event.queryCriteria')}
                          </span>
                        }
                      >
                        <Form.Item
                          name="query"
                          noStyle
                          rules={[
                            { required: true, message: t('common.required') },
                          ]}
                        >
                          <Input
                            placeholder={t('common.inputMsg')}
                            className="w-[800px]"
                            allowClear
                          />
                        </Form.Item>
                        <div className="text-[var(--color-text-3)] mt-[10px]">
                          {t('log.event.queryCriteriaTips')}
                        </div>
                      </Form.Item>
                      <Form.Item
                        noStyle
                        shouldUpdate={(prevValues, currentValues) =>
                          prevValues.alert_type !== currentValues.alert_type
                        }
                      >
                        {({ getFieldValue }) =>
                          getFieldValue('alert_type') === 'aggregate' ? (
                            <>
                              <Form.Item<StrategyFields>
                                required
                                label={
                                  <span className="w-[100px]">
                                    {t('log.event.polymerizationConditions')}
                                  </span>
                                }
                              >
                                <Form.Item
                                  name="group_by"
                                  noStyle
                                  rules={[
                                    {
                                      required: true,
                                      message: t('common.required'),
                                    },
                                  ]}
                                >
                                  <Select
                                    style={{ width: 800 }}
                                    allowClear
                                    showSearch
                                    mode="multiple"
                                    maxTagCount="responsive"
                                  >
                                    {fieldList.map((item) => (
                                      <Option key={item} value={item}>
                                        {item}
                                      </Option>
                                    ))}
                                  </Select>
                                </Form.Item>
                                <div className="text-[var(--color-text-3)] mt-[10px]">
                                  {t('log.event.polymerizationConditionsDes')}
                                </div>
                              </Form.Item>
                              <Form.Item<StrategyFields>
                                required
                                label={
                                  <span className="w-[100px]">
                                    {t('log.integration.rule')}
                                  </span>
                                }
                              >
                                <Form.Item
                                  name="rule"
                                  noStyle
                                  rules={[
                                    {
                                      validator: validateConidtion,
                                      required: true,
                                    },
                                  ]}
                                >
                                  <div className="flex items-center mb-[20px] w-[800px]">
                                    <span>{t('log.integration.meetRule')}</span>
                                    <Select
                                      className="ml-[8px] flex-1"
                                      placeholder={t('log.integration.rule')}
                                      showSearch
                                      value={term}
                                      onChange={(val) => setTerm(val)}
                                    >
                                      {TERM_LIST.map((item: ListItem) => (
                                        <Option
                                          value={item.value}
                                          key={item.value}
                                        >
                                          {item.name}
                                        </Option>
                                      ))}
                                    </Select>
                                  </div>
                                  <ConditionSelector
                                    fields={fieldList}
                                    data={conditions}
                                    onChange={(val) => setConditions(val)}
                                  ></ConditionSelector>
                                </Form.Item>
                              </Form.Item>
                            </>
                          ) : (
                            <Form.Item<StrategyFields>
                              required
                              label={
                                <span className="w-[100px]">
                                  {t('log.event.displayFields')}
                                </span>
                              }
                            >
                              <Form.Item
                                name="show_fields"
                                noStyle
                                rules={[
                                  {
                                    required: true,
                                    message: t('common.required'),
                                  },
                                ]}
                              >
                                <Select
                                  style={{ width: 800 }}
                                  showSearch
                                  mode="multiple"
                                  maxTagCount="responsive"
                                  options={fieldList
                                    .filter(
                                      (item) =>
                                        ![
                                          'message',
                                          'timestamp',
                                          '_time',
                                          '_msg',
                                        ].includes(item)
                                    )
                                    .map((item) => ({
                                      value: item,
                                      label: item,
                                    }))}
                                />
                              </Form.Item>
                              <div className="text-[var(--color-text-3)] mt-[10px]">
                                {t('log.event.displayFieldsDes')}
                              </div>
                            </Form.Item>
                          )
                        }
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('log.event.frequency')}
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
                          {t('log.event.setFrequency')}
                        </div>
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        required
                        label={
                          <span className="w-[100px]">
                            {t('log.event.period')}
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
                          {t('log.event.setPeriod')}
                        </div>
                      </Form.Item>
                      <Form.Item<StrategyFields>
                        name="alert_level"
                        label={
                          <span className="w-[100px]">
                            {t('log.event.alarmLevel')}
                          </span>
                        }
                        rules={[
                          {
                            required: true,
                            message: t('common.required'),
                          },
                        ]}
                      >
                        <Radio.Group>
                          {LEVEL_LIST.map((item) => (
                            <Radio key={item.value} value={item.value}>
                              {item.label}
                            </Radio>
                          ))}
                        </Radio.Group>
                      </Form.Item>
                    </>
                  ),
                  status: 'process',
                },
                {
                  title: t('log.event.configureNotifications'),
                  description: (
                    <>
                      <Form.Item<StrategyFields>
                        label={
                          <span className="w-[100px]">
                            {t('log.event.notification')}
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
                                    {t('log.event.method')}
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
                                    {t('log.event.noticeWay')}
                                    <Button
                                      type="link"
                                      className="p-0 mx-[4px]"
                                      onClick={linkToSystemManage}
                                    >
                                      {t('log.event.systemManage')}
                                    </Button>
                                    {t('log.event.config')}
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
                                            {t('log.event.notifier')}
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
                                          mode="multiple"
                                          maxTagCount="responsive"
                                          placeholder={t('log.event.notifier')}
                                        >
                                          {userList.map((item) => (
                                            <Option value={item.id} key={item.id}>
                                              {item.display_name || item.username}
                                            </Option>
                                          ))}
                                        </Select>
                                      </Form.Item>
                                    ) : (
                                      <Form.Item<StrategyFields>
                                        label={
                                          <span className="w-[100px]">
                                            {t('log.event.notifier')}
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
                                          placeholder={t('log.event.notifier')}
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
    </Spin>
  );
};

export default StrategyOperation;
