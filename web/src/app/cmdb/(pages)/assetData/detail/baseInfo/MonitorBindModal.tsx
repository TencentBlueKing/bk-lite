'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Input, Modal, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import { HandledRequestError } from '@/utils/request';
import { useInstanceApi } from '@/app/cmdb/api';
import {
  parseMonitorBindConflict,
  type MonitorBindCandidate,
} from '@/app/cmdb/utils/systemLinkage';

interface MonitorBindModalProps {
  open: boolean;
  instUuid: string;
  alreadyLinked: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}

const SEARCH_DEBOUNCE_MS = 300;

const MonitorBindModal: React.FC<MonitorBindModalProps> = ({
  open,
  instUuid,
  alreadyLinked,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { listMonitorBindCandidates, bindMonitor } = useInstanceApi();
  const [search, setSearch] = useState('');
  const [items, setItems] = useState<MonitorBindCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [binding, setBinding] = useState(false);
  const [selectedId, setSelectedId] = useState<string>();

  useEffect(() => {
    if (!open) {
      setSearch('');
      setItems([]);
      setSelectedId(undefined);
      setBinding(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open || !instUuid) return undefined;
    let cancelled = false;
    const delay = search ? SEARCH_DEBOUNCE_MS : 0;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const data = await listMonitorBindCandidates(instUuid, search.trim());
        if (!cancelled) {
          setItems(Array.isArray(data) ? data : []);
        }
      } catch {
        if (!cancelled) {
          setItems([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, delay);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, instUuid, search]);

  const columns: ColumnsType<MonitorBindCandidate> = useMemo(
    () => [
      {
        title: t('Model.systemLinkageBindName'),
        dataIndex: 'name',
        ellipsis: true,
        render: (value: string) => value || '--',
      },
      {
        title: t('Model.systemLinkageBindIp'),
        dataIndex: 'ip',
        width: 140,
        render: (value: string) => value || '--',
      },
      {
        title: t('Model.systemLinkageBindObject'),
        dataIndex: 'object_name',
        width: 140,
        render: (value: string) => value || '--',
      },
      {
        title: t('Model.systemLinkageBindId'),
        dataIndex: 'id',
        width: 160,
        ellipsis: true,
        render: (value: string) => (
          <span className="text-xs text-[var(--color-text-3)]">{value || '--'}</span>
        ),
      },
    ],
    [t]
  );

  const submitBind = async (monitorId: string, confirm?: boolean) => {
    setBinding(true);
    try {
      await bindMonitor(instUuid, {
        monitor_id: monitorId,
        ...(confirm ? { confirm: true } : {}),
      });
      message.success(t('Model.systemLinkageBindSuccess'));
      onSuccess();
    } catch (error) {
      const conflict = parseMonitorBindConflict(error);
      if (error instanceof HandledRequestError && error.status === 409) {
        if (conflict.status === 'occupied') {
          message.error(
            t('Model.systemLinkageOccupied', '', {
              name: conflict.occupiedLabel || '--',
            })
          );
          return;
        }
        if (conflict.status === 'confirm_required') {
          Modal.confirm({
            centered: true,
            title: t('Model.systemLinkageRebindConfirm'),
            okText: t('common.confirm'),
            cancelText: t('common.cancel'),
            onOk: () => submitBind(monitorId, true),
          });
          return;
        }
      }
      message.error(
        error instanceof HandledRequestError && error.message
          ? error.message
          : t('Model.systemLinkageBindFailed')
      );
    } finally {
      setBinding(false);
    }
  };

  const handleOk = () => {
    if (!selectedId) return;
    if (alreadyLinked) {
      Modal.confirm({
        centered: true,
        title: t('Model.systemLinkageRebindConfirm'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        onOk: () => submitBind(selectedId, true),
      });
      return;
    }
    void submitBind(selectedId);
  };

  return (
    <Modal
      title={t('Model.systemLinkageBindTitle')}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={binding}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      okButtonProps={{ disabled: !selectedId }}
      width={720}
      destroyOnClose
      centered
    >
      <Input
        allowClear
        value={search}
        placeholder={t('Model.systemLinkageBindSearch')}
        className="mb-3"
        onChange={(event) => setSearch(event.target.value)}
      />
      <Table<MonitorBindCandidate>
        size="small"
        rowKey={(row) => String(row.id)}
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
        scroll={{ y: 360 }}
        locale={{ emptyText: t('Model.systemLinkageBindEmpty') }}
        rowSelection={{
          type: 'radio',
          selectedRowKeys: selectedId ? [selectedId] : [],
          onChange: (keys) => setSelectedId(keys[0] ? String(keys[0]) : undefined),
        }}
        onRow={(record) => ({
          onClick: () => setSelectedId(String(record.id)),
        })}
      />
    </Modal>
  );
};

export default MonitorBindModal;
