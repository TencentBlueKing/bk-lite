'use client';

import { CloseOutlined } from '@ant-design/icons';
import { Button, Tag } from 'antd';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';

import type { NodeTarget, TargetListResponse, TargetSource } from '../lib/types';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';

export function targetSourceOf(id: string): TargetSource | null {
  if (id.startsWith('manual:')) return 'job_mgmt';
  if (id.startsWith('node:')) return 'node_mgmt';
  return null;
}

export function fallbackTargetLabel(id: string, t: (key: string, defaultMessage?: string, values?: Record<string, unknown>) => string) {
  if (id.startsWith('manual:')) {
    return t('workflowOrchestration.editor.jobTargetFallback', '作业目标 #{id}', { id: id.slice('manual:'.length) });
  }
  if (id.startsWith('node:')) {
    return t('workflowOrchestration.editor.nodeTargetFallback', '节点 #{id}', { id: id.slice('node:'.length) });
  }
  return id;
}

export async function loadTargetPages(
  get: <T>(url: string, config?: { signal?: AbortSignal }) => Promise<T>,
  source: TargetSource,
  signal?: AbortSignal,
) {
  const response = await get<TargetListResponse>(
    `${API}/workflows/targets/?${new URLSearchParams({ source, page: '1', page_size: '100' }).toString()}`,
    signal ? { signal } : undefined,
  );
  return response.items || [];
}

export function useResolvedTargets(ids: string[]) {
  const { get } = useApiClient();
  const [records, setRecords] = useState<Record<string, NodeTarget>>({});
  const [loading, setLoading] = useState(false);
  const idsKey = ids.join('\0');

  const mergeRecords = useCallback((items: NodeTarget[]) => {
    if (!items.length) return;
    setRecords((current) => {
      const next = { ...current };
      let changed = false;
      for (const item of items) {
        if (next[item.id] === item) continue;
        next[item.id] = item;
        changed = true;
      }
      return changed ? next : current;
    });
  }, []);

  useEffect(() => {
    const needed = ids.filter((id) => targetSourceOf(id) && !records[id]);
    if (!needed.length) return undefined;
    const sources = [...new Set(needed.map((id) => targetSourceOf(id)).filter(Boolean))] as TargetSource[];
    const controller = new AbortController();
    setLoading(true);
    void Promise.all(sources.map((source) => loadTargetPages(get, source, controller.signal)))
      .then((pages) => {
        if (controller.signal.aborted) return;
        mergeRecords(pages.flat());
      })
      .catch(() => undefined)
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // records intentionally omitted: only refetch for newly missing ids
  }, [get, idsKey, mergeRecords]);

  const items = useMemo(
    () => ids.map((id) => records[id] || null),
    [ids, records],
  );

  return { items, records, loading, mergeRecords };
}

export function JobSelectedTargets({
  value,
  knownRecords,
  readOnly,
  onChange,
  onSelectClick,
  selectLabel,
  extra,
}: {
  value: string[];
  knownRecords?: Record<string, NodeTarget>;
  readOnly?: boolean;
  onChange?: (value: string[]) => void;
  onSelectClick?: () => void;
  selectLabel?: string;
  extra?: ReactNode;
}) {
  const { t } = useTranslation();
  const { items, loading, mergeRecords } = useResolvedTargets(value);

  useEffect(() => {
    if (!knownRecords) return;
    mergeRecords(Object.values(knownRecords));
  }, [knownRecords, mergeRecords]);

  const resolvedItems = value.map((id, index) => items[index] || knownRecords?.[id] || null);

  return <div className="flex flex-col gap-2">
    {value.length ? <div className="flex flex-wrap gap-2 rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2">
      {value.map((id, index) => {
        const target = resolvedItems[index];
        const label = target?.name || fallbackTargetLabel(id, t);
        const secondary = target?.ip || '';
        return <Tag
          key={id}
          className="m-0 inline-flex max-w-full items-center gap-1 !px-2 !py-1 !text-sm"
          closable={!readOnly}
          onClose={(event) => {
            event.preventDefault();
            onChange?.(value.filter((item) => item !== id));
          }}
          closeIcon={!readOnly ? <CloseOutlined className="text-[10px]" /> : undefined}
        >
          <span className="truncate font-medium text-[var(--color-text-1)]" title={secondary ? `${label} (${secondary})` : label}>
            {label}
          </span>
          {secondary ? <span className="truncate font-mono text-[11px] text-[var(--color-text-3)]">{secondary}</span> : null}
        </Tag>;
      })}
      {loading && value.some((id, index) => !resolvedItems[index]) ? <span className="text-xs text-[var(--color-text-3)]">{t('common.loading', '加载中…')}</span> : null}
    </div> : <div className="rounded-md border border-dashed border-[var(--color-border-2)] px-3 py-2 text-sm text-[var(--color-text-3)]">
      {t('workflowOrchestration.launch.selectHosts', '请选择目标主机')}
    </div>}
    <div className="flex flex-wrap items-center gap-2">
      {onSelectClick && !readOnly ? <WorkflowPermission operation="Edit">
        <Button type="default" onClick={onSelectClick}>
          {selectLabel || t('workflowOrchestration.editor.selectTargets', '选择主机')}
        </Button>
      </WorkflowPermission> : null}
      {extra}
    </div>
  </div>;
}
