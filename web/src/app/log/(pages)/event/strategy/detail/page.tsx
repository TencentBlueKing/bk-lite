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
import { cloneDeep } from 'lodash';
import BasicInfoForm from './basicInfoForm';
import AlertConditionsForm from './alertConditionsForm';
import NotificationForm from './notificationForm';

const StrategyOperation = () => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getSystemChannelList, getPolicy, createPolicy, updatePolicy } =
    useLogEventApi();
  const { getCollectTypesById, getLogStreams } = useLogIntegrationApi();
  const commonContext = useCommon();
  const searchParams = useSearchParams();
  const [form] = Form.useForm();
  const router = useRouter();
  const users = useRef(commonContext?.userList || []);
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
                  description: <BasicInfoForm />,
                  status: 'process',
                },
                {
                  title: t('log.event.setAlertConditions'),
                  description: (
                    <AlertConditionsForm
                      unit={unit}
                      periodUnit={periodUnit}
                      conditions={conditions}
                      term={term}
                      fieldList={fieldList}
                      streamList={streamList}
                      onUnitChange={handleUnitChange}
                      onPeriodUnitChange={handlePeriodUnitChange}
                      onConditionsChange={setConditions}
                      onTermChange={setTerm}
                    />
                  ),
                  status: 'process',
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
