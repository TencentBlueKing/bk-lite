'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Input, Modal, Select, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { useCollectApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';

import {
  NETWORK_DEVICE_TYPES,
  canOperateUnknownSoid,
  flattenUnresolvedDevices,
  uniqueSoidRows,
  type SoidRow,
  type UnresolvedGroup,
} from './unknownSoidRows';

interface UnknownSoidPanelProps {
  taskId: number;
  execStatus: number;
  groups: UnresolvedGroup[];
  onChanged: () => void;
}

type PanelMode = 'map' | 'write';

const UnknownSoidPanel: React.FC<UnknownSoidPanelProps> = ({
  taskId,
  execStatus,
  groups,
  onChanged,
}) => {
  const { t } = useTranslation();
  const { saveUnknownSoidMappings, writeUnknownDevices } = useCollectApi();
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [mode, setMode] = useState<PanelMode | null>(null);
  const [draft, setDraft] = useState<SoidRow[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const devices = useMemo(() => flattenUnresolvedDevices(groups), [groups]);
  const selectedDevices = devices.filter((device) => selectedKeys.includes(device.ip_addr));
  const operable = canOperateUnknownSoid(execStatus, selectedDevices.length);
  const readOnly = mode === 'write' && draft.length > 0 && draft.every((row) => row.locked);

  useEffect(() => {
    const ips = new Set(devices.map((device) => device.ip_addr));
    setSelectedKeys((keys) => keys.filter((key) => ips.has(String(key))));
  }, [devices]);

  const open = (nextMode: PanelMode) => {
    setDraft(uniqueSoidRows(selectedDevices));
    setMode(nextMode);
  };

  const updateDraft = (soid: string, patch: Partial<SoidRow>) => {
    setDraft((rows) => rows.map((row) => (row.soid === soid ? { ...row, ...patch } : row)));
  };

  const typeOptions = NETWORK_DEVICE_TYPES.map((value) => ({
    value,
    label: t(`Collection.networkDevice.${value}`),
  }));

  const submit = async () => {
    const incomplete = draft.filter((row) => !row.locked && (!row.device_type || !row.brand.trim() || !row.model.trim()));
    if (incomplete.length > 0) {
      message.warning(t('Collection.taskDetail.unknownSoidRequired'));
      return;
    }
    const items = draft
      .filter((row) => !row.locked)
      .map((row) => ({
        soid: row.soid,
        device_type: row.device_type,
        brand: row.brand.trim(),
        model: row.model.trim(),
      }));
    setSubmitting(true);
    try {
      if (items.length > 0) {
        await saveUnknownSoidMappings(String(taskId), { items });
      }
      if (mode === 'write') {
        await writeUnknownDevices(String(taskId), {
          ip_addrs: selectedDevices.map((device) => device.ip_addr),
        });
      }
      setMode(null);
      onChanged();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('Collection.taskDetail.unknownSoidFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const draftColumns: ColumnsType<SoidRow> = [
    { title: 'SOID', dataIndex: 'soid', width: 220 },
    { title: t('Collection.taskDetail.unknownSoidCount'), dataIndex: 'count', width: 90 },
    {
      title: t('Collection.taskDetail.unknownSoidType'),
      dataIndex: 'device_type',
      width: 140,
      render: (_value, row) => (
        <Select
          className="w-full"
          disabled={row.locked || readOnly}
          value={row.device_type || undefined}
          options={typeOptions}
          onChange={(value) => updateDraft(row.soid, { device_type: value })}
        />
      ),
    },
    {
      title: t('Collection.taskDetail.unknownSoidBrand'),
      dataIndex: 'brand',
      render: (_value, row) => (
        <Input
          disabled={row.locked || readOnly}
          value={row.brand}
          onChange={(event) => updateDraft(row.soid, { brand: event.target.value })}
        />
      ),
    },
    {
      title: t('Collection.taskDetail.unknownSoidModel'),
      dataIndex: 'model',
      render: (_value, row) => (
        <Input
          disabled={row.locked || readOnly}
          value={row.model}
          onChange={(event) => updateDraft(row.soid, { model: event.target.value })}
        />
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={!operable} onClick={() => open('map')}>
          {t('Collection.taskDetail.completeMapping')}
        </Button>
        <Button type="primary" disabled={!operable} onClick={() => open('write')}>
          {t('Collection.taskDetail.writeModel')}
        </Button>
      </div>
      <p className="m-0 text-[var(--color-text-3)]">{t('Collection.taskDetail.unknownSoidHint')}</p>
      <CustomTable
        rowKey="ip_addr"
        size="small"
        dataSource={devices}
        pagination={false}
        rowSelection={{
          selectedRowKeys: selectedKeys,
          onChange: (keys) => setSelectedKeys(keys),
        }}
        columns={[
          { title: 'IP', dataIndex: 'ip_addr', key: 'ip_addr' },
          { title: 'SOID', dataIndex: 'soid', key: 'soid' },
          { title: t('Collection.taskDetail.unknownSoidType'), dataIndex: 'device_type', key: 'device_type',
            render: (value: string) => (value ? t(`Collection.networkDevice.${value}`) : '-') },
          { title: t('Collection.taskDetail.unknownSoidBrand'), dataIndex: 'brand', key: 'brand', render: (value: string) => value || '-' },
          { title: t('Collection.taskDetail.unknownSoidModel'), dataIndex: 'model', key: 'model', render: (value: string) => value || '-' },
          { title: t('Collection.taskDetail.unknownSoidPort'), dataIndex: 'port', key: 'port' },
        ]}
      />
      <Modal
        open={mode !== null}
        title={mode === 'write' ? t('Collection.taskDetail.writeModel') : t('Collection.taskDetail.completeMapping')}
        width={860}
        confirmLoading={submitting}
        onCancel={() => setMode(null)}
        onOk={submit}
        okText={mode === 'write' ? t('Collection.taskDetail.writeModel') : t('common.confirm')}
      >
        <p className="mb-3 text-[var(--color-text-3)]">
          {mode === 'write'
            ? t('Collection.taskDetail.writeModelHint')
            : t('Collection.taskDetail.completeMappingHint')}
        </p>
        <Table rowKey="soid" size="small" pagination={false} dataSource={draft} columns={draftColumns} />
      </Modal>
    </div>
  );
};

export default UnknownSoidPanel;
