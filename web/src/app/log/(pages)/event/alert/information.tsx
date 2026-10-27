'use client';
import React, { useMemo } from 'react';
import { Descriptions } from 'antd';
import {
  TableDataItem,
  Organization
} from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import informationStyle from './index.module.scss';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { showGroupName } from '@/app/log/utils/common';
import { useCommon } from '@/app/log/context/common';
import { Button } from 'antd';
import { LEVEL_MAP } from '@/app/log/constants';
import { useLevelList } from '@/app/log/hooks/event';
import CustomTable from '@/components/custom-table';
import { buildLogAlertRawColumns } from './rawLogColumns';
import { formatUserDisplayName } from '@/utils/userDisplay';
import AlertHandlerActions from './alertHandlerActions';
import useLogEventApi from '@/app/log/api/event';
import { buildSearchJumpUrl } from './buildSearchJumpUrl';
import { formatAlertHandlers } from './alertHandlerUtils';
import { AggregateHitSummary } from '@/app/log/components/aggregateConditionHit';

const Information: React.FC<TableDataItem> = ({
  formData,
  userList,
  onClose,
  rawData = [],
  aggregateResult
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const LEVEL_LIST = useLevelList();
  const commonContext = useCommon();
  const { getAlertSnapshots } = useLogEventApi();
  const organizationList: Organization[] =
    commonContext?.authOrganizations || [];

  const isAggregate = useMemo(
    () => formData.alert_type === 'aggregate',
    [formData]
  );

  const isClosed = useMemo(() => formData.status === 'closed', [formData]);

  const activeColumns = useMemo(() => {
    return buildLogAlertRawColumns({
      isAggregate,
      showFields: formData.show_fields,
      rawData,
      renderTime: convertToLocalizedTime
    });
  }, [convertToLocalizedTime, formData.show_fields, isAggregate, rawData]);

  const checkDetail = async () => {
    const logGroups = Array.isArray(formData.log_groups)
      ? formData.log_groups.filter(Boolean)
      : [];
    let jumpQuery: { query?: string; window_start?: number; window_end?: number } | null = null;
    if (formData.id) {
      try {
        const payload = await getAlertSnapshots(formData.id);
        const snapshots = Array.isArray(payload?.snapshots) ? payload.snapshots : [];
        for (let index = snapshots.length - 1; index >= 0; index -= 1) {
          const jump = snapshots[index]?.jump_query;
          if (jump?.query) {
            jumpQuery = jump;
            break;
          }
        }
      } catch {
        jumpQuery = null;
      }
    }
    const url = buildSearchJumpUrl({
      jumpQuery,
      fallbackQuery: (formData.alert_condition?.query as string) || '',
      fallbackStart: String(
        +new Date(convertToLocalizedTime(formData.start_event_time))
      ),
      fallbackEnd: String(
        isClosed
          ? +new Date(convertToLocalizedTime(formData.end_event_time))
          : +new Date()
      ),
      logGroups,
    });
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const showNotifiers = (row: TableDataItem) => {
    return (
      (row.notice_users || [])
        .map((item: string) => formatUserDisplayName(item, userList))
        .join(',') || '--'
    );
  };

  return (
    <div className={informationStyle.information}>
      <Descriptions title={t('log.event.information')} column={2} bordered>
        <Descriptions.Item label={t('common.time')}>
          {formData.updated_at
            ? convertToLocalizedTime(formData.updated_at)
            : '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.level')}>
          <div
            className={informationStyle.level}
            style={{
              borderLeft: `4px solid ${LEVEL_MAP[formData.level]}`
            }}
          >
            <span
              style={{
                color: LEVEL_MAP[formData.level] as string
              }}
            >
              {LEVEL_LIST.find((item) => item.value === formData.level)
                ?.label || '--'}
            </span>
          </div>
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.firstAlertTime')}>
          {formData.start_event_time
            ? convertToLocalizedTime(formData.start_event_time)
            : '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.integration.collectType')} span={3}>
          {formData.collect_type_name || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.alertType')}>
          {isAggregate
            ? t('log.event.aggregationAlert')
            : t('log.event.keywordAlert')}
        </Descriptions.Item>
        {isAggregate && (
          <Descriptions.Item label={t('log.event.aggregateFields')}>
            {(formData.alert_condition?.group_by || []).join(',') || '--'}
          </Descriptions.Item>
        )}
        <Descriptions.Item label={t('common.organizations')}>
          {showGroupName(formData.organizations || [], organizationList)}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.strategyName')}>
          {formData.policy_name || '--'}
        </Descriptions.Item>
        {isClosed && (
          <Descriptions.Item label={t('log.event.alertEndTime')}>
            {formData.end_event_time
              ? convertToLocalizedTime(formData.end_event_time)
              : '--'}
          </Descriptions.Item>
        )}
        <Descriptions.Item label={t('log.event.notify')}>
          {t(`log.event.${formData.notice ? 'notified' : 'unnotified'}`)}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.handler')}>
          {formatAlertHandlers(formData.handlers, formData.handlers_display, userList)}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.notifier')}>
          {showNotifiers(formData)}
        </Descriptions.Item>
      </Descriptions>
      <div className="mt-4 flex justify-between">
        <AlertHandlerActions
          record={formData}
          closeText={t('common.close')}
          requiredPermissions={['Operate', 'Detail']}
          onSuccess={onClose}
        />
        <Button type="link" onClick={checkDetail}>
          {' '}
          {t('log.event.seeMore')}
        </Button>
      </div>
      <div className="mt-4">
        <AggregateHitSummary aggregateResult={aggregateResult} t={t} />
        <div>
          <h3 className="font-[600] text-[16px] mb-[15px]">
            {t('log.event.originalLog')}
          </h3>
          <CustomTable
            scroll={{ y: '400px', x: '840px' }}
            virtual
            columns={activeColumns}
            dataSource={rawData}
            rowKey="id"
          />
        </div>
      </div>
    </div>
  );
};

export default Information;
