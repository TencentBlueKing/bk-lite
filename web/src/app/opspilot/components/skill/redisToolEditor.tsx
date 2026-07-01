'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Empty, Input, Switch, Tag, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type RedisTestStatus = 'untested' | 'success' | 'failed';

export interface RedisInstanceFormValue {
  id: string;
  name: string;
  url: string;
  username: string;
  password: string;
  ssl: boolean;
  ssl_ca_path: string;
  ssl_keyfile: string;
  ssl_certfile: string;
  ssl_cert_reqs: string;
  ssl_ca_certs: string;
  cluster_mode: boolean;
  testStatus: RedisTestStatus;
}

// ── constants ─────────────────────────────────────────────────────────────────
const INSTANCES_KEY = 'redis_instances';
const DEFAULT_INSTANCE_ID_KEY = 'redis_default_instance_id';
const AUTO_NAME_PREFIX = 'Redis - ';

// ── helpers ───────────────────────────────────────────────────────────────────
const createId = () => `redis-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const getDefaultInstance = (name: string): RedisInstanceFormValue => ({
  id: createId(),
  name,
  url: '',
  username: '',
  password: '',
  ssl: false,
  ssl_ca_path: '',
  ssl_keyfile: '',
  ssl_certfile: '',
  ssl_cert_reqs: '',
  ssl_ca_certs: '',
  cluster_mode: false,
  testStatus: 'untested',
});

const getNextName = (instances: RedisInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => {
    const match = inst.name.match(/^Redis - (\d+)$/);
    return match ? Math.max(m, Number(match[1])) : m;
  }, 0);
  return `${AUTO_NAME_PREFIX}${max + 1}`;
};

const parseBoolean = (value: unknown) => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
  return Boolean(value);
};

const parseInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch { return []; }
  }
  return [];
};

export const parseRedisToolConfig = (kwargs: ToolVariable[] = []): RedisInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => ({
      id: String(item.id || `redis-${i + 1}`),
      name: String(item.name || `${AUTO_NAME_PREFIX}${i + 1}`),
      url: String(item.url || ''),
      username: String(item.username || ''),
      password: String(item.password || ''),
      ssl: parseBoolean(item.ssl),
      ssl_ca_path: String(item.ssl_ca_path || ''),
      ssl_keyfile: String(item.ssl_keyfile || ''),
      ssl_certfile: String(item.ssl_certfile || ''),
      ssl_cert_reqs: String(item.ssl_cert_reqs || ''),
      ssl_ca_certs: String(item.ssl_ca_certs || ''),
      cluster_mode: parseBoolean(item.cluster_mode),
      testStatus: 'untested',
    }));
  }
  return [getDefaultInstance('Redis - 1')];
};

const serializeRedisToolConfig = (instances: RedisInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => {
    const copy = { ...inst } as Partial<RedisInstanceFormValue>;
    delete copy.testStatus;
    return copy;
  });
  return [
    { key: INSTANCES_KEY, value: JSON.stringify(normalized) },
    { key: DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
  ];
};

// ── ref handle ────────────────────────────────────────────────────────────────
export interface RedisToolEditorHandle {
  /** Validates then calls onSave; returns false if validation fails */
  save: () => boolean;
}

// ── status display ────────────────────────────────────────────────────────────
const statusColorMap: Record<RedisTestStatus, string> = {
  untested: 'default',
  success: 'blue',
  failed: 'red',
};

// ── component props ───────────────────────────────────────────────────────────
interface RedisToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const RedisToolEditor = forwardRef<RedisToolEditorHandle, RedisToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { testRedisConnection } = useSkillApi();
  const [instances, setInstances] = useState<RedisInstanceFormValue[]>(() => parseRedisToolConfig(initialKwargs));
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    const insts = parseRedisToolConfig(initialKwargs);
    return insts[0]?.id ?? null;
  });
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
      if (instances.length === 0) { message.error(t('tool.redis.noInstances')); return false; }
      if (trimmedNames.length !== instances.length) { message.error(t('tool.redis.instanceNameRequired')); return false; }
      if (new Set(trimmedNames).size !== trimmedNames.length) { message.error(t('tool.redis.duplicateInstanceName')); return false; }
      if (instances.some((inst) => !inst.url.trim())) { message.error(t('tool.redis.urlRequired')); return false; }
      const trimmed = instances.map((inst) => ({ ...inst, name: inst.name.trim(), url: inst.url.trim() }));
      onSave(serializeRedisToolConfig(trimmed));
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

  const handleChange = <K extends keyof RedisInstanceFormValue>(id: string, field: K, value: RedisInstanceFormValue[K]) => {
    setInstances((prev) => prev.map((inst) => (inst.id === id ? { ...inst, [field]: value, testStatus: 'untested' } : inst)));
  };

  const handleTest = async () => {
    if (!selectedInstance) return;
    setTesting(true);
    try {
      const payload = { ...selectedInstance } as Partial<RedisInstanceFormValue>;
      delete payload.testStatus;
      await testRedisConnection(payload as Omit<RedisInstanceFormValue, 'testStatus'>);
      message.success(t('tool.redis.status.success'));
      setInstances((prev) => prev.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst)));
    } catch {
      setInstances((prev) => prev.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst)));
    } finally {
      setTesting(false);
    }
  };

  const renderStatus = (status: RedisTestStatus) => (
    <Tag color={statusColorMap[status]}>{t(`tool.redis.status.${status}`)}</Tag>
  );

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.redis.instances')}</span>
          <Button type="primary" ghost size="small" onClick={handleAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.redis.noInstances')} />
          ) : (
            instances.map((instance) => {
              const isActive = instance.id === selectedId;
              return (
                <button
                  key={instance.id}
                  type="button"
                  className={`w-full rounded border p-3 text-left transition ${
                    isActive ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'
                  }`}
                  onClick={() => setSelectedId(instance.id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{instance.name || t('tool.redis.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.url || t('tool.redis.addressNotConfigured')}
                      </div>
                    </div>
                    <DeleteOutlined
                      className="mt-1 text-[var(--color-text-3)] hover:text-[var(--color-error)]"
                      onClick={(e) => { e.stopPropagation(); handleDelete(instance.id); }}
                    />
                  </div>
                </button>
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
                {t('tool.redis.configTitle').replace('{name}', selectedInstance.name || t('tool.redis.unnamedInstance'))}
              </div>
              {renderStatus(selectedInstance.testStatus)}
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)}
                placeholder={t('tool.redis.instanceNamePlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.url')}</div>
              <Input
                value={selectedInstance.url}
                onChange={(e) => handleChange(selectedInstance.id, 'url', e.target.value)}
                placeholder={t('tool.redis.urlPlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.username')}</div>
                <Input
                  value={selectedInstance.username}
                  onChange={(e) => handleChange(selectedInstance.id, 'username', e.target.value)}
                  placeholder={t('tool.redis.usernamePlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.password')}</div>
                <Input.Password
                  value={selectedInstance.password}
                  onChange={(e) => handleChange(selectedInstance.id, 'password', e.target.value)}
                  placeholder={t('tool.redis.passwordPlaceholder')}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-2">
                <Switch checked={selectedInstance.ssl} onChange={(checked) => handleChange(selectedInstance.id, 'ssl', checked)} />
                <span>{t('tool.redis.ssl')}</span>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={selectedInstance.cluster_mode} onChange={(checked) => handleChange(selectedInstance.id, 'cluster_mode', checked)} />
                <span>{t('tool.redis.clusterMode')}</span>
              </div>
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCaPath')}</div>
              <Input
                value={selectedInstance.ssl_ca_path}
                onChange={(e) => handleChange(selectedInstance.id, 'ssl_ca_path', e.target.value)}
                placeholder={t('tool.redis.sslCaPathPlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslKeyfile')}</div>
              <Input
                value={selectedInstance.ssl_keyfile}
                onChange={(e) => handleChange(selectedInstance.id, 'ssl_keyfile', e.target.value)}
                placeholder={t('tool.redis.sslKeyfilePlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCertfile')}</div>
              <Input
                value={selectedInstance.ssl_certfile}
                onChange={(e) => handleChange(selectedInstance.id, 'ssl_certfile', e.target.value)}
                placeholder={t('tool.redis.sslCertfilePlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCertReqs')}</div>
                <Input
                  value={selectedInstance.ssl_cert_reqs}
                  onChange={(e) => handleChange(selectedInstance.id, 'ssl_cert_reqs', e.target.value)}
                  placeholder={t('tool.redis.sslCertReqsPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCaCerts')}</div>
                <Input
                  value={selectedInstance.ssl_ca_certs}
                  onChange={(e) => handleChange(selectedInstance.id, 'ssl_ca_certs', e.target.value)}
                  placeholder={t('tool.redis.sslCaCertsPlaceholder')}
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button loading={testing} onClick={handleTest}>
                {t('tool.redis.testConnection')}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.redis.selectInstance')} />
          </div>
        )}
      </div>
    </div>
  );
});

RedisToolEditor.displayName = 'RedisToolEditor';

export default RedisToolEditor;
