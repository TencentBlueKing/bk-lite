'use client';
import React, { useRef, useState } from 'react';
import { Descriptions } from 'antd';
import { TableDataItem, Organization, UserItem } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';
import informationStyle from './index.module.scss';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import LineChart from '@/app/monitor/components/charts/lineChart';
import { ObjectItem } from '@/app/monitor/types';
import { findUnitNameById, showGroupName } from '@/app/monitor/utils/common';
import { useCommon } from '@/app/monitor/context/common';
import { Popconfirm, message, Button } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import { useLevelList } from '@/app/monitor/hooks';
import { OBJECT_DEFAULT_ICON, LEVEL_MAP } from '@/app/monitor/constants';
import Permission from '@/components/permission';

interface InformationProps extends TableDataItem {
  eventData?: TableDataItem[];
}

const Information: React.FC<InformationProps> = ({
  formData,
  chartData,
  objects,
  userList,
  onClose,
  trapData,
  eventData = [],
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const LEVEL_LIST = useLevelList();
  const { patchMonitorAlert } = useMonitorApi();
  const commonContext = useCommon();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const [confirmLoading, setConfirmLoading] = useState(false);

  const checkDetail = (row: TableDataItem) => {
    const monitorItem = objects.find(
      (item: ObjectItem) => item.id === row.policy?.monitor_object
    );
    const params = {
      monitorObjId: row.policy?.monitor_object,
      name: monitorItem?.name || '',
      monitorObjDisplayName: monitorItem?.display_name || '',
      icon: monitorItem?.icon || OBJECT_DEFAULT_ICON,
      instance_id: row.monitor_instance_id,
      instance_name: row.monitor_instance_name,
      instance_id_values: row.instance_id_values,
    };
    const queryString = new URLSearchParams(params).toString();
    const url = `/monitor/view/detail?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleCloseConfirm = async (row: TableDataItem) => {
    setConfirmLoading(true);
    try {
      await patchMonitorAlert(row.id as string, {
        status: 'closed',
      });
      message.success(t('monitor.events.successfullyClosed'));
      onClose();
    } finally {
      setConfirmLoading(false);
    }
  };

  const getUsers = (id: string) => {
    return userList.find((item: UserItem) => item.id === id)?.username || '--';
  };

  const showNotifiers = (row: TableDataItem) => {
    return (
      (row.policy?.notice_users || [])
        .map((item: string) => getUsers(item))
        .join(',') || '--'
    );
  };

  return (
    <div className={informationStyle.information}>
      <Descriptions title={t('monitor.events.information')} column={2} bordered>
        <Descriptions.Item label={t('common.time')}>
          {formData.updated_at
            ? convertToLocalizedTime(formData.updated_at)
            : '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.events.level')}>
          <div
            className={informationStyle.level}
            style={{
              borderLeft: `4px solid ${LEVEL_MAP[formData.level]}`,
            }}
          >
            <span
              style={{
                color: LEVEL_MAP[formData.level] as string,
              }}
            >
              {LEVEL_LIST.find((item) => item.value === formData.level)
                ?.label || '--'}
            </span>
          </div>
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.events.firstAlertTime')}>
          {formData.start_event_time
            ? convertToLocalizedTime(formData.start_event_time)
            : '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.events.information')} span={3}>
          {formData.content || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.events.assetType')}>
          {objects.find(
            (item: ObjectItem) => item.id === formData.policy?.monitor_object
          )?.display_name || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.asset')}>
          <div className="flex justify-between">
            {formData.monitor_instance_name || '--'}
            <a
              href="#"
              className="text-blue-500 w-[36px]"
              onClick={() => checkDetail(formData)}
            >
              {t('common.more')}
            </a>
          </div>
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.events.assetGroup')}>
          {showGroupName(
            formData.policy?.organizations || [],
            organizationList
          )}
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.events.strategyName')}>
          {formData.policy?.name || '--'}
        </Descriptions.Item>
        {formData.status === 'closed' && (
          <Descriptions.Item label={t('monitor.events.alertEndTime')}>
            {formData.end_event_time
              ? convertToLocalizedTime(formData.end_event_time)
              : '--'}
          </Descriptions.Item>
        )}
        <Descriptions.Item label={t('monitor.events.notify')}>
          {t(
            `monitor.events.${
              formData.policy?.notice ? 'notified' : 'unnotified'
            }`
          )}
        </Descriptions.Item>
        <Descriptions.Item label={t('common.operator')}>
          {formData.operator || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('monitor.events.notifier')}>
          {showNotifiers(formData)}
        </Descriptions.Item>
      </Descriptions>
      <div className="mt-4">
        <Permission
          requiredPermissions={['Operate', 'Detail']}
          instPermissions={formData.permission}
        >
          <Popconfirm
            title={t('monitor.events.closeTitle')}
            description={t('monitor.events.closeContent')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            okButtonProps={{ loading: confirmLoading }}
            onConfirm={() => handleCloseConfirm(formData)}
          >
            <Button type="link" disabled={formData.status !== 'new'}>
              {t('monitor.events.closeAlert')}
            </Button>
          </Popconfirm>
        </Permission>
      </div>
      <div className="mt-4">
        {formData.policy?.query_condition?.type === 'pmq' ? (
          <div>
            <h3 className="font-[600] text-[16px] mb-[15px]">
              {t('monitor.events.message')}
            </h3>
            <div className="leading-[24px]">
              {/* 报文表格 */}
              <Descriptions column={2} bordered>
                {Object.entries<string | Array<string>>(trapData).map(
                  ([key, value]) => {
                    return (
                      <Descriptions.Item label={key} key={key}>
                        {Array.isArray(value)
                          ? value[0]?.[1] ?? '--'
                          : value ?? '--'}
                      </Descriptions.Item>
                    );
                  }
                )}
              </Descriptions>
            </div>
          </div>
        ) : (
          <div>
            <h3 className="font-[600] text-[16px] mb-[15px]">
              {t('monitor.views.indexView')}
            </h3>
            <div className="text-[12px]">{`${
              formData.metric?.display_name
            }（${findUnitNameById(formData.metric?.unit)}）`}</div>
            <div className="h-[250px]">
              <LineChart
                allowSelect={false}
                eventData={eventData}
                data={chartData}
                threshold={formData.policy?.threshold}
                unit={formData.metric?.unit}
                metric={formData.metric}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Information;
