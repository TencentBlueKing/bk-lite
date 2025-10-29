'use client';
import React, { useRef, useState, useMemo } from 'react';
import { Descriptions } from 'antd';
import {
  TableDataItem,
  Organization,
  UserItem,
  ColumnItem,
} from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import informationStyle from './index.module.scss';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { showGroupName } from '@/app/log/utils/common';
import { useCommon } from '@/app/log/context/common';
import { Popconfirm, message, Button } from 'antd';
import useLogEventApi from '@/app/log/api/event';
import { LEVEL_MAP } from '@/app/log/constants';
import { useLevelList } from '@/app/log/hooks/event';
import Permission from '@/components/permission';
import CustomTable from '@/components/custom-table';
import { FilterItem } from '@/app/log/types/integration';

const Information: React.FC<TableDataItem> = ({
  formData,
  userList,
  onClose,
  rawData = [],
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const LEVEL_LIST = useLevelList();
  const { patchLogAlert } = useLogEventApi();
  const commonContext = useCommon();
  const authList = useRef(commonContext?.authOrganizations || []);
  const organizationList: Organization[] = authList.current;
  const [confirmLoading, setConfirmLoading] = useState(false);

  const isAggregate = useMemo(
    () => formData.alert_type === 'aggregate',
    [formData]
  );

  const isClosed = useMemo(() => formData.status === 'closed', [formData]);

  const activeColumns = useMemo(() => {
    let columns: ColumnItem[] = [
      {
        title: 'timestrap',
        dataIndex: '_time',
        key: '_time',
        width: 150,
        fixed: 'left',
        sorter: (a: any, b: any) => a.id - b.id,
        render: (val, { _time }) => (
          <>{val ? convertToLocalizedTime(_time) : '--'}</>
        ),
      },
      {
        title: 'message',
        dataIndex: '_msg',
        key: '_msg',
        width: 600,
        render: (val) => <>{val || '--'}</>,
      },
    ];
    if (!isAggregate && formData.show_fields?.length) {
      const displayColumns = formData.show_fields.map((item: string) => ({
        title: item,
        dataIndex: item,
        key: item,
        width: 100,
      }));
      columns = [...columns, ...displayColumns];
    }
    if (isAggregate && rawData.length) {
      columns = Object.keys(rawData[0] || {})
        .filter((item) => item !== 'id')
        .map((item) => ({
          title: item,
          dataIndex: item,
          key: item,
          width: 100,
        }));
    }
    return columns;
  }, [formData, isAggregate, rawData]);

  const buildVictoriaLogsQuery = () => {
    try {
      const alertCondition = formData.alert_condition;
      if (!alertCondition) return '';
      const { query, group_by, rule } = alertCondition;
      const baseQuery = query || '*';
      // 首先构建基础过滤查询（不包含聚合函数的条件）
      const filterConditions: string[] = [];
      const aggregateConditions: any[] = [];
      if (rule?.conditions?.length) {
        rule.conditions.forEach((condition: FilterItem) => {
          const { field, op, value, func } = condition;
          // 如果有聚合函数，放入聚合条件处理
          if (func && ['count', 'sum', 'max', 'min', 'avg'].includes(func)) {
            aggregateConditions.push(condition);
          } else {
            // 普通字段过滤条件
            let fieldCondition = '';
            switch (op) {
              case '=':
                fieldCondition = `${field}:"${value}"`;
                break;
              case '!=':
                fieldCondition = `!${field}:"${value}"`;
                break;
              case '>':
                fieldCondition = `${field}:>${value}`;
                break;
              case '<':
                fieldCondition = `${field}:<${value}`;
                break;
              case 'in':
                fieldCondition = `${field}:*${value}*`;
                break;
              case 'nin':
                fieldCondition = `!${field}:*${value}*`;
                break;
              default:
                fieldCondition = `${field}:"${value}"`;
            }
            filterConditions.push(fieldCondition);
          }
        });
      }
      // 构建基础查询部分
      let victoriaQuery = baseQuery;
      if (filterConditions.length > 0) {
        const filterStr =
          rule?.mode === 'and'
            ? filterConditions.join(' AND ')
            : filterConditions.join(' OR ');
        if (victoriaQuery === '*' || !victoriaQuery) {
          victoriaQuery = filterStr;
        } else {
          victoriaQuery = `(${victoriaQuery}) AND (${filterStr})`;
        }
      }
      // 处理 group_by 字段 - 确保这些字段存在
      if (group_by && group_by.length > 0) {
        const groupByConditions = group_by.map((field: string) => `${field}:*`);
        const groupByStr = groupByConditions.join(' AND ');
        if (victoriaQuery === '*' || !victoriaQuery) {
          victoriaQuery = groupByStr;
        } else {
          victoriaQuery = `(${victoriaQuery}) AND (${groupByStr})`;
        }
      }
      // 如果有聚合条件或group_by，构建 stats 管道
      if (aggregateConditions.length > 0 || (group_by && group_by.length > 0)) {
        const statsExpressions: string[] = [];
        // 添加聚合函数表达式
        aggregateConditions.forEach((condition: FilterItem) => {
          const { field, func } = condition;
          let aggregateExpr = '';
          switch (func) {
            case 'count':
              if (field === '*' || !field) {
                aggregateExpr = 'count()';
              } else {
                aggregateExpr = `count(${field})`;
              }
              break;
            case 'sum':
              aggregateExpr = `sum(${field})`;
              break;
            case 'max':
              aggregateExpr = `max(${field})`;
              break;
            case 'min':
              aggregateExpr = `min(${field})`;
              break;
            case 'avg':
              aggregateExpr = `avg(${field})`;
              break;
          }
          if (aggregateExpr) {
            statsExpressions.push(aggregateExpr);
          }
        });
        // 如果没有聚合表达式但有group_by，添加count()
        if (statsExpressions.length === 0 && group_by && group_by.length > 0) {
          statsExpressions.push('count()');
        }
        // 构建完整的stats查询 - 正确的语法应该是 | stats by (fields) functions
        if (statsExpressions.length > 0) {
          if (group_by && group_by.length > 0) {
            // 有group by的情况
            victoriaQuery += ` | stats by (${group_by.join(
              ', '
            )}) ${statsExpressions.join(', ')}`;
          } else {
            // 没有group by的情况
            victoriaQuery += ` | stats ${statsExpressions.join(', ')}`;
          }
        }
      }
      return victoriaQuery;
    } catch (error) {
      console.error('Error building VictoriaLogs query:', error);
      return '';
    }
  };

  const checkDetail = () => {
    const params = {
      query: formData.alert_condition?.query as string,
      startTime: String(
        +new Date(convertToLocalizedTime(formData.start_event_time))
      ),
      endTime: String(
        isClosed
          ? +new Date(convertToLocalizedTime(formData.end_event_time))
          : +new Date()
      ),
    };
    if (isAggregate) {
      params.query = buildVictoriaLogsQuery();
    }
    const queryString = new URLSearchParams(params).toString();
    const url = `/log/search?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleCloseConfirm = async (row: TableDataItem) => {
    setConfirmLoading(true);
    try {
      await patchLogAlert({
        status: 'closed',
        id: row.id,
      });
      message.success(t('log.event.successfullyClosed'));
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
      (row.notice_users || [])
        .map((item: string) => getUsers(item))
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
        <Descriptions.Item label={t('common.operator')}>
          {formData.operator || '--'}
        </Descriptions.Item>
        <Descriptions.Item label={t('log.event.notifier')}>
          {showNotifiers(formData)}
        </Descriptions.Item>
      </Descriptions>
      <div className="mt-4 flex justify-between">
        <Permission
          requiredPermissions={['Operate', 'Detail']}
          instPermissions={formData.permission}
        >
          <Popconfirm
            title={t('log.event.closeTitle')}
            description={t('log.event.closeContent')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            okButtonProps={{ loading: confirmLoading }}
            onConfirm={() => handleCloseConfirm(formData)}
          >
            <Button type="link" disabled={formData.status !== 'new'}>
              {t('log.event.closeAlert')}
            </Button>
          </Popconfirm>
        </Permission>
        <Button type="link" onClick={checkDetail}>
          {' '}
          {t('log.event.seeMore')}
        </Button>
      </div>
      <div className="mt-4">
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
