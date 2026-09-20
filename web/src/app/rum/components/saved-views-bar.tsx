'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  BookOutlined,
  CheckOutlined,
  DeleteOutlined,
  GlobalOutlined,
  LockOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { Button, Dropdown, Input, Popconfirm, Switch } from 'antd';

import { useRumQueries, type RumSavedView } from '@/app/rum/api';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useTranslation } from '@/utils/i18n';

export interface ViewPreset { nameKey: string; fallback: string; context: Record<string, string> }

/** Context keys stored with a saved view (Haro parity). */
const STORED_KEYS = [
  'application',
  'sessionId',
  'route',
  'device',
  'browser',
  'country',
  'userId',
  'hasError',
  'hasReplay',
  'status',
  'release',
  'orderBy',
  'mode',
] as const;

function currentContext(params: URLSearchParams): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of STORED_KEYS) {
    const v = params.get(key);
    if (v) out[key] = v;
  }
  return out;
}

export default function SavedViewsBar({
  screen,
  presets,
}: {
  screen: 'sessions' | 'views' | 'errors';
  presets: ViewPreset[];
}) {
  const { t } = useTranslation();
  const { searchParams, setParams } = useRumSearchParams();
  const { listSavedViews, createSavedView, deleteSavedView } = useRumQueries();
  const [open, setOpen] = useState(false);
  const [views, setViews] = useState<RumSavedView[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [shared, setShared] = useState(false);

  const ctx = JSON.stringify(currentContext(searchParams));

  const reload = useCallback(async () => {
    try {
      setViews(await listSavedViews(screen));
      setError('');
    } catch (err) {
      setViews([]);
      setError(rumErrorMessage(err, t));
    }
  }, [listSavedViews, screen, t]);

  useEffect(() => {
    if (open) void reload();
  }, [open, reload]);

  const mine = views.filter((v) => !v.shared);
  const sharedViews = views.filter((v) => v.shared);
  const activeView = views.some((v) => ctx === v.contextJson);

  function applyContext(context: Record<string, string>) {
    const patch: Record<string, string | null> = {};
    for (const key of STORED_KEYS) patch[key] = null;
    for (const [key, value] of Object.entries(context)) {
      if (value) patch[key] = value;
    }
    setParams(patch);
    setOpen(false);
  }

  function clearContext() {
    const patch: Record<string, string | null> = {};
    for (const key of STORED_KEYS) patch[key] = null;
    setParams(patch);
    setOpen(false);
  }

  async function handleSave() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    setError('');
    try {
      await createSavedView({
        screen,
        name: trimmed,
        contextJson: JSON.stringify(currentContext(searchParams)),
        shared,
      });
      setName('');
      setShared(false);
      await reload();
    } catch (err) {
      setError(rumErrorMessage(err, t));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    setError('');
    try {
      await deleteSavedView(id);
      await reload();
    } catch (err) {
      setError(rumErrorMessage(err, t));
    }
  }

  const panel = (
    <div className="w-72 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-1.5 shadow-lg">
      <div className="border-b border-[var(--color-border-2)] px-2 pb-1.5">
        <button
          type="button"
          className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--color-fill-2)]"
          onClick={clearContext}
        >
          {t('rum.savedViews.clear', '清除筛选')}
        </button>
      </div>

      <p className="px-2 pb-0.5 pt-2 text-[11px] font-medium text-[var(--color-text-3)]">
        {t('rum.savedViews.presets', '预设')}
      </p>
      {presets.map((preset) => (
        <button
          key={preset.nameKey}
          type="button"
          className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-[var(--color-fill-2)]"
          onClick={() => applyContext(preset.context)}
        >
          {t(preset.nameKey, preset.fallback)}
        </button>
      ))}

      <p className="px-2 pb-0.5 pt-2 text-[11px] font-medium text-[var(--color-text-3)]">
        {t('rum.savedViews.mine', '我的视图')}
      </p>
      {views.length === 0 ? (
        <p className="px-2 py-1 text-[11px] text-[var(--color-text-3)]">
          {t('rum.savedViews.empty', '还没有保存的视图')}
        </p>
      ) : (
        [...sharedViews, ...mine].map((view) => (
          <div key={view.id} className="group flex items-center justify-between gap-1 rounded px-2 py-1">
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-1.5 text-left text-sm hover:text-[var(--color-primary)]"
              onClick={() => {
                try {
                  applyContext(JSON.parse(view.contextJson) as Record<string, string>);
                } catch {
                  /* ignore malformed */
                }
              }}
            >
              {view.shared ? (
                <GlobalOutlined className="shrink-0 text-[var(--color-text-3)]" />
              ) : (
                <LockOutlined className="shrink-0 text-[var(--color-text-3)]" />
              )}
              <span className="truncate">{view.name}</span>
              {ctx === view.contextJson ? (
                <CheckOutlined className="shrink-0 text-[var(--color-primary)]" />
              ) : null}
            </button>
            <Popconfirm
              title={t('rum.savedViews.deleteConfirm', '删除「{name}」？', { name: view.name })}
              onConfirm={() => void handleDelete(view.id)}
              okText={t('rum.common.delete', '删除')}
              cancelText={t('rum.common.cancel', '取消')}
            >
              <button
                type="button"
                className="shrink-0 text-[var(--color-text-3)] opacity-0 transition-opacity hover:text-[var(--color-fail)] group-hover:opacity-100"
                aria-label={t('rum.savedViews.deleteConfirm', '删除「{name}」？', { name: view.name })}
              >
                <DeleteOutlined />
              </button>
            </Popconfirm>
          </div>
        ))
      )}

      <div className="border-t border-[var(--color-border-2)] px-1 pb-0.5 pt-2">
        <p className="pb-1 text-[11px] font-medium text-[var(--color-text-3)]">
          {t('rum.savedViews.save', '保存当前筛选')}
        </p>
        <div className="space-y-1.5">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('rum.savedViews.namePlaceholder', '视图名称')}
            size="small"
          />
          <div className="flex items-center justify-between gap-1.5 text-sm">
            <span>{t('rum.savedViews.sharedLabel', '共享')}</span>
            <Switch size="small" checked={shared} onChange={setShared} />
          </div>
          {error ? <p className="text-xs text-[var(--color-fail)]">{error}</p> : null}
          <Button
            type="primary"
            size="small"
            className="w-full"
            icon={<PlusOutlined />}
            loading={saving}
            disabled={!name.trim()}
            onClick={() => void handleSave()}
          >
            {t('rum.savedViews.save', '保存当前筛选')}
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <Dropdown trigger={['click']} open={open} onOpenChange={setOpen} popupRender={() => panel}>
      <Button
        icon={<BookOutlined aria-hidden="true" />}
        className={activeView ? 'border-[var(--color-primary)]' : undefined}
      >
        {t('rum.savedViews.title', '已保存视图')}
      </Button>
    </Dropdown>
  );
}
