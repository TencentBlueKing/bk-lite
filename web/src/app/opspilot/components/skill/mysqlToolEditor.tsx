'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Empty, Input, InputNumber, Switch, Tag, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type MysqlTestStatus = 'untested' | 'success' | 'failed';

export interface MysqlInstanceFormValue {
  id: string;
  name: string;
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  charset: string;
  collation: string;
  ssl: boolean;
  ssl_ca: string;
  ssl_cert: string;
  ssl_key: string;
  testStatus: MysqlTestStatus;
}

// ── constants ─────────────────────────────────────────────────────────────────
const INSTANCES_KEY = 'mysql_instances';
const DEFAULT_INSTANCE_ID_KEY = 'mysql_default_instance_id';
const AUTO_NAME_PREFIX = 'MySQL - ';

// ── helpers ───────────────────────────────────────────────────────────────────
const createId = () => `mysql-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultInstance = (name: string): MysqlInstanceFormValue => ({
  id: createId(),
  name,
  host: '',
  port: 3306,
  database: '',
  user: '',
  password: '',
  charset: 'utf8mb4',
  collation: 'utf8mb4_unicode_ci',
  ssl: false,
  ssl_ca: '',
  ssl_cert: '',
  ssl_key: '',
  testStatus: 'untested',
});

const getNextName = (instances: MysqlInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => {
    const match = inst.name.match(/^MySQL - (\d+)$/);
    return match ? Math.max(m, Number(match[1])) : m;
  }, 0);
  return `${AUTO_NAME_PREFIX}${max + 1}`;
};

const parseBoolean = (value: unknown) => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
  return Boolean(value);
};

const parseInt10 = (value: unknown, defaultValue: number) => {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') { const n = parseInt(value, 10); return isNaN(n) ? defaultValue : n; }
  return defaultValue;
};

const parseInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) {
    try { const p = JSON.parse(value); return Array.isArray(p) ? p : []; } catch { return []; }
  }
  return [];
};

export const parseMysqlToolConfig = (kwargs: ToolVariable[] = []): MysqlInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => ({
      id: String(item.id || `mysql-${i + 1}`),
      name: String(item.name || `${AUTO_NAME_PREFIX}${i + 1}`),
      host: String(item.host || ''),
      port: parseInt10(item.port, 3306),
      database: String(item.database || ''),
      user: String(item.user || ''),
      password: String(item.password || ''),
      charset: String(item.charset || 'utf8mb4'),
      collation: String(item.collation || 'utf8mb4_unicode_ci'),
      ssl: parseBoolean(item.ssl),
      ssl_ca: String(item.ssl_ca || ''),
      ssl_cert: String(item.ssl_cert || ''),
      ssl_key: String(item.ssl_key || ''),
      testStatus: 'untested',
    }));
  }
  const hasLegacy = ['host', 'port', 'database', 'user', 'password'].some((k) => map.has(k));
  if (hasLegacy) {
    return [{
      id: 'mysql-1', name: 'MySQL - 1',
      host: String(map.get('host') || ''), port: parseInt10(map.get('port'), 3306),
      database: String(map.get('database') || ''), user: String(map.get('user') || ''),
      password: String(map.get('password') || ''), charset: String(map.get('charset') || 'utf8mb4'),
      collation: String(map.get('collation') || 'utf8mb4_unicode_ci'), ssl: parseBoolean(map.get('ssl')),
      ssl_ca: String(map.get('ssl_ca') || ''), ssl_cert: String(map.get('ssl_cert') || ''),
      ssl_key: String(map.get('ssl_key') || ''), testStatus: 'untested',
    }];
  }
  return [getDefaultInstance('MySQL - 1')];
};

const serializeMysqlToolConfig = (instances: MysqlInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => { const c = { ...inst } as Partial<MysqlInstanceFormValue>; delete c.testStatus; return c; });
  return [
    { key: INSTANCES_KEY, value: JSON.stringify(normalized) },
    { key: DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
  ];
};

// ── ref handle ────────────────────────────────────────────────────────────────
export interface MysqlToolEditorHandle { save: () => boolean; }

const statusColorMap: Record<MysqlTestStatus, string> = { untested: 'default', success: 'blue', failed: 'red' };

interface MysqlToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const MysqlToolEditor = forwardRef<MysqlToolEditorHandle, MysqlToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { testMysqlConnection } = useSkillApi();
  const [instances, setInstances] = useState<MysqlInstanceFormValue[]>(() => parseMysqlToolConfig(initialKwargs));
  const [selectedId, setSelectedId] = useState<string | null>(() => parseMysqlToolConfig(initialKwargs)[0]?.id ?? null);
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
      if (instances.length === 0) { message.error(t('tool.mysql.noInstances')); return false; }
      if (trimmedNames.length !== instances.length) { message.error(t('tool.mysql.instanceNameRequired')); return false; }
      if (new Set(trimmedNames).size !== trimmedNames.length) { message.error(t('tool.mysql.duplicateInstanceName')); return false; }
      if (instances.some((inst) => !inst.host.trim())) { message.error(t('tool.mysql.hostRequired')); return false; }
      const trimmed = instances.map((inst) => ({ ...inst, name: inst.name.trim(), host: inst.host.trim() }));
      onSave(serializeMysqlToolConfig(trimmed));
      return true;
    },
  }));

  const handleAdd = () => { const next = getDefaultInstance(getNextName(instances)); setInstances((p) => [...p, next]); setSelectedId(next.id); };
  const handleDelete = (id: string) => {
    setInstances((p) => { const n = p.filter((inst) => inst.id !== id); if (selectedId === id) setSelectedId(n[0]?.id ?? null); return n; });
  };
  const handleChange = <K extends keyof MysqlInstanceFormValue>(id: string, field: K, value: MysqlInstanceFormValue[K]) => {
    setInstances((p) => p.map((inst) => (inst.id === id ? { ...inst, [field]: value, testStatus: 'untested' } : inst)));
  };
  const handleTest = async () => {
    if (!selectedInstance) return;
    setTesting(true);
    try {
      const payload = { ...selectedInstance } as Partial<MysqlInstanceFormValue>; delete payload.testStatus;
      await testMysqlConnection(payload as Omit<MysqlInstanceFormValue, 'testStatus'>);
      message.success(t('tool.mysql.status.success'));
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst)));
    } catch {
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst)));
    } finally { setTesting(false); }
  };

  const renderStatus = (status: MysqlTestStatus) => <Tag color={statusColorMap[status]}>{t(`tool.mysql.status.${status}`)}</Tag>;

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.mysql.instances')}</span>
          <Button type="primary" ghost size="small" onClick={handleAdd}>+ {t('common.add')}</Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.mysql.noInstances')} />
          ) : instances.map((instance) => {
            const isActive = instance.id === selectedId;
            return (
              <button key={instance.id} type="button"
                className={`w-full rounded border p-3 text-left transition ${isActive ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'}`}
                onClick={() => setSelectedId(instance.id)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{instance.name || t('tool.mysql.unnamedInstance')}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                      {instance.host ? `${instance.host}:${instance.port}` : t('tool.mysql.addressNotConfigured')}
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
              <div className="text-lg font-medium">{t('tool.mysql.configTitle').replace('{name}', selectedInstance.name || t('tool.mysql.unnamedInstance'))}</div>
              {renderStatus(selectedInstance.testStatus)}
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.instanceName')}</div>
              <Input value={selectedInstance.name} onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)} placeholder={t('tool.mysql.instanceNamePlaceholder')} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.host')}</div>
                <Input value={selectedInstance.host} onChange={(e) => handleChange(selectedInstance.id, 'host', e.target.value)} placeholder={t('tool.mysql.hostPlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.port')}</div>
                <InputNumber style={{ width: '100%' }} value={selectedInstance.port} min={1} max={65535} onChange={(v) => handleChange(selectedInstance.id, 'port', v ?? 3306)} placeholder="3306" />
              </div>
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.database')}</div>
              <Input value={selectedInstance.database} onChange={(e) => handleChange(selectedInstance.id, 'database', e.target.value)} placeholder={t('tool.mysql.databasePlaceholder')} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.user')}</div>
                <Input value={selectedInstance.user} onChange={(e) => handleChange(selectedInstance.id, 'user', e.target.value)} placeholder={t('tool.mysql.userPlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.password')}</div>
                <Input.Password value={selectedInstance.password} onChange={(e) => handleChange(selectedInstance.id, 'password', e.target.value)} placeholder={t('tool.mysql.passwordPlaceholder')} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.charset')}</div>
                <Input value={selectedInstance.charset} onChange={(e) => handleChange(selectedInstance.id, 'charset', e.target.value)} placeholder="utf8mb4" />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.collation')}</div>
                <Input value={selectedInstance.collation} onChange={(e) => handleChange(selectedInstance.id, 'collation', e.target.value)} placeholder="utf8mb4_unicode_ci" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={selectedInstance.ssl} onChange={(checked) => handleChange(selectedInstance.id, 'ssl', checked)} />
              <span>{t('tool.mysql.ssl')}</span>
            </div>
            {selectedInstance.ssl && (
              <>
                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.sslCa')}</div>
                  <Input value={selectedInstance.ssl_ca} onChange={(e) => handleChange(selectedInstance.id, 'ssl_ca', e.target.value)} placeholder={t('tool.mysql.sslCaPlaceholder')} />
                </div>
                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.sslCert')}</div>
                  <Input value={selectedInstance.ssl_cert} onChange={(e) => handleChange(selectedInstance.id, 'ssl_cert', e.target.value)} placeholder={t('tool.mysql.sslCertPlaceholder')} />
                </div>
                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.sslKey')}</div>
                  <Input value={selectedInstance.ssl_key} onChange={(e) => handleChange(selectedInstance.id, 'ssl_key', e.target.value)} placeholder={t('tool.mysql.sslKeyPlaceholder')} />
                </div>
              </>
            )}
            <div className="flex justify-end">
              <Button loading={testing} onClick={handleTest}>{t('tool.mysql.testConnection')}</Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.mysql.selectInstance')} />
          </div>
        )}
      </div>
    </div>
  );
});

MysqlToolEditor.displayName = 'MysqlToolEditor';
export default MysqlToolEditor;
