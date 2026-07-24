'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Empty, Input, Tag, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type KubernetesTestStatus = 'untested' | 'success' | 'failed';

export interface KubernetesInstanceFormValue {
  id: string;
  name: string;
  kubeconfig_data: string;
  testStatus: KubernetesTestStatus;
}

const INSTANCES_KEY = 'kubernetes_instances';
const AUTO_NAME_PREFIX = 'Kubernetes - ';

const createId = () => `kubernetes-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const getDefaultInstance = (name: string): KubernetesInstanceFormValue => ({
  id: createId(), name, kubeconfig_data: '', testStatus: 'untested',
});
const getNextName = (instances: KubernetesInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => { const match = inst.name.match(/^Kubernetes - (\d+)$/); return match ? Math.max(m, Number(match[1])) : m; }, 0);
  return `${AUTO_NAME_PREFIX}${max + 1}`;
};
const parseInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) { try { const p = JSON.parse(value); return Array.isArray(p) ? p : []; } catch { return []; } }
  return [];
};

export const parseKubernetesToolConfig = (kwargs: ToolVariable[] = []): KubernetesInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => ({
      id: String(item.id || `kubernetes-${i + 1}`), name: String(item.name || `${AUTO_NAME_PREFIX}${i + 1}`),
      kubeconfig_data: String(item.kubeconfig_data || ''), testStatus: 'untested',
    }));
  }
  const hasLegacy = ['kubeconfig_data'].some((k) => map.has(k));
  if (hasLegacy) {
    return [{ id: 'kubernetes-1', name: 'Kubernetes - 1', kubeconfig_data: String(map.get('kubeconfig_data') || ''), testStatus: 'untested' }];
  }
  return [getDefaultInstance('Kubernetes - 1')];
};

const serializeKubernetesToolConfig = (instances: KubernetesInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => { const c = { ...inst } as Partial<KubernetesInstanceFormValue>; delete c.testStatus; return c; });
  return [{ key: INSTANCES_KEY, value: JSON.stringify(normalized) }];
};

export interface KubernetesToolEditorHandle { save: () => boolean; }
const statusColorMap: Record<KubernetesTestStatus, string> = { untested: 'default', success: 'blue', failed: 'red' };

interface KubernetesToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const KubernetesToolEditor = forwardRef<KubernetesToolEditorHandle, KubernetesToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { testKubernetesConnection } = useSkillApi();
  const [instances, setInstances] = useState<KubernetesInstanceFormValue[]>(() => parseKubernetesToolConfig(initialKwargs));
  const [selectedId, setSelectedId] = useState<string | null>(() => parseKubernetesToolConfig(initialKwargs)[0]?.id ?? null);
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
      if (instances.length === 0) { message.error(t('tool.kubernetes.noInstances')); return false; }
      if (trimmedNames.length !== instances.length) { message.error(t('tool.kubernetes.instanceNameRequired')); return false; }
      if (new Set(trimmedNames).size !== trimmedNames.length) { message.error(t('tool.kubernetes.duplicateInstanceName')); return false; }
      if (instances.some((inst) => !inst.kubeconfig_data.trim())) { message.error(t('tool.kubernetes.kubeconfigDataRequired')); return false; }
      const trimmed = instances.map((inst) => ({ ...inst, name: inst.name.trim(), kubeconfig_data: inst.kubeconfig_data.trim() }));
      onSave(serializeKubernetesToolConfig(trimmed));
      return true;
    },
  }));

  const handleAdd = () => { const next = getDefaultInstance(getNextName(instances)); setInstances((p) => [...p, next]); setSelectedId(next.id); };
  const handleDelete = (id: string) => {
    setInstances((p) => { const n = p.filter((inst) => inst.id !== id); if (selectedId === id) setSelectedId(n[0]?.id ?? null); return n; });
  };
  const handleChange = <K extends keyof KubernetesInstanceFormValue>(id: string, field: K, value: KubernetesInstanceFormValue[K]) => {
    setInstances((p) => p.map((inst) => (inst.id === id ? { ...inst, [field]: value, testStatus: 'untested' } : inst)));
  };
  const handleTest = async () => {
    if (!selectedInstance) return;
    setTesting(true);
    try {
      const payload = { ...selectedInstance } as Partial<KubernetesInstanceFormValue>; delete payload.testStatus;
      await testKubernetesConnection(payload as Omit<KubernetesInstanceFormValue, 'testStatus'>);
      message.success(t('tool.kubernetes.status.success'));
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst)));
    } catch {
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst)));
    } finally { setTesting(false); }
  };

  const getKubeconfigPreview = (data: string) => {
    if (!data) return t('tool.kubernetes.noKubeconfigData');
    const firstLine = data.split('\n')[0].trim();
    return firstLine || t('tool.kubernetes.noKubeconfigData');
  };

  const renderStatus = (status: KubernetesTestStatus) => <Tag color={statusColorMap[status]}>{t(`tool.kubernetes.status.${status}`)}</Tag>;

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.kubernetes.instances')}</span>
          <Button type="primary" ghost size="small" onClick={handleAdd}>+ {t('common.add')}</Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.kubernetes.noInstances')} />
          ) : instances.map((instance) => {
            const isActive = instance.id === selectedId;
            return (
              <button key={instance.id} type="button"
                className={`w-full rounded p-3 text-left transition ${isActive ? 'border-2 border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border border-[var(--color-border)] bg-[var(--color-bg-1)]'}`}
                onClick={() => setSelectedId(instance.id)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{instance.name || t('tool.kubernetes.unnamedInstance')}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                      {getKubeconfigPreview(instance.kubeconfig_data)}
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
              <div className="text-lg font-medium">{t('tool.kubernetes.configTitle').replace('{name}', selectedInstance.name || t('tool.kubernetes.unnamedInstance'))}</div>
              {renderStatus(selectedInstance.testStatus)}
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.kubernetes.instanceName')}</div>
              <Input value={selectedInstance.name} onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)} placeholder={t('tool.kubernetes.instanceNamePlaceholder')} />
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.kubernetes.kubeconfigData')}</div>
              <Input.TextArea value={selectedInstance.kubeconfig_data} onChange={(e) => handleChange(selectedInstance.id, 'kubeconfig_data', e.target.value)}
                placeholder={t('tool.kubernetes.kubeconfigDataPlaceholder')} rows={12} style={{ fontFamily: 'monospace', fontSize: '12px' }} />
            </div>
            <div className="flex justify-end">
              <Button loading={testing} onClick={handleTest}>{t('tool.kubernetes.testConnection')}</Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.kubernetes.selectInstance')} />
          </div>
        )}
      </div>
    </div>
  );
});

KubernetesToolEditor.displayName = 'KubernetesToolEditor';
export default KubernetesToolEditor;
