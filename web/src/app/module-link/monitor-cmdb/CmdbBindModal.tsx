'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Input, Modal, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import { HandledRequestError } from '@/utils/request';
import { useInstanceApi } from '@/app/cmdb/api';
import { parseMonitorBindConflict } from '@/app/cmdb/utils/systemLinkage';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';

interface CmdbCandidate {
  inst_uuid: string;
  inst_name?: string;
  ip_addr?: string;
}

interface CmdbBindModalProps {
  open: boolean;
  modelId: string;
  monitorId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const SEARCH_DEBOUNCE_MS = 300;

const CmdbBindModal: React.FC<CmdbBindModalProps> = ({
  open,
  modelId,
  monitorId,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { searchInstances, bindMonitor } = useInstanceApi();
  const [search, setSearch] = useState('');
  const [items, setItems] = useState<CmdbCandidate[]>([]);
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
    if (!open || !modelId) return undefined;
    let cancelled = false;
    const delay = search ? SEARCH_DEBOUNCE_MS : 0;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const data = await searchInstances({
          model_id: modelId,
          query_list: search.trim()
            ? [{ field: 'inst_name', type: 'str*', value: search.trim() }]
            : [],
          page: 1,
          page_size: 20,
          order: '',
          role: '',
          case_sensitive: false,
        });
        if (!cancelled) {
          const insts = Array.isArray(data?.insts) ? data.insts : [];
          setItems(
            insts
              .map((row: { inst_uuid?: string; inst_name?: string; ip_addr?: string }) => {
                const instUuid = resolveCmdbInstUuid(row.inst_uuid);
                if (!instUuid) return null;
                return {
                  inst_uuid: instUuid,
                  inst_name: row.inst_name,
                  ip_addr: row.ip_addr,
                };
              })
              .filter(Boolean) as CmdbCandidate[],
          );
        }
      } catch {
        if (!cancelled) setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, delay);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, modelId, search, searchInstances]);

  const columns: ColumnsType<CmdbCandidate> = useMemo(
    () => [
      {
        title: t('ModuleLink.instName'),
        dataIndex: 'inst_name',
        ellipsis: true,
        render: (value: string) => value || '--',
      },
      {
        title: t('ModuleLink.ip'),
        dataIndex: 'ip_addr',
        width: 140,
        render: (value: string) => value || '--',
      },
      {
        title: t('ModuleLink.cmdbId'),
        dataIndex: 'inst_uuid',
        ellipsis: true,
      },
    ],
    [t],
  );

  const submitBind = async (instUuid: string, confirm?: boolean) => {
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
            }),
          );
          return;
        }
        if (conflict.status === 'confirm_required') {
          Modal.confirm({
            centered: true,
            title: t('Model.systemLinkageRebindConfirm'),
            okText: t('common.confirm'),
            cancelText: t('common.cancel'),
            onOk: () => submitBind(instUuid, true),
          });
          return;
        }
      }
      message.error(
        error instanceof HandledRequestError && error.message
          ? error.message
          : t('Model.systemLinkageBindFailed'),
      );
    } finally {
      setBinding(false);
    }
  };

  return (
    <Modal
      title={t('ModuleLink.bind')}
      open={open}
      onCancel={onCancel}
      onOk={() => selectedId && void submitBind(selectedId)}
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
      <Table<CmdbCandidate>
        size="small"
        rowKey="inst_uuid"
        loading={loading}
        dataSource={items}
        columns={columns}
        pagination={false}
        scroll={{ y: 360 }}
        locale={{ emptyText: t('ModuleLink.empty') }}
        rowSelection={{
          type: 'radio',
          selectedRowKeys: selectedId ? [selectedId] : [],
          onChange: (keys) => setSelectedId(keys[0] ? String(keys[0]) : undefined),
        }}
        onRow={(record) => ({
          onClick: () => setSelectedId(record.inst_uuid),
        })}
      />
    </Modal>
  );
};

export default CmdbBindModal;
