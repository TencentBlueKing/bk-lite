'use client';

import React, { useState, useEffect } from 'react';
import AlarmTable from '@/app/alarm/(pages)/alarms/components/alarmTable';
import SearchFilter from '@/app/alarm/components/searchFilter';
import type { TableDataItem } from '@/app/alarm/types/types';
import { Drawer, Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useAlarmApi } from '@/app/alarm/api/alarms';

interface OperateModalProps {
  visible: boolean;
  confirmLoading?: boolean;
  onClose: () => void;
  onLink: (selectedKeys: React.Key[]) => void;
}

const OperateModal: React.FC<OperateModalProps> = ({
  visible,
  confirmLoading = false,
  onClose,
  onLink,
}) => {
  const { t } = useTranslation();
  const { getAlarmList } = useAlarmApi();
  const [alarmTableList, setAlarmTableList] = useState<TableDataItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
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
    condition?: { field: string; value: string }
  ) => {
    try {
      setLoading(true);
      const current = pag?.current ?? pagination.current;
      const pageSizeVal = pag?.pageSize ?? pagination.pageSize;
      const params: any = {
        page: current,
        page_size: pageSizeVal,
        has_incident: false,
      };
      if (condition) {
        params[condition.field] = condition.value;
      }
      const res: any = await getAlarmList(params);
      setAlarmTableList(res.items || []);
      setLoading(false);
      setPagination({
        current,
        pageSize: pageSizeVal,
        total: res.count || 0,
      });
    } catch (error) {
      setLoading(false);
      console.error('Error fetching alarm list:', error);
    }
  };

  useEffect(() => {
    if (visible) {
      setAlarmTableList([]);
      setSelectedKeys([]);
      fetchAlarmList({ current: 1, pageSize: pagination.pageSize });
    }
  }, [visible]);

  const onTableChange = (pag: { current: number; pageSize: number }) => {
    fetchAlarmList({ current: pag.current, pageSize: pag.pageSize });
  };

  return (
    <Drawer
      title={t('alarmCommon.linkAlert')}
      width={820}
      onClose={onClose}
      open={visible}
      maskClosable={false}
    >
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          gap: 8,
          justifyContent: 'space-between',
        }}
      >
        {visible && (
          <SearchFilter
            attrList={alarmAttrList}
            onSearch={(condition) => {
              setSelectedKeys([]);
              fetchAlarmList(
                { current: 1, pageSize: pagination.pageSize },
                condition
              );
            }}
          />
        )}
        <Button
          type="primary"
          disabled={!selectedKeys.length}
          onClick={() => onLink(selectedKeys)}
          loading={confirmLoading}
        >
          {t('alarmCommon.linkAlert')}
        </Button>
      </div>
      <AlarmTable
        dataSource={alarmTableList}
        pagination={pagination}
        loading={loading}
        tableScrollY="calc(100vh - 260px)"
        selectedRowKeys={selectedKeys}
        onSelectionChange={setSelectedKeys}
        onChange={onTableChange}
        onRefresh={() =>
          fetchAlarmList({
            current: pagination.current,
            pageSize: pagination.pageSize,
          })
        }
        extraActions={(record) => (
          <Button
            className="mr-2"
            type="link"
            onClick={() => onLink([record.id as number])}
          >
            {t('alarmCommon.linkAlert')}
          </Button>
        )}
      />
    </Drawer>
  );
};

export default OperateModal;
