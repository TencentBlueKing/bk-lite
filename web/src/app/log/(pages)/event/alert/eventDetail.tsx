'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useEffect,
  useRef,
} from 'react';
import { Button } from 'antd';
import OperateModal from '@/app/log/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import {
  ModalRef,
  ModalConfig,
  TableDataItem,
  TimeLineItem,
  ColumnItem,
} from '@/app/log/types';
import useLogApi from '@/app/log/api/event';
import CustomTable from '@/components/custom-table';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const EventDetail = forwardRef<ModalRef, ModalConfig>(({}, ref) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getEventRawData } = useLogApi();
  const [visible, setVisible] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TimeLineItem[]>([]);
  const [formData, setFormData] = useState<TableDataItem>({});
  const [scrollY, setScrollY] = useState<number>(300);
  const containerRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    showModal: ({ title, form }) => {
      setVisible(true);
      setTitle(title);
      setFormData(form);
      getTableData(form);
    },
  }));

  // 动态计算表格滚动高度
  useEffect(() => {
    const updateScrollHeight = () => {
      if (containerRef.current) {
        const containerHeight = containerRef.current.clientHeight;
        const calculatedHeight = Math.max(200, containerHeight - 55);
        setScrollY(calculatedHeight);
      }
    };

    // 延迟执行以确保 DOM 渲染完成
    const timeoutId = setTimeout(updateScrollHeight, 100);

    // 监听窗口大小变化
    const handleResize = () => {
      setTimeout(updateScrollHeight, 100);
    };
    window.addEventListener('resize', handleResize);

    // 使用 ResizeObserver 监听容器大小变化
    let resizeObserver: ResizeObserver | null = null;
    if (containerRef.current && window.ResizeObserver) {
      resizeObserver = new ResizeObserver(() => {
        updateScrollHeight();
      });
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener('resize', handleResize);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
    };
  }, [visible]);

  const isAggregate = useMemo(
    () => formData.alert_type === 'aggregate',
    [formData]
  );

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
        width: 500,
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
    if (isAggregate && tableData.length) {
      columns = Object.keys(tableData[0] || {})
        .filter((item) => item !== 'id')
        .map((item) => ({
          title: item,
          dataIndex: item,
          key: item,
          width: 100,
        }));
    }
    return columns;
  }, [formData, isAggregate, tableData]);

  const getTableData = async (row: TableDataItem) => {
    setTableLoading(true);
    try {
      const { data } = await getEventRawData(row.id);
      const isAggregate = row.alert_type === 'aggregate';
      const aggregateData = data?.query_result ? [data?.query_result] : [];
      const result = !isAggregate ? data || [] : aggregateData;
      const rawData = result.map((item: TableDataItem, index: number) => ({
        ...item,
        id: index,
      }));
      setTableData(rawData);
    } finally {
      setTableLoading(false);
    }
  };

  const handleCancel = () => {
    setVisible(false);
    setTableData([]);
    setFormData({});
  };

  return (
    <div>
      <OperateModal
        title={title}
        visible={visible}
        width={800}
        destroyOnClose
        onClose={handleCancel}
        footer={
          <div>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <div ref={containerRef} className="h-full">
          <CustomTable
            loading={tableLoading}
            scroll={{ y: scrollY, x: '840px' }}
            virtual
            columns={activeColumns}
            dataSource={tableData}
            rowKey="id"
          />
        </div>
      </OperateModal>
    </div>
  );
});

EventDetail.displayName = 'eventDetail';
export default EventDetail;
