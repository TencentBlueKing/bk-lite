'use client';

import React, { useState, useEffect } from 'react';
import AlarmTable from '@/app/alarm/(pages)/alarms/components/alarmTable';
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
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  const fetchAlarmList = async (pag?: { current?: number; pageSize?: number }) => {
    if (!ruleId) return;
    try {
      setLoading(true);
      const current = pag?.current ?? pagination.current;
      const pageSizeVal = pag?.pageSize ?? pagination.pageSize;
      const params: any = {
        page: current,
        page_size: pageSizeVal,
        rule_id: ruleId,
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

  return (
    <Drawer
      title={t('alarms.alert')}
      width={820}
      onClose={onClose}
      open={visible}
      maskClosable={false}
    >
      <AlarmTable
        dataSource={alarmTableList}
        pagination={pagination}
        loading={loading}
        tableScrollY="calc(100vh - 230px)"
        selectedRowKeys={[]}
        onSelectionChange={() => {}}
        onChange={onTableChange}
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
