'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Empty, Input, InputNumber, Tag, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type MssqlTestStatus = 'untested' | 'success' | 'failed';

export interface MssqlInstanceFormValue {
  id: string;
  name: string;
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  testStatus: MssqlTestStatus;
}

const INSTANCES_KEY = 'mssql_instances';
const DEFAULT_INSTANCE_ID_KEY = 'mssql_default_instance_id';
const AUTO_NAME_PREFIX = 'MSSQL - ';

const createId = () => `mssql-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const getDefaultInstance = (name: string): MssqlInstanceFormValue => ({
  id: createId(), name, host: '', port: 1433, database: 'master', user: '', password: '', testStatus: 'untested',
});
const getNextName = (instances: MssqlInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => { const match = inst.name.match(/^MSSQL - (\d+)$/); return match ? Math.max(m, Number(match[1])) : m; }, 0);
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

export const parseMssqlToolConfig = (kwargs: ToolVariable[] = []): MssqlInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => ({
      id: String(item.id || `mssql-${i + 1}`), name: String(item.name || `${AUTO_NAME_PREFIX}${i + 1}`),
      host: String(item.host || ''), port: parseInt10(item.port, 1433), database: String(item.database || 'master'),
      user: String(item.user || ''), password: String(item.password || ''), testStatus: 'untested',
    }));
  }
  const hasLegacy = ['host', 'port', 'database', 'user', 'password'].some((k) => map.has(k));
  if (hasLegacy) {
    return [{ id: 'mssql-1', name: 'MSSQL - 1', host: String(map.get('host') || ''), port: parseInt10(map.get('port'), 1433),
      database: String(map.get('database') || 'master'), user: String(map.get('user') || ''),
      password: String(map.get('password') || ''), testStatus: 'untested' }];
  }
  return [getDefaultInstance('MSSQL - 1')];
};

const serializeMssqlToolConfig = (instances: MssqlInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => { const c = { ...inst } as Partial<MssqlInstanceFormValue>; delete c.testStatus; return c; });
  return [{ key: INSTANCES_KEY, value: JSON.stringify(normalized) }, { key: DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' }];
};

export interface MssqlToolEditorHandle { save: () => boolean; }
const statusColorMap: Record<MssqlTestStatus, string> = { untested: 'default', success: 'blue', failed: 'red' };

interface MssqlToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const MssqlToolEditor = forwardRef<MssqlToolEditorHandle, MssqlToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { testMssqlConnection } = useSkillApi();
  const [instances, setInstances] = useState<MssqlInstanceFormValue[]>(() => parseMssqlToolConfig(initialKwargs));
  const [selectedId, setSelectedId] = useState<string | null>(() => parseMssqlToolConfig(initialKwargs)[0]?.id ?? null);
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
      if (instances.length === 0) { message.error(t('tool.mssql.noInstances')); return false; }
      if (trimmedNames.length !== instances.length) { message.error(t('tool.mssql.instanceNameRequired')); return false; }
      if (new Set(trimmedNames).size !== trimmedNames.length) { message.error(t('tool.mssql.duplicateInstanceName')); return false; }
      if (instances.some((inst) => !inst.host.trim())) { message.error(t('tool.mssql.hostRequired')); return false; }
      const trimmed = instances.map((inst) => ({ ...inst, name: inst.name.trim(), host: inst.host.trim() }));
      onSave(serializeMssqlToolConfig(trimmed));
      return true;
    },
  }));

  const handleAdd = () => { const next = getDefaultInstance(getNextName(instances)); setInstances((p) => [...p, next]); setSelectedId(next.id); };
  const handleDelete = (id: string) => {
    setInstances((p) => { const n = p.filter((inst) => inst.id !== id); if (selectedId === id) setSelectedId(n[0]?.id ?? null); return n; });
  };
  const handleChange = <K extends keyof MssqlInstanceFormValue>(id: string, field: K, value: MssqlInstanceFormValue[K]) => {
    setInstances((p) => p.map((inst) => (inst.id === id ? { ...inst, [field]: value, testStatus: 'untested' } : inst)));
  };
  const handleTest = async () => {
    if (!selectedInstance) return;
    setTesting(true);
    try {
      const payload = { ...selectedInstance } as Partial<MssqlInstanceFormValue>; delete payload.testStatus;
      await testMssqlConnection(payload as Omit<MssqlInstanceFormValue, 'testStatus'>);
      message.success(t('tool.mssql.status.success'));
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst)));
    } catch {
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst)));
    } finally { setTesting(false); }
  };

  const renderStatus = (status: MssqlTestStatus) => <Tag color={statusColorMap[status]}>{t(`tool.mssql.status.${status}`)}</Tag>;

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.mssql.instances')}</span>
          <Button type="primary" ghost size="small" onClick={handleAdd}>+ {t('common.add')}</Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.mssql.noInstances')} />
          ) : instances.map((instance) => {
            const isActive = instance.id === selectedId;
            return (
              <button key={instance.id} type="button"
                className={`w-full rounded border p-3 text-left transition ${isActive ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'}`}
                onClick={() => setSelectedId(instance.id)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{instance.name || t('tool.mssql.unnamedInstance')}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                      {instance.host ? `${instance.host}:${instance.port}` : t('tool.mssql.addressNotConfigured')}
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
              <div className="text-lg font-medium">{t('tool.mssql.configTitle').replace('{name}', selectedInstance.name || t('tool.mssql.unnamedInstance'))}</div>
              {renderStatus(selectedInstance.testStatus)}
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.instanceName')}</div>
              <Input value={selectedInstance.name} onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)} placeholder={t('tool.mssql.instanceNamePlaceholder')} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.host')}</div>
                <Input value={selectedInstance.host} onChange={(e) => handleChange(selectedInstance.id, 'host', e.target.value)} placeholder={t('tool.mssql.hostPlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.port')}</div>
                <InputNumber style={{ width: '100%' }} value={selectedInstance.port} min={1} max={65535} onChange={(v) => handleChange(selectedInstance.id, 'port', v ?? 1433)} placeholder="1433" />
              </div>
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.database')}</div>
              <Input value={selectedInstance.database} onChange={(e) => handleChange(selectedInstance.id, 'database', e.target.value)} placeholder="master" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.user')}</div>
                <Input value={selectedInstance.user} onChange={(e) => handleChange(selectedInstance.id, 'user', e.target.value)} placeholder={t('tool.mssql.userPlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.password')}</div>
                <Input.Password value={selectedInstance.password} onChange={(e) => handleChange(selectedInstance.id, 'password', e.target.value)} placeholder={t('tool.mssql.passwordPlaceholder')} />
              </div>
            </div>
            <div className="flex justify-end">
              <Button loading={testing} onClick={handleTest}>{t('tool.mssql.testConnection')}</Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.mssql.selectInstance')} />
          </div>
        )}
      </div>
    </div>
  );
});

MssqlToolEditor.displayName = 'MssqlToolEditor';
export default MssqlToolEditor;
