'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Button, Tag, Empty } from 'antd';
import { RightOutlined, GlobalOutlined } from '@ant-design/icons';
import OperateDrawer from '@/app/node-manager/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import { useTelegrafMap } from '@/app/node-manager/hooks/node';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { STATUS_CODE_PRIORITY } from '@/app/node-manager/constants/cloudregion';
import {
  ModalSuccess,
  TableDataItem,
  ModalRef,
} from '@/app/node-manager/types';

const CollectorDetailDrawer = forwardRef<ModalRef, ModalSuccess>(({}, ref) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const statusMap = useTelegrafMap();
  const [visible, setVisible] = useState<boolean>(false);
  const [selectedCollector, setSelectedCollector] =
    useState<TableDataItem | null>(null);
  const [collectors, setCollectors] = useState<TableDataItem[]>([]);
  const [form, setForm] = useState<TableDataItem>({});

  useImperativeHandle(ref, () => ({
    showModal: ({ collectors, row }) => {
      setVisible(true);
      setCollectors(collectors);
      setForm(row);
      if (collectors.length > 0) {
        const sortedCollectors = [...collectors].sort((a, b) => {
          const priorityA = STATUS_CODE_PRIORITY[a.status] || 999;
          const priorityB = STATUS_CODE_PRIORITY[b.status] || 999;
          return priorityA - priorityB;
        });

        setSelectedCollector(sortedCollectors[0]);
      }
    },
  }));

  const getSortedGroupedCollectors = () => {
    const groupedCollectors = collectors.reduce((groups, collector) => {
      const status = collector.status.toString();
      if (!groups[status]) {
        groups[status] = [];
      }
      groups[status].push(collector);
      return groups;
    }, {} as Record<string, TableDataItem[]>);

    return Object.entries(groupedCollectors).sort(([statusA], [statusB]) => {
      const priorityA = STATUS_CODE_PRIORITY[Number(statusA)] || 999;
      const priorityB = STATUS_CODE_PRIORITY[Number(statusB)] || 999;
      return priorityA - priorityB;
    });
  };

  const handleCancel = () => {
    setVisible(false);
    setCollectors([]);
    setSelectedCollector(null);
    setForm({});
  };

  const handleCollectorClick = (collector: TableDataItem) => {
    setSelectedCollector(collector);
  };

  const getStatusInfo = (status: number) => {
    return (
      statusMap[status] || {
        tagColor: 'default',
        color: '#b2b5bd',
        text: t('node-manager.cloudregion.node.unknown'),
        engText: 'Unknown',
      }
    );
  };

  return (
    <div>
      <OperateDrawer
        title={form?.name || '--'}
        subTitle={
          <Tag icon={<GlobalOutlined />} color="blue" className="text-sm">
            {form?.ip || '--'}
          </Tag>
        }
        headerExtra={
          <div
            style={{
              color: 'var(--color-text-3)',
              fontSize: '12px',
            }}
          >
            {t('node-manager.cloudregion.node.lastReportTime')}：
            {form.updated_at ? convertToLocalizedTime(form.updated_at) : '--'}
          </div>
        }
        open={visible}
        width={600}
        destroyOnClose
        onClose={handleCancel}
        footer={
          <div className="flex justify-end">
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <div className="flex h-full">
          <div className="w-1/2 pr-4 border-r border-gray-200">
            <b className="block mb-2">
              {t('node-manager.cloudregion.node.collector')}
            </b>
            <div className="space-y-2">
              {getSortedGroupedCollectors().map(([status, items]) => {
                return (
                  <div key={status} className="text-[12px]">
                    <div className="space-y-2 mb-2">
                      {items.map((collector) => {
                        const collectorStatusInfo = getStatusInfo(
                          collector.status
                        );
                        return (
                          <div
                            key={collector.collector_id}
                            className={`p-3 rounded cursor-pointer transition-colors flex items-center justify-between border-l-4 ${
                              selectedCollector?.collector_id ===
                              collector.collector_id
                                ? 'bg-[var(--color-bg-hover)] border-blue-200'
                                : 'bg-[var(--color-bg-1)] border-gray-200 hover:bg-[var(--color-bg-hover)]'
                            }`}
                            style={{
                              border: '1px solid var(--color-border-1)',
                              borderLeft: `4px solid ${collectorStatusInfo.color}`,
                            }}
                            onClick={() => handleCollectorClick(collector)}
                          >
                            <div className="flex items-center flex-1">
                              <div className="mr-2">
                                {collectorStatusInfo.icon}
                              </div>
                              <div className="flex-1">
                                <div className="font-medium text-sm">
                                  {collector.collector_name}
                                </div>
                                <div
                                  className="text-xs mt-1"
                                  style={{ color: collectorStatusInfo.color }}
                                >
                                  {collectorStatusInfo.text}
                                </div>
                              </div>
                            </div>
                            <RightOutlined className="text-xs" />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="w-1/2 pl-4">
            {selectedCollector ? (
              <div className="space-y-4">
                <div className="text-lg font-bold">
                  {selectedCollector.collector_name}
                </div>
                <div className="flex items-center">
                  <label className="text-[var(--color-text-3)]">
                    {t('node-manager.cloudregion.node.status')}：
                  </label>
                  <Tag color={getStatusInfo(selectedCollector.status).tagColor}>
                    {getStatusInfo(selectedCollector.status).text}
                  </Tag>
                </div>
                <div>
                  <label className="text-[var(--color-text-3)]">
                    {t('node-manager.cloudregion.node.message')}：
                  </label>
                  <div className="text-sm text-[var(--color-text-3)] p-2 bg-[var(--color-fill-1)] rounded">
                    {selectedCollector.message || '--'}
                  </div>
                </div>
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </div>
        </div>
      </OperateDrawer>
    </div>
  );
});

CollectorDetailDrawer.displayName = 'CollectorDetailDrawer';
export default CollectorDetailDrawer;
