'use client';
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Spin, Button, Form, message, Steps } from 'antd';
import useApiClient from '@/utils/request';
import useLogEventApi from '@/app/log/api/event';
import { useTranslation } from '@/utils/i18n';
import { StrategyFields, ChannelItem } from '@/app/log/types/event';
import { FilterItem } from '@/app/log/types/integration';
import { useCommon } from '@/app/log/context/common';
import strategyStyle from '../index.module.scss';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useSearchParams, useRouter } from 'next/navigation';
import { useUserInfoContext } from '@/context/userInfo';
import { ListItem, TableDataItem, UserItem } from '@/app/log/types';
import useLogIntegrationApi from '@/app/log/api/integration';
import BasicInfoForm from './basicInfoForm';
import AlertConditionsForm from './alertConditionsForm';
import NotificationForm from './notificationForm';
import {
  buildStrategyPayload,
  getDefaultShowFields,
  getLockedPolicyType
} from './policyFormUtils';

const StrategyOperation = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getSystemChannelList, getPolicy, createPolicy, updatePolicy } =
    useLogEventApi();
  const { getLogStreams, getFields } = useLogIntegrationApi();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const router = useRouter();
  const userList: UserItem[] = commonContext?.userList || [];
  const userContext = useUserInfoContext();
  const currentGroup = useRef(userContext?.selectedGroup);
  const groupId = [currentGroup?.current?.id || ''];
  const type = searchParams.get('type') || '';
  const detailId = searchParams.get('id') || '';
  const detailName = searchParams.get('name') || '--';
  const urlAlertType = searchParams.get('alert_type');
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
  const lockedAlertType = useMemo(
    () =>
      getLockedPolicyType({
        urlAlertType,
        detailAlertType: formData.alert_type
      }),
    [urlAlertType, formData.alert_type]
  );

  useEffect(() => {
    if (!isLoading) {
      setPageLoading(true);
      Promise.all([
        getAllFields(),
        getChannelList(),
        getGroups(),
        detailId && getStragyDetail()
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
        alert_type: lockedAlertType,
        show_fields: getDefaultShowFields()
      };
      form.setFieldsValue(initForm);
      setTerm('or');
      setConditions([{ op: null, field: null, value: '', func: null }]);
      return;
    }
    dealDetail(formData);
  }, [isEdit, formData, channelList, lockedAlertType]);

  const getChannelList = async () => {
    const data = await getSystemChannelList();
    setChannelList(data);
  };

  const getAllFields = async () => {
    const data = await getFields({
      query: form.getFieldValue('query') || '*',
      log_groups: form.getFieldValue('log_groups') || []
    });
    setFieldList(data || []);
  };

  const getGroups = async () => {
    const data = await getLogStreams({
      page_size: -1,
      page: 1
    });
    setStreamList(data || []);
  };

  const dealDetail = (data: StrategyFields) => {
    const { schedule, period, alert_condition = {}, alert_type } = data;
    const scheduleValue = typeof schedule === 'number' ? schedule : schedule?.value;
    const periodValue = typeof period === 'number' ? period : period?.value;
    const scheduleUnit = typeof schedule === 'number' ? '' : schedule?.type;
    const periodType = typeof period === 'number' ? '' : period?.type;
    const detailData = {
      ...data,
      alert_type: lockedAlertType,
      show_fields: getDefaultShowFields(data.show_fields),
      period: periodValue || '',
      schedule: scheduleValue || '',
      query: alert_condition.query || '',
      group_by: alert_condition.group_by || null
    };
    if (alert_type === 'aggregate') {
      setTerm(alert_condition.rule?.mode || '');
      setConditions(alert_condition.rule?.conditions || []);
    } else {
      setConditions([{ op: null, field: null, value: '', func: null }]);
    }
    form.setFieldsValue(detailData);
    setUnit(scheduleUnit || '');
    setPeriodUnit(periodType || '');
  };

  const getStragyDetail = async () => {
    const data = await getPolicy(detailId);
    setFormData(data);
  };

  const handleUnitChange = (val: string) => {
    setUnit(val);
    form.setFieldsValue({
      schedule: null
    });
  };

  const handlePeriodUnitChange = (val: string) => {
    setPeriodUnit(val);
    form.setFieldsValue({
      period: null
    });
  };

  const handleConditionsChange = (newConditions: FilterItem[]) => {
    setConditions(newConditions);
    form.validateFields(['rule']);
  };

  const handleTermChange = (val: string) => {
    setTerm(val);
    form.validateFields(['rule']);
  };

  const goBack = () => {
    const targetUrl = `/log/event/strategy`;
    router.push(targetUrl);
  };

  const createStrategy = () => {
    form?.validateFields().then((values) => {
      const params = buildStrategyPayload(
        {
          ...values,
          alert_type: lockedAlertType
        },
        {
          unit,
          periodUnit,
          channelList,
          conditions,
          term,
          isEdit,
          formData
        }
      );
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
                  description: <BasicInfoForm />,
                  status: 'process'
                },
                {
                  title: t('log.event.setAlertConditions'),
                  description: (
                    <AlertConditionsForm
                      policyType={lockedAlertType}
                      unit={unit}
                      periodUnit={periodUnit}
                      conditions={conditions}
                      term={term}
                      fieldList={fieldList}
                      streamList={streamList}
                      onUnitChange={handleUnitChange}
                      onPeriodUnitChange={handlePeriodUnitChange}
                      onConditionsChange={handleConditionsChange}
                      onTermChange={handleTermChange}
                    />
                  ),
                  status: 'process'
                },
                {
                  title: t('log.event.configureNotifications'),
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
