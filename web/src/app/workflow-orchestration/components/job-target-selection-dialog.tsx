'use client';

import { Button } from 'antd';
import { useMemo, useState } from 'react';

import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';

import type { NodeTarget, WorkflowTargetField } from '../lib/types';
import { targetSourceOf } from './job-selected-targets';
import { RuntimeTargetSelector, WORKFLOW_NESTED_SELECTOR_Z_INDEX } from './workflow-launch-dialog';
import { WorkflowPermission } from './workflow-permission';

const JOB_TARGET_SOURCES = ['node_mgmt', 'job_mgmt'] as const;

interface Props {
  open: boolean;
  value: string[];
  maxCount?: number;
  onCancel: () => void;
  onConfirm: (value: string[], records: NodeTarget[]) => void;
}

export function JobTargetSelectionDialog({ open, value, maxCount = 100, onCancel, onConfirm }: Props) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [recordCache, setRecordCache] = useState<Record<string, NodeTarget>>({});
  const [blocked, setBlocked] = useState(false);

  if (open !== opened) {
    setOpened(open);
    setBlocked(false);
    if (open) setSelectedKeys(value.filter((item) => targetSourceOf(item)));
  }

  const field = useMemo<WorkflowTargetField>(() => ({
    key: 'targets',
    name: t('workflowOrchestration.editor.targetHosts', '目标主机'),
    required: true,
    binding_mode: 'runtime',
    allowed_sources: [...JOB_TARGET_SOURCES],
    allowed_operating_systems: ['linux', 'windows'],
    min_count: 1,
    max_count: maxCount,
  }), [maxCount, t]);
  const selectedRecords = selectedKeys.map((key) => recordCache[key]).filter(Boolean);
  const confirmDisabled = blocked || selectedKeys.length < field.min_count || selectedKeys.length > field.max_count;

  return <OperateModal
    width={1040}
    title={t('workflowOrchestration.launch.selectTargetTitle', '选择主机 · {name}', { name: field.name })}
    open={open}
    destroyOnHidden
    zIndex={WORKFLOW_NESTED_SELECTOR_Z_INDEX}
    footer={<div className="flex justify-end gap-2">
      <WorkflowPermission operation="Execute"><Button onClick={onCancel}>{t('common.cancel', '取消')}</Button></WorkflowPermission>
      <WorkflowPermission operation="Execute"><Button type="primary" disabled={confirmDisabled} onClick={() => onConfirm(selectedKeys, selectedRecords)}>{t('workflowOrchestration.launch.confirmSelection', '确认选择')}</Button></WorkflowPermission>
    </div>}
    styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto', paddingBlock: 24 }, footer: { marginTop: 8 } }}
    onCancel={onCancel}
  >
    {open ? <RuntimeTargetSelector
      field={field}
      value={selectedKeys}
      onChange={setSelectedKeys}
      onBlockingChange={setBlocked}
      recordCache={recordCache}
      onRecordsDiscovered={(records) => {
        setRecordCache((current) => ({ ...current, ...Object.fromEntries(records.map((item) => [item.id, item])) }));
      }}
    /> : null}
  </OperateModal>;
}
