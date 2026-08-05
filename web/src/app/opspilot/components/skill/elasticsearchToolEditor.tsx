'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Empty, Input, Switch, Tag, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type ElasticsearchTestStatus = 'untested' | 'success' | 'failed';

export interface ElasticsearchInstanceFormValue {
  id: string;
  name: string;
  url: string;
  username: string;
  password: string;
  api_key: string;
  verify_certs: boolean;
  testStatus: ElasticsearchTestStatus;
}

const INSTANCES_KEY = 'es_instances';
const DEFAULT_INSTANCE_ID_KEY = 'es_default_instance_id';
const AUTO_NAME_PREFIX = 'Elasticsearch - ';

const createId = () => `es-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const getDefaultInstance = (name: string): ElasticsearchInstanceFormValue => ({
  id: createId(), name, url: '', username: '', password: '', api_key: '', verify_certs: true, testStatus: 'untested',
});
const getNextName = (instances: ElasticsearchInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => { const match = inst.name.match(/^Elasticsearch - (\d+)$/); return match ? Math.max(m, Number(match[1])) : m; }, 0);
  return `${AUTO_NAME_PREFIX}${max + 1}`;
};
const parseBoolean = (value: unknown, defaultValue = true) => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return !['false', '0', 'no', 'off'].includes(value.toLowerCase());
  return defaultValue;
};
const parseInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) { try { const p = JSON.parse(value); return Array.isArray(p) ? p : []; } catch { return []; } }
  return [];
};

export const parseEsToolConfig = (kwargs: ToolVariable[] = []): ElasticsearchInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => ({
      id: String(item.id || `es-${i + 1}`), name: String(item.name || `${AUTO_NAME_PREFIX}${i + 1}`),
      url: String(item.url || ''), username: String(item.username || ''), password: String(item.password || ''),
      api_key: String(item.api_key || ''), verify_certs: parseBoolean(item.verify_certs), testStatus: 'untested',
    }));
  }
  const hasLegacy = ['url', 'username', 'password', 'api_key'].some((k) => map.has(k));
  if (hasLegacy) {
    return [{ id: 'es-1', name: 'Elasticsearch - 1', url: String(map.get('url') || ''), username: String(map.get('username') || ''),
      password: String(map.get('password') || ''), api_key: String(map.get('api_key') || ''),
      verify_certs: parseBoolean(map.get('verify_certs')), testStatus: 'untested' }];
  }
  return [getDefaultInstance('Elasticsearch - 1')];
};

const serializeEsToolConfig = (instances: ElasticsearchInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => { const c = { ...inst } as Partial<ElasticsearchInstanceFormValue>; delete c.testStatus; return c; });
  return [{ key: INSTANCES_KEY, value: JSON.stringify(normalized) }, { key: DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' }];
};

export interface ElasticsearchToolEditorHandle { save: () => boolean; }
const statusColorMap: Record<ElasticsearchTestStatus, string> = { untested: 'default', success: 'blue', failed: 'red' };

interface ElasticsearchToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const ElasticsearchToolEditor = forwardRef<ElasticsearchToolEditorHandle, ElasticsearchToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { testEsConnection } = useSkillApi();
  const [instances, setInstances] = useState<ElasticsearchInstanceFormValue[]>(() => parseEsToolConfig(initialKwargs));
  const [selectedId, setSelectedId] = useState<string | null>(() => parseEsToolConfig(initialKwargs)[0]?.id ?? null);
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
      if (instances.length === 0) { message.error(t('tool.elasticsearch.noInstances')); return false; }
      if (trimmedNames.length !== instances.length) { message.error(t('tool.elasticsearch.instanceNameRequired')); return false; }
      if (new Set(trimmedNames).size !== trimmedNames.length) { message.error(t('tool.elasticsearch.duplicateInstanceName')); return false; }
      if (instances.some((inst) => !inst.url.trim())) { message.error(t('tool.elasticsearch.urlRequired')); return false; }
      const trimmed = instances.map((inst) => ({ ...inst, name: inst.name.trim(), url: inst.url.trim() }));
      onSave(serializeEsToolConfig(trimmed));
      return true;
    },
  }));

  const handleAdd = () => { const next = getDefaultInstance(getNextName(instances)); setInstances((p) => [...p, next]); setSelectedId(next.id); };
  const handleDelete = (id: string) => {
    setInstances((p) => { const n = p.filter((inst) => inst.id !== id); if (selectedId === id) setSelectedId(n[0]?.id ?? null); return n; });
  };
  const handleChange = <K extends keyof ElasticsearchInstanceFormValue>(id: string, field: K, value: ElasticsearchInstanceFormValue[K]) => {
    setInstances((p) => p.map((inst) => (inst.id === id ? { ...inst, [field]: value, testStatus: 'untested' } : inst)));
  };
  const handleTest = async () => {
    if (!selectedInstance) return;
    setTesting(true);
    try {
      const payload = { ...selectedInstance } as Partial<ElasticsearchInstanceFormValue>; delete payload.testStatus;
      await testEsConnection(payload as Omit<ElasticsearchInstanceFormValue, 'testStatus'>);
      message.success(t('tool.elasticsearch.status.success'));
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst)));
    } catch {
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst)));
    } finally { setTesting(false); }
  };

  const renderStatus = (status: ElasticsearchTestStatus) => <Tag color={statusColorMap[status]}>{t(`tool.elasticsearch.status.${status}`)}</Tag>;

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.elasticsearch.instances')}</span>
          <Button type="primary" ghost size="small" onClick={handleAdd}>+ {t('common.add')}</Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.elasticsearch.noInstances')} />
          ) : instances.map((instance) => {
            const isActive = instance.id === selectedId;
            return (
              <button key={instance.id} type="button"
                className={`w-full rounded border p-3 text-left transition ${isActive ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'}`}
                onClick={() => setSelectedId(instance.id)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{instance.name || t('tool.elasticsearch.unnamedInstance')}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                      {instance.url || t('tool.elasticsearch.addressNotConfigured')}
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
              <div className="text-lg font-medium">{t('tool.elasticsearch.configTitle').replace('{name}', selectedInstance.name || t('tool.elasticsearch.unnamedInstance'))}</div>
              {renderStatus(selectedInstance.testStatus)}
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.instanceName')}</div>
              <Input value={selectedInstance.name} onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)} placeholder={t('tool.elasticsearch.instanceNamePlaceholder')} />
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.url')}</div>
              <Input value={selectedInstance.url} onChange={(e) => handleChange(selectedInstance.id, 'url', e.target.value)} placeholder="http://127.0.0.1:9200" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.username')}</div>
                <Input value={selectedInstance.username} onChange={(e) => handleChange(selectedInstance.id, 'username', e.target.value)} placeholder={t('tool.elasticsearch.usernamePlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.password')}</div>
                <Input.Password value={selectedInstance.password} onChange={(e) => handleChange(selectedInstance.id, 'password', e.target.value)} placeholder={t('tool.elasticsearch.passwordPlaceholder')} />
              </div>
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.apiKey')}</div>
              <Input.Password value={selectedInstance.api_key} onChange={(e) => handleChange(selectedInstance.id, 'api_key', e.target.value)} placeholder={t('tool.elasticsearch.apiKeyPlaceholder')} />
            </div>
            <div className="flex items-center gap-3">
              <div className="text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.verifyCerts')}</div>
              <Switch checked={selectedInstance.verify_certs} onChange={(v) => handleChange(selectedInstance.id, 'verify_certs', v)} />
            </div>
            <div className="flex justify-end">
              <Button loading={testing} onClick={handleTest}>{t('tool.elasticsearch.testConnection')}</Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.elasticsearch.selectInstance')} />
          </div>
        )}
      </div>
    </div>
  );
});

ElasticsearchToolEditor.displayName = 'ElasticsearchToolEditor';
export default ElasticsearchToolEditor;
