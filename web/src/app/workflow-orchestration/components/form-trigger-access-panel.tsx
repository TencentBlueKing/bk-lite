'use client';

import { CopyOutlined, ExportOutlined } from '@ant-design/icons';
import { App, Button, Segmented, Tooltip } from 'antd';
import { useCallback, useEffect, useState } from 'react';

import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import type { PaginatedResponse, WorkflowTriggerRecord } from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';

function absoluteUrl(path: string) {
  if (typeof window === 'undefined') return path;
  return `${window.location.origin}${path}`;
}

function EntryActions({
  label,
  path,
  unavailableTip,
}: {
  label: string;
  path?: string;
  unavailableTip: string;
}) {
  const { message } = App.useApp();
  const { t } = useTranslation();
  const openTip = path ? t('workflowOrchestration.form.viewEntry', '查看{label}', { label }) : unavailableTip;
  const copyTip = path ? t('workflowOrchestration.form.copyEntryLink', '复制{label}链接', { label }) : unavailableTip;

  const copy = async () => {
    if (!path) return;
    await navigator.clipboard.writeText(absoluteUrl(path));
    message.success(t('workflowOrchestration.form.linkCopied', '入口链接已复制'));
  };

  return (
    <div className="flex shrink-0 items-center gap-1">
      <Tooltip title={openTip}>
        <span>
          <WorkflowPermission operation="View"><Button
            aria-label={t('workflowOrchestration.form.viewEntry', '查看{label}', { label })}
            disabled={!path}
            icon={<ExportOutlined />}
            size="small"
            onClick={() => path && window.open(path, '_blank', 'noopener,noreferrer')}
          /></WorkflowPermission>
        </span>
      </Tooltip>
      <Tooltip title={copyTip}>
        <span>
          <WorkflowPermission operation="View"><Button aria-label={t('workflowOrchestration.form.copyEntryLink', '复制{label}链接', { label })} disabled={!path} icon={<CopyOutlined />} size="small" onClick={() => void copy()} /></WorkflowPermission>
        </span>
      </Tooltip>
    </div>
  );
}

export function FormTriggerAccessPanel({
  workflowId,
  nodeKey,
  currentVersion,
  hasDraft,
}: {
  workflowId: number | null;
  nodeKey: string;
  currentVersion: number;
  hasDraft: boolean;
}) {
  const { get } = useApiClient();
  const { t } = useTranslation();
  const [runtimeTrigger, setRuntimeTrigger] = useState<WorkflowTriggerRecord>();
  const [loading, setLoading] = useState(false);
  const draftAvailable = currentVersion === 0 || hasDraft;
  const productionAvailable = currentVersion > 0;
  const [activeEntry, setActiveEntry] = useState<'draft' | 'production'>(draftAvailable ? 'draft' : 'production');
  const coordinator = useRequestCoordinator(setLoading);

  useEffect(() => {
    if (!draftAvailable && productionAvailable) setActiveEntry('production');
    if (draftAvailable && !productionAvailable) setActiveEntry('draft');
  }, [draftAvailable, productionAvailable]);

  const loadRuntimeTrigger = useCallback(async () => {
    if (!workflowId || currentVersion <= 0) return;
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const response = await get<PaginatedResponse<WorkflowTriggerRecord>>(
        `${API}/triggers/?workflow_id=${workflowId}&page_size=100`,
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
      setRuntimeTrigger((response?.items || []).find((item) => item.node_key === nodeKey && item.trigger_type === 'FORM'));
    } catch {
      if (coordinator.shouldApply(ticket)) setRuntimeTrigger(undefined);
    } finally {
      coordinator.finish(ticket);
    }
  }, [coordinator, currentVersion, get, nodeKey, workflowId]);

  useAutoRequest(
    workflowId && currentVersion > 0 ? `form-trigger-access:${workflowId}:${nodeKey}:${currentVersion}` : undefined,
    loadRuntimeTrigger,
  );

  const testPath = workflowId
    ? `/workflow-orchestration/forms/test/${workflowId}/${encodeURIComponent(nodeKey)}`
    : undefined;
  const productionPath = currentVersion > 0 && runtimeTrigger
    ? `/workflow-orchestration/forms/${runtimeTrigger.id}`
    : undefined;
  const productionTip = loading ? t('workflowOrchestration.form.loadingProductionEntry', '正在获取正式入口') : currentVersion > 0 ? t('workflowOrchestration.form.productionUnavailable', '正式入口暂不可用') : t('workflowOrchestration.form.availableAfterPublish', '发布流程后生成');
  const showSwitcher = draftAvailable && productionAvailable;
  const active = activeEntry === 'draft'
    ? {
      label: t('workflowOrchestration.form.draftPreview', '草稿预览'),
      description: t('workflowOrchestration.form.savedDraft', '使用已保存草稿'),
      path: testPath,
      unavailableTip: t('workflowOrchestration.form.availableAfterSave', '首次保存流程后可用'),
    }
    : {
      label: t('workflowOrchestration.form.productionEntry', '正式入口'),
      description: t('workflowOrchestration.form.latestPublished', '指向最新发布版本'),
      path: productionPath,
      unavailableTip: productionTip,
    };

  return (
    <section className="rounded-lg bg-[var(--color-fill-1)] px-4 py-3" aria-label={t('workflowOrchestration.form.entry', '表单入口')}>
      <div className="flex items-center justify-between gap-4">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('workflowOrchestration.form.entry', '表单入口')}</div>
        {showSwitcher ? (
          <Segmented<'draft' | 'production'>
            aria-label={t('workflowOrchestration.form.entryType', '入口类型')}
            size="small"
            value={activeEntry}
            options={[{ label: t('workflowOrchestration.form.draftPreview', '草稿预览'), value: 'draft' }, { label: t('workflowOrchestration.form.productionEntry', '正式入口'), value: 'production' }]}
            onChange={setActiveEntry}
          />
        ) : null}
      </div>
      <div className="mt-3 flex items-center justify-between gap-4">
        <div className="min-w-0">
          {!showSwitcher ? <div className="text-sm text-[var(--color-text-1)]">{active.label}</div> : null}
          <div className="mt-0.5 text-xs text-[var(--color-text-3)]">{active.description}</div>
        </div>
        <EntryActions label={active.label} path={active.path} unavailableTip={active.unavailableTip} />
      </div>
    </section>
  );
}
