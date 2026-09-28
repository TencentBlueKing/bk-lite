'use client';

import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, App, Button, Input } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Key } from 'react';

import { WORKFLOW_NESTED_SELECTOR_Z_INDEX } from './workflow-launch-dialog';
import DualSelector from '@/components/dual-selector';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';

import type { NodeTarget, TargetListResponse } from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { targetSourceOf } from './job-selected-targets';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';
const JOB_SOURCE = 'job_mgmt' as const;

interface Props {
  open: boolean;
  value: string[];
  maxCount?: number;
  onCancel: () => void;
  onConfirm: (value: string[], records: NodeTarget[]) => void;
}

export function JobTargetSelectionDialog({ open, value, maxCount = 100, onCancel, onConfirm }: Props) {
  const { get } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [records, setRecords] = useState<NodeTarget[]>([]);
  const [recordCache, setRecordCache] = useState<Record<string, NodeTarget>>({});
  const [count, setCount] = useState(0);
  const [error, setError] = useState<string>();
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [queryDraft, setQueryDraft] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const requestCoordinator = useRequestCoordinator(setLoading);

  useEffect(() => {
    if (!open) {
      requestCoordinator.invalidate();
      return;
    }
    setSelectedKeys(value.filter((item) => targetSourceOf(item) === JOB_SOURCE));
    setPage(1);
    setQueryDraft('');
    setQuery('');
    setError(undefined);
    // Only re-sync when the dialog opens; keep in-dialog selection stable.
  }, [open]);

  const load = useCallback(async (nextPage: number, nextQuery: string) => {
    const ticket = requestCoordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const params = new URLSearchParams({ source: JOB_SOURCE, page: String(nextPage), page_size: '10' });
      if (nextQuery) params.set('query', nextQuery);
      const response = await get<TargetListResponse>(`${API}/workflows/targets/?${params.toString()}`, { signal: ticket.signal });
      if (!requestCoordinator.shouldApply(ticket)) return;
      const items = response.items || [];
      setRecords(items);
      setCount(response.count || 0);
      setRecordCache((current) => ({ ...current, ...Object.fromEntries(items.map((item) => [item.id, item])) }));
      setError(undefined);
    } catch (loadError) {
      if (!requestCoordinator.shouldApply(ticket)) return;
      setRecords([]);
      setError(loadError instanceof Error
        ? loadError.message
        : t('workflowOrchestration.launch.sourceUnavailable', '{source}暂时不可用', {
          source: t('workflowOrchestration.launch.jobPlatform', '作业平台'),
        }));
    } finally {
      requestCoordinator.finish(ticket);
    }
  }, [get, requestCoordinator, t]);

  useAutoRequest(open ? `job-targets:${JOB_SOURCE}:${page}:${query}` : undefined, () => load(page, query));

  const selectedRecords = useMemo(
    () => selectedKeys.map((key) => recordCache[key]).filter(Boolean),
    [recordCache, selectedKeys],
  );
  const columns: ColumnsType<NodeTarget> = [
    { title: t('workflowOrchestration.launch.hostName', '主机名'), dataIndex: 'name', render: (name: string) => <span className="font-medium text-[var(--color-text-1)]">{name || t('workflowOrchestration.launch.unnamedHost', '未命名主机')}</span> },
    { title: 'IP', dataIndex: 'ip', width: 180, render: (ip: string) => <span className="font-mono text-xs text-[var(--color-text-2)]">{ip || '--'}</span> },
    { title: t('workflowOrchestration.launch.system', '系统'), dataIndex: 'operating_system', width: 110, render: (system: string) => system || '--' },
  ];
  const changeSelection = (keys: Key[]) => {
    if (keys.length > maxCount) {
      message.warning(t('workflowOrchestration.launch.maxHosts', '最多选择 {count} 台主机', { count: maxCount }));
      return;
    }
    setSelectedKeys(keys.map(String));
  };

  return <OperateModal
    width={1040}
    title={t('workflowOrchestration.editor.selectJobPlatformHosts', '选择作业平台主机')}
    open={open}
    destroyOnHidden
    zIndex={WORKFLOW_NESTED_SELECTOR_Z_INDEX}
    footer={<div className="flex justify-end gap-2"><WorkflowPermission operation="Execute"><Button onClick={onCancel}>{t('common.cancel', '取消')}</Button></WorkflowPermission><WorkflowPermission operation="Execute"><Button type="primary" onClick={() => onConfirm(selectedKeys, selectedRecords)}>{t('workflowOrchestration.launch.confirmSelection', '确认选择')}</Button></WorkflowPermission></div>}
    styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto', paddingBlock: 24 }, footer: { marginTop: 8 } }}
    onCancel={onCancel}
  >
    <DualSelector<NodeTarget>
      rowKey="id"
      dataSource={error ? [] : records}
      loading={loading}
      columns={columns}
      selectedKeys={selectedKeys}
      selectedRecordsData={selectedRecords}
      onChange={changeSelection}
      pagination={{ current: page, pageSize: 10, total: count, showSizeChanger: false }}
      onPageChange={(nextPage) => setPage(nextPage)}
      rightTitle={t('workflowOrchestration.launch.selectedHosts', '已选 {count} 台', { count: selectedKeys.length })}
      clearAllText={t('workflowOrchestration.launch.clearAll', '全部清除')}
      emptySelectionText={t('workflowOrchestration.launch.noTargetsSelected', '暂未选择主机')}
      selectedPreviewLabel={t('workflowOrchestration.launch.selectedPreview', '已选项预览')}
      getRemoveLabel={(target) => t('workflowOrchestration.launch.removeTarget', '移除 {name}', { name: target.name || target.ip })}
      renderSelectedItem={(target) => <div><div className="truncate font-medium text-[var(--color-text-1)]">{target.name || t('workflowOrchestration.launch.unnamedHost', '未命名主机')}</div><div className="mt-0.5 truncate font-mono text-[11px] text-[var(--color-text-3)]">{target.ip}</div></div>}
      leftTitle={<div className="mb-4 space-y-3">
        <div className="text-xs leading-5 text-[var(--color-text-3)]">{t('workflowOrchestration.editor.jobPlatformSelectorHint', '仅从作业平台选择主机，展示当前组织内有权限的目标')}</div>
        <div className="flex gap-2">
          <Input.Search
            allowClear
            value={queryDraft}
            placeholder={t('workflowOrchestration.launch.searchHost', '搜索主机名或 IP')}
            enterButton={<SearchOutlined />}
            onChange={(event) => {
              const next = event.target.value;
              setQueryDraft(next);
              if (!next) {
                setPage(1);
                setQuery('');
              }
            }}
            onSearch={(next) => {
              setPage(1);
              setQuery(next.trim());
            }}
          />
          <Button
            aria-label={t('workflowOrchestration.launch.refreshSource', '刷新{source}目标', { source: t('workflowOrchestration.launch.jobPlatform', '作业平台') })}
            icon={<ReloadOutlined aria-hidden="true" />}
            onClick={() => void load(page, query)}
          />
        </div>
        {error ? <Alert
          type="error"
          showIcon
          message={t('workflowOrchestration.launch.sourceLoadFailed', '{source}加载失败', { source: t('workflowOrchestration.launch.jobPlatform', '作业平台') })}
          description={error}
          action={<WorkflowPermission operation="Execute"><Button size="small" onClick={() => void load(page, query)}>{t('common.retry', '重试')}</Button></WorkflowPermission>}
        /> : null}
      </div>}
      height="min(520px, calc(100vh - 330px))"
    />
  </OperateModal>;
}
