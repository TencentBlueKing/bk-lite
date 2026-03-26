'use client';

import React, { useState, useEffect } from 'react';
import AlarmTable from '@/app/alarm/(pages)/alarms/components/alarmTable';
import SearchFilter from '@/app/alarm/components/searchFilter';
import { SearchFilterCondition } from '@/app/alarm/types/alarms';
import type { TableDataItem } from '@/app/alarm/types/types';
import { Drawer } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useAlarmApi } from '@/app/alarm/api/alarms';

interface AlertListDrawerProps {
  visible: boolean;
  ruleId: number | null;
  onClose: () => void;
}

const AlertListDrawer: React.FC<AlertListDrawerProps> = ({
  visible,
  ruleId,
  onClose,
}) => {
  const { t } = useTranslation();
  const { getAlarmList } = useAlarmApi();
  const [alarmTableList, setAlarmTableList] = useState<TableDataItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchCondition, setSearchCondition] = useState<SearchFilterCondition | null>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  const alarmAttrList = [
    {
      attr_id: 'alert_id',
      attr_name: t('alarms.alertId'),
      attr_type: 'str',
      option: [],
    },
    {
      attr_id: 'title',
      attr_name: t('alarms.alertName'),
      attr_type: 'str',
      option: [],
    },
    {
      attr_id: 'content',
      attr_name: t('alarms.alertContent'),
      attr_type: 'str',
      option: [],
    },
  ];

  const fetchAlarmList = async (
    pag?: { current?: number; pageSize?: number },
    condition?: SearchFilterCondition | null
  ) => {
    if (!ruleId) return;
    try {
      setLoading(true);
      const current = pag?.current ?? pagination.current;
      const pageSizeVal = pag?.pageSize ?? pagination.pageSize;
      const nextCondition = condition ?? searchCondition;
      const params: any = {
        page: current,
        page_size: pageSizeVal,
        rule_id: ruleId,
        [nextCondition?.field as string]: nextCondition?.value,
      };
      const res: any = await getAlarmList(params);
      setAlarmTableList(res.items || []);
      setPagination({
        current,
        pageSize: pageSizeVal,
        total: res.count || 0,
      });
    } catch (error) {
      console.error('Error fetching alarm list:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (visible && ruleId) {
      setAlarmTableList([]);
      fetchAlarmList({ current: 1, pageSize: pagination.pageSize });
    }
  }, [visible, ruleId]);

  const onTableChange = (pag: { current: number; pageSize: number }) => {
    fetchAlarmList({ current: pag.current, pageSize: pag.pageSize });
  };

  const onFilterSearch = (condition: SearchFilterCondition) => {
    setSearchCondition(condition);
    fetchAlarmList({ current: 1, pageSize: pagination.pageSize }, condition);
  };

  return (
    <Drawer
      title={t('settings.correlation.effectiveAlerts')}
      width={820}
      onClose={onClose}
      open={visible}
      maskClosable={false}
    >
      <div className="mb-[16px]">
        <SearchFilter attrList={alarmAttrList} onSearch={onFilterSearch} />
      </div>
      <AlarmTable
        dataSource={alarmTableList}
        pagination={pagination}
        loading={loading}
        tableScrollY="calc(100vh - 280px)"
        selectedRowKeys={[]}
        onSelectionChange={() => {}}
        onChange={onTableChange}
        readonly
        onRefresh={() =>
          fetchAlarmList({
            current: pagination.current,
            pageSize: pagination.pageSize,
          })
        }
      />
    </Drawer>
  );
};

export default AlertListDrawer;
