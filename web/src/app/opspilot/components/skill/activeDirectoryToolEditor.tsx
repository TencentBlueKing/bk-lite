'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Input, InputNumber, Switch, message } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import ToolConnectionStatusTag from '@/app/opspilot/components/opspilot-tool-editor/tool-connection-status-tag';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type ActiveDirectoryTestStatus = 'untested' | 'success' | 'failed';

export interface ActiveDirectoryInstanceFormValue {
  id: string;
  name: string;
  host: string;
  port: number;
  use_ssl: boolean;
  verify_cert: boolean;
  ca_cert: string;
  bind_dn: string;
  bind_password: string;
  base_dn: string;
  testStatus: ActiveDirectoryTestStatus;
}

const INSTANCES_KEY = 'ad_instances';
const DEFAULT_INSTANCE_ID_KEY = 'ad_default_instance_id';
const AUTO_NAME_PREFIX = 'AD - ';

const createId = () => `ad-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultInstance = (name: string): ActiveDirectoryInstanceFormValue => ({
  id: createId(),
  name,
  host: '',
  port: 636,
  use_ssl: true,
  verify_cert: true,
  ca_cert: '',
  bind_dn: '',
  bind_password: '',
  base_dn: '',
  testStatus: 'untested',
});

const getNextName = (instances: ActiveDirectoryInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => {
    const match = inst.name.match(/^AD - (\d+)$/);
    return match ? Math.max(m, Number(match[1])) : m;
  }, 0);
  return `${AUTO_NAME_PREFIX}${max + 1}`;
};

const parseBoolean = (value: unknown, defaultValue = false) => {
  if (typeof value === 'boolean') return value;
  if (value === undefined || value === null || value === '') return defaultValue;
  if (typeof value === 'string') return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
  return Boolean(value);
};

const parseInt10 = (value: unknown, defaultValue: number) => {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const n = parseInt(value, 10);
    return Number.isNaN(n) ? defaultValue : n;
  }
  return defaultValue;
};

const parseInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

const mapRawInstance = (item: Record<string, unknown>, index: number): ActiveDirectoryInstanceFormValue => {
  const useSsl = parseBoolean(item.use_ssl, true);
  const defaultPort = useSsl ? 636 : 389;
  return {
    id: String(item.id || `ad-${index + 1}`),
    name: String(item.name || `${AUTO_NAME_PREFIX}${index + 1}`),
    host: String(item.host || item.ad_host || ''),
    port: parseInt10(item.port ?? item.ad_port, defaultPort),
    use_ssl: useSsl,
    verify_cert: parseBoolean(item.verify_cert ?? item.ad_verify_cert, true),
    ca_cert: String(item.ca_cert || item.ad_ca_cert || '').trim(),
    bind_dn: String(item.bind_dn || item.ad_bind_dn || ''),
    bind_password: String(item.bind_password || item.ad_bind_password || ''),
    base_dn: String(item.base_dn || item.ad_base_dn || ''),
    testStatus: 'untested',
  };
};

export const parseActiveDirectoryToolConfig = (kwargs: ToolVariable[] = []): ActiveDirectoryInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => mapRawInstance(item, i));
  }
  const hasLegacy = ['host', 'bind_dn', 'bind_password', 'base_dn', 'ad_host', 'ad_bind_dn', 'ad_bind_password', 'ad_base_dn'].some(
    (key) => map.has(key)
  );
  if (hasLegacy) {
    return [
      mapRawInstance(
        {
          id: 'ad-1',
          name: 'AD - 1',
          host: map.get('host') || map.get('ad_host'),
          port: map.get('port') || map.get('ad_port'),
          use_ssl: map.get('use_ssl') ?? map.get('ad_use_ssl') ?? true,
          verify_cert: map.get('verify_cert') ?? map.get('ad_verify_cert') ?? true,
          ca_cert: map.get('ca_cert') || map.get('ad_ca_cert') || '',
          bind_dn: map.get('bind_dn') || map.get('ad_bind_dn'),
          bind_password: map.get('bind_password') || map.get('ad_bind_password'),
          base_dn: map.get('base_dn') || map.get('ad_base_dn'),
        },
        0
      ),
    ];
  }
  return [getDefaultInstance('AD - 1')];
};

const serializeActiveDirectoryToolConfig = (instances: ActiveDirectoryInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => {
    const copy = { ...inst } as Partial<ActiveDirectoryInstanceFormValue>;
    delete copy.testStatus;
    return copy;
  });
  return [
    { key: INSTANCES_KEY, value: JSON.stringify(normalized) },
    { key: DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
  ];
};

export interface ActiveDirectoryToolEditorHandle {
  save: () => boolean;
}

interface ActiveDirectoryToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const ActiveDirectoryToolEditor = forwardRef<ActiveDirectoryToolEditorHandle, ActiveDirectoryToolEditorProps>(
  ({ initialKwargs, onSave }, ref) => {
    const { t } = useTranslation();
    const { testAdConnection } = useSkillApi();
    const [instances, setInstances] = useState<ActiveDirectoryInstanceFormValue[]>(() =>
      parseActiveDirectoryToolConfig(initialKwargs)
    );
    const [selectedId, setSelectedId] = useState<string | null>(
      () => parseActiveDirectoryToolConfig(initialKwargs)[0]?.id ?? null
    );
    const [testing, setTesting] = useState(false);
    const selectedInstance = instances.find((inst) => inst.id === selectedId) ?? null;

    const listRef = useRef<HTMLDivElement>(null);
    const prevLengthRef = useRef(instances.length);
    useEffect(() => {
      if (instances.length > prevLengthRef.current && listRef.current) {
        listRef.current.scrollTop = listRef.current.scrollHeight;
      }
      prevLengthRef.current = instances.length;
    }, [instances.length]);

    useImperativeHandle(ref, () => ({
      save: () => {
        const trimmedNames = instances.map((inst) => inst.name.trim()).filter(Boolean);
        if (instances.length === 0) {
          message.error(t('tool.activedirectory.noInstances'));
          return false;
        }
        if (trimmedNames.length !== instances.length) {
          message.error(t('tool.activedirectory.instanceNameRequired'));
          return false;
        }
        if (new Set(trimmedNames).size !== trimmedNames.length) {
          message.error(t('tool.activedirectory.duplicateInstanceName'));
          return false;
        }
        if (instances.some((inst) => !inst.host.trim())) {
          message.error(t('tool.activedirectory.hostRequired'));
          return false;
        }
        if (instances.some((inst) => !inst.bind_dn.trim())) {
          message.error(t('tool.activedirectory.bindDnRequired'));
          return false;
        }
        if (instances.some((inst) => !inst.bind_password)) {
          message.error(t('tool.activedirectory.passwordRequired'));
          return false;
        }
        if (instances.some((inst) => !inst.base_dn.trim())) {
          message.error(t('tool.activedirectory.baseDnRequired'));
          return false;
        }
        const trimmed = instances.map((inst) => ({
          ...inst,
          name: inst.name.trim(),
          host: inst.host.trim(),
          bind_dn: inst.bind_dn.trim(),
          base_dn: inst.base_dn.trim(),
          ca_cert: inst.ca_cert.trim(),
        }));
        onSave(serializeActiveDirectoryToolConfig(trimmed));
        return true;
      },
    }));

    const handleAdd = () => {
      const next = getDefaultInstance(getNextName(instances));
      setInstances((prev) => [...prev, next]);
      setSelectedId(next.id);
    };

    const handleDelete = (id: string) => {
      setInstances((prev) => {
        const next = prev.filter((inst) => inst.id !== id);
        if (selectedId === id) setSelectedId(next[0]?.id ?? null);
        return next;
      });
    };

    const handleChange = <K extends keyof ActiveDirectoryInstanceFormValue>(
      id: string,
      field: K,
      value: ActiveDirectoryInstanceFormValue[K]
    ) => {
      setInstances((prev) =>
        prev.map((inst) => {
          if (inst.id !== id) return inst;
          const next = { ...inst, [field]: value, testStatus: 'untested' as const };
          if (field === 'use_ssl') {
            const sslOn = Boolean(value);
            if (sslOn && (inst.port === 389 || !inst.port)) next.port = 636;
            if (!sslOn && (inst.port === 636 || !inst.port)) next.port = 389;
          }
          return next;
        })
      );
    };

    const handleTest = async () => {
      if (!selectedInstance) return;
      setTesting(true);
      try {
        const payload = { ...selectedInstance } as Partial<ActiveDirectoryInstanceFormValue>;
        delete payload.testStatus;
        await testAdConnection(payload as Omit<ActiveDirectoryInstanceFormValue, 'testStatus'>);
        message.success(t('tool.activedirectory.status.success'));
        setInstances((prev) =>
          prev.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst))
        );
      } catch {
        setInstances((prev) =>
          prev.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst))
        );
      } finally {
        setTesting(false);
      }
    };

    return (
      <div className="flex gap-4 min-h-[480px]">
        <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
          <div className="mb-3 flex items-center justify-between">
            <span className="font-medium">{t('tool.activedirectory.instances')}</span>
            <Button type="primary" ghost size="small" onClick={handleAdd}>
              + {t('common.add')}
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
            {instances.length === 0 ? (
              <CompactEmptyState description={t('tool.activedirectory.noInstances')} />
            ) : (
              instances.map((instance) => {
                const isActive = instance.id === selectedId;
                return (
                  <div
                    key={instance.id}
                    className={`flex w-full items-start gap-2 rounded border p-3 transition ${
                      isActive
                        ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]'
                        : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'
                    }`}
                  >
                    <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setSelectedId(instance.id)}>
                      <div className="truncate font-medium">
                        {instance.name || t('tool.activedirectory.unnamedInstance')}
                      </div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.host
                          ? `${instance.host}:${instance.port}`
                          : t('tool.activedirectory.addressNotConfigured')}
                      </div>
                    </button>
                    <Button
                      type="link"
                      size="small"
                      danger
                      aria-label={t('common.delete')}
                      icon={<DeleteOutlined />}
                      onClick={() => handleDelete(instance.id)}
                    />
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="flex-1 rounded border border-[var(--color-border)] p-4">
          {selectedInstance ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-lg font-medium">
                  {t('tool.activedirectory.configTitle').replace(
                    '{name}',
                    selectedInstance.name || t('tool.activedirectory.unnamedInstance')
                  )}
                </div>
                <ToolConnectionStatusTag scope="tool.activedirectory" status={selectedInstance.testStatus} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.activedirectory.instanceName')}</div>
                <Input
                  value={selectedInstance.name}
                  onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)}
                  placeholder={t('tool.activedirectory.instanceNamePlaceholder')}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.activedirectory.host')}</div>
                  <Input
                    value={selectedInstance.host}
                    onChange={(e) => handleChange(selectedInstance.id, 'host', e.target.value)}
                    placeholder={t('tool.activedirectory.hostPlaceholder')}
                  />
                </div>
                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.activedirectory.port')}</div>
                  <InputNumber
                    style={{ width: '100%' }}
                    value={selectedInstance.port}
                    min={1}
                    max={65535}
                    onChange={(v) => handleChange(selectedInstance.id, 'port', v ?? (selectedInstance.use_ssl ? 636 : 389))}
                    placeholder={selectedInstance.use_ssl ? '636' : '389'}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={selectedInstance.use_ssl}
                  onChange={(checked) => handleChange(selectedInstance.id, 'use_ssl', checked)}
                />
                <span>{t('tool.activedirectory.useSsl')}</span>
              </div>
              {selectedInstance.use_ssl ? (
                <>
                  <div>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={selectedInstance.verify_cert}
                        onChange={(checked) => handleChange(selectedInstance.id, 'verify_cert', checked)}
                      />
                      <span>{t('tool.activedirectory.verifyCert')}</span>
                    </div>
                    <div className="mt-1 text-xs text-[var(--color-text-4)]">{t('tool.activedirectory.verifyCertHint')}</div>
                  </div>
                  {selectedInstance.verify_cert ? (
                    <div>
                      <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.activedirectory.caCert')}</div>
                      <Input.TextArea
                        value={selectedInstance.ca_cert}
                        onChange={(e) => handleChange(selectedInstance.id, 'ca_cert', e.target.value)}
                        placeholder={t('tool.activedirectory.caCertPlaceholder')}
                        rows={4}
                        className="font-mono text-xs"
                      />
                      <div className="mt-1 text-xs text-[var(--color-text-4)]">{t('tool.activedirectory.caCertHint')}</div>
                    </div>
                  ) : null}
                </>
              ) : null}
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.activedirectory.bindDn')}</div>
                <Input
                  value={selectedInstance.bind_dn}
                  onChange={(e) => handleChange(selectedInstance.id, 'bind_dn', e.target.value)}
                  placeholder={t('tool.activedirectory.bindDnPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.activedirectory.password')}</div>
                <Input.Password
                  value={selectedInstance.bind_password}
                  onChange={(e) => handleChange(selectedInstance.id, 'bind_password', e.target.value)}
                  placeholder={t('tool.activedirectory.passwordPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.activedirectory.baseDn')}</div>
                <Input
                  value={selectedInstance.base_dn}
                  onChange={(e) => handleChange(selectedInstance.id, 'base_dn', e.target.value)}
                  placeholder={t('tool.activedirectory.baseDnPlaceholder')}
                />
                <div className="mt-1 text-xs text-[var(--color-text-4)]">{t('tool.activedirectory.baseDnHint')}</div>
              </div>
              <div className="flex justify-end">
                <Button loading={testing} onClick={handleTest}>
                  {t('tool.activedirectory.testConnection')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <CompactEmptyState description={t('tool.activedirectory.selectInstance')} />
            </div>
          )}
        </div>
      </div>
    );
  }
);

ActiveDirectoryToolEditor.displayName = 'ActiveDirectoryToolEditor';
export default ActiveDirectoryToolEditor;
