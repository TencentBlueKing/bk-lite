'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Empty, Input, InputNumber, Tag, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type PostgresTestStatus = 'untested' | 'success' | 'failed';

export interface PostgresInstanceFormValue {
  id: string;
  name: string;
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  testStatus: PostgresTestStatus;
}

const INSTANCES_KEY = 'postgres_instances';
const DEFAULT_INSTANCE_ID_KEY = 'postgres_default_instance_id';
const AUTO_NAME_PREFIX = 'PostgreSQL - ';

const createId = () => `postgres-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const getDefaultInstance = (name: string): PostgresInstanceFormValue => ({
  id: createId(), name, host: '', port: 5432, database: 'postgres', user: '', password: '', testStatus: 'untested',
});
const getNextName = (instances: PostgresInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => { const match = inst.name.match(/^PostgreSQL - (\d+)$/); return match ? Math.max(m, Number(match[1])) : m; }, 0);
  return `${AUTO_NAME_PREFIX}${max + 1}`;
};
const parseInt10 = (value: unknown, defaultValue: number) => {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') { const n = parseInt(value, 10); return isNaN(n) ? defaultValue : n; }
  return defaultValue;
};
const parseInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) { try { const p = JSON.parse(value); return Array.isArray(p) ? p : []; } catch { return []; } }
  return [];
};

export const parsePostgresToolConfig = (kwargs: ToolVariable[] = []): PostgresInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => ({
      id: String(item.id || `postgres-${i + 1}`), name: String(item.name || `${AUTO_NAME_PREFIX}${i + 1}`),
      host: String(item.host || ''), port: parseInt10(item.port, 5432), database: String(item.database || 'postgres'),
      user: String(item.user || ''), password: String(item.password || ''), testStatus: 'untested',
    }));
  }
  const hasLegacy = ['host', 'port', 'database', 'user', 'password'].some((k) => map.has(k));
  if (hasLegacy) {
    return [{ id: 'postgres-1', name: 'PostgreSQL - 1', host: String(map.get('host') || ''), port: parseInt10(map.get('port'), 5432),
      database: String(map.get('database') || 'postgres'), user: String(map.get('user') || ''),
      password: String(map.get('password') || ''), testStatus: 'untested' }];
  }
  return [getDefaultInstance('PostgreSQL - 1')];
};

const serializePostgresToolConfig = (instances: PostgresInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => { const c = { ...inst } as Partial<PostgresInstanceFormValue>; delete c.testStatus; return c; });
  return [{ key: INSTANCES_KEY, value: JSON.stringify(normalized) }, { key: DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' }];
};

export interface PostgresToolEditorHandle { save: () => boolean; }
const statusColorMap: Record<PostgresTestStatus, string> = { untested: 'default', success: 'blue', failed: 'red' };

interface PostgresToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const PostgresToolEditor = forwardRef<PostgresToolEditorHandle, PostgresToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { testPostgresConnection } = useSkillApi();
  const [instances, setInstances] = useState<PostgresInstanceFormValue[]>(() => parsePostgresToolConfig(initialKwargs));
  const [selectedId, setSelectedId] = useState<string | null>(() => parsePostgresToolConfig(initialKwargs)[0]?.id ?? null);
  const [testing, setTesting] = useState(false);
  const selectedInstance = instances.find((inst) => inst.id === selectedId) ?? null;

  const listRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(instances.length);
  useEffect(() => {
    if (instances.length > prevLengthRef.current && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    prevLengthRef.current = instances.length;
  }, [instances.length]);

  useImperativeHandle(ref, () => ({
    save: () => {
      const trimmedNames = instances.map((inst) => inst.name.trim()).filter(Boolean);
      if (instances.length === 0) { message.error(t('tool.postgres.noInstances')); return false; }
      if (trimmedNames.length !== instances.length) { message.error(t('tool.postgres.instanceNameRequired')); return false; }
      if (new Set(trimmedNames).size !== trimmedNames.length) { message.error(t('tool.postgres.duplicateInstanceName')); return false; }
      if (instances.some((inst) => !inst.host.trim())) { message.error(t('tool.postgres.hostRequired')); return false; }
      const trimmed = instances.map((inst) => ({ ...inst, name: inst.name.trim(), host: inst.host.trim() }));
      onSave(serializePostgresToolConfig(trimmed));
      return true;
    },
  }));

  const handleAdd = () => { const next = getDefaultInstance(getNextName(instances)); setInstances((p) => [...p, next]); setSelectedId(next.id); };
  const handleDelete = (id: string) => {
    setInstances((p) => { const n = p.filter((inst) => inst.id !== id); if (selectedId === id) setSelectedId(n[0]?.id ?? null); return n; });
  };
  const handleChange = <K extends keyof PostgresInstanceFormValue>(id: string, field: K, value: PostgresInstanceFormValue[K]) => {
    setInstances((p) => p.map((inst) => (inst.id === id ? { ...inst, [field]: value, testStatus: 'untested' } : inst)));
  };
  const handleTest = async () => {
    if (!selectedInstance) return;
    setTesting(true);
    try {
      const payload = { ...selectedInstance } as Partial<PostgresInstanceFormValue>; delete payload.testStatus;
      await testPostgresConnection(payload as Omit<PostgresInstanceFormValue, 'testStatus'>);
      message.success(t('tool.postgres.status.success'));
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst)));
    } catch {
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst)));
    } finally { setTesting(false); }
  };

  const renderStatus = (status: PostgresTestStatus) => <Tag color={statusColorMap[status]}>{t(`tool.postgres.status.${status}`)}</Tag>;

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.postgres.instances')}</span>
          <Button type="primary" ghost size="small" onClick={handleAdd}>+ {t('common.add')}</Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.postgres.noInstances')} />
          ) : instances.map((instance) => {
            const isActive = instance.id === selectedId;
            return (
              <button key={instance.id} type="button"
                className={`w-full rounded border p-3 text-left transition ${isActive ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'}`}
                onClick={() => setSelectedId(instance.id)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{instance.name || t('tool.postgres.unnamedInstance')}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                      {instance.host ? `${instance.host}:${instance.port}` : t('tool.postgres.addressNotConfigured')}
                    </div>
                  </div>
                  <DeleteOutlined className="mt-1 text-[var(--color-text-3)] hover:text-[var(--color-error)]"
                    onClick={(e) => { e.stopPropagation(); handleDelete(instance.id); }} />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 rounded border border-[var(--color-border)] p-4">
        {selectedInstance ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-lg font-medium">{t('tool.postgres.configTitle').replace('{name}', selectedInstance.name || t('tool.postgres.unnamedInstance'))}</div>
              {renderStatus(selectedInstance.testStatus)}
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.instanceName')}</div>
              <Input value={selectedInstance.name} onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)} placeholder={t('tool.postgres.instanceNamePlaceholder')} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.host')}</div>
                <Input value={selectedInstance.host} onChange={(e) => handleChange(selectedInstance.id, 'host', e.target.value)} placeholder={t('tool.postgres.hostPlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.port')}</div>
                <InputNumber style={{ width: '100%' }} value={selectedInstance.port} min={1} max={65535} onChange={(v) => handleChange(selectedInstance.id, 'port', v ?? 5432)} placeholder="5432" />
              </div>
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.database')}</div>
              <Input value={selectedInstance.database} onChange={(e) => handleChange(selectedInstance.id, 'database', e.target.value)} placeholder="postgres" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.user')}</div>
                <Input value={selectedInstance.user} onChange={(e) => handleChange(selectedInstance.id, 'user', e.target.value)} placeholder={t('tool.postgres.userPlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.password')}</div>
                <Input.Password value={selectedInstance.password} onChange={(e) => handleChange(selectedInstance.id, 'password', e.target.value)} placeholder={t('tool.postgres.passwordPlaceholder')} />
              </div>
            </div>
            <div className="flex justify-end">
              <Button loading={testing} onClick={handleTest}>{t('tool.postgres.testConnection')}</Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.postgres.selectInstance')} />
          </div>
        )}
      </div>
    </div>
  );
});

PostgresToolEditor.displayName = 'PostgresToolEditor';
export default PostgresToolEditor;
