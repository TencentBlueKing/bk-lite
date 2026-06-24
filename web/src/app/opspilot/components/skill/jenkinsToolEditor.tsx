'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Button, Empty, Input, Tag, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ToolVariable } from '@/app/opspilot/types/tool';
import { useSkillApi } from '@/app/opspilot/api/skill';

export type JenkinsTestStatus = 'untested' | 'success' | 'failed';

export interface JenkinsInstanceFormValue {
  id: string;
  name: string;
  jenkins_url: string;
  jenkins_username: string;
  jenkins_password: string;
  testStatus: JenkinsTestStatus;
}

const INSTANCES_KEY = 'jenkins_instances';
const DEFAULT_INSTANCE_ID_KEY = 'jenkins_default_instance_id';
const AUTO_NAME_PREFIX = 'Jenkins - ';

const createId = () => `jenkins-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const getDefaultInstance = (name: string): JenkinsInstanceFormValue => ({
  id: createId(), name, jenkins_url: '', jenkins_username: '', jenkins_password: '', testStatus: 'untested',
});
const getNextName = (instances: JenkinsInstanceFormValue[]) => {
  const max = instances.reduce((m, inst) => { const match = inst.name.match(/^Jenkins - (\d+)$/); return match ? Math.max(m, Number(match[1])) : m; }, 0);
  return `${AUTO_NAME_PREFIX}${max + 1}`;
};
const parseInstancesValue = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) return value as Record<string, unknown>[];
  if (typeof value === 'string' && value.trim()) { try { const p = JSON.parse(value); return Array.isArray(p) ? p : []; } catch { return []; } }
  return [];
};

export const parseJenkinsToolConfig = (kwargs: ToolVariable[] = []): JenkinsInstanceFormValue[] => {
  const map = new Map(kwargs.filter((k) => k.key).map((k) => [k.key, k.value]));
  const parsed = parseInstancesValue(map.get(INSTANCES_KEY));
  if (parsed.length > 0) {
    return parsed.map((item, i) => ({
      id: String(item.id || `jenkins-${i + 1}`), name: String(item.name || `${AUTO_NAME_PREFIX}${i + 1}`),
      jenkins_url: String(item.jenkins_url || ''), jenkins_username: String(item.jenkins_username || ''),
      jenkins_password: String(item.jenkins_password || ''), testStatus: 'untested',
    }));
  }
  const hasLegacy = ['jenkins_url', 'jenkins_username', 'jenkins_password'].some((k) => map.has(k));
  if (hasLegacy) {
    return [{ id: 'jenkins-1', name: 'Jenkins - 1', jenkins_url: String(map.get('jenkins_url') || ''),
      jenkins_username: String(map.get('jenkins_username') || ''), jenkins_password: String(map.get('jenkins_password') || ''), testStatus: 'untested' }];
  }
  return [getDefaultInstance('Jenkins - 1')];
};

const serializeJenkinsToolConfig = (instances: JenkinsInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((inst) => { const c = { ...inst } as Partial<JenkinsInstanceFormValue>; delete c.testStatus; return c; });
  return [{ key: INSTANCES_KEY, value: JSON.stringify(normalized) }, { key: DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' }];
};

export interface JenkinsToolEditorHandle { save: () => boolean; }
const statusColorMap: Record<JenkinsTestStatus, string> = { untested: 'default', success: 'blue', failed: 'red' };

interface JenkinsToolEditorProps {
  initialKwargs: ToolVariable[];
  onSave: (kwargs: ToolVariable[]) => void;
}

const JenkinsToolEditor = forwardRef<JenkinsToolEditorHandle, JenkinsToolEditorProps>(({ initialKwargs, onSave }, ref) => {
  const { t } = useTranslation();
  const { testJenkinsConnection } = useSkillApi();
  const [instances, setInstances] = useState<JenkinsInstanceFormValue[]>(() => parseJenkinsToolConfig(initialKwargs));
  const [selectedId, setSelectedId] = useState<string | null>(() => parseJenkinsToolConfig(initialKwargs)[0]?.id ?? null);
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
      if (instances.length === 0) { message.error(t('tool.jenkins.noInstances')); return false; }
      if (trimmedNames.length !== instances.length) { message.error(t('tool.jenkins.instanceNameRequired')); return false; }
      if (new Set(trimmedNames).size !== trimmedNames.length) { message.error(t('tool.jenkins.duplicateInstanceName')); return false; }
      if (instances.some((inst) => !inst.jenkins_url.trim())) { message.error(t('tool.jenkins.urlRequired')); return false; }
      const trimmed = instances.map((inst) => ({ ...inst, name: inst.name.trim(), jenkins_url: inst.jenkins_url.trim() }));
      onSave(serializeJenkinsToolConfig(trimmed));
      return true;
    },
  }));

  const handleAdd = () => { const next = getDefaultInstance(getNextName(instances)); setInstances((p) => [...p, next]); setSelectedId(next.id); };
  const handleDelete = (id: string) => {
    setInstances((p) => { const n = p.filter((inst) => inst.id !== id); if (selectedId === id) setSelectedId(n[0]?.id ?? null); return n; });
  };
  const handleChange = <K extends keyof JenkinsInstanceFormValue>(id: string, field: K, value: JenkinsInstanceFormValue[K]) => {
    setInstances((p) => p.map((inst) => (inst.id === id ? { ...inst, [field]: value, testStatus: 'untested' } : inst)));
  };
  const handleTest = async () => {
    if (!selectedInstance) return;
    setTesting(true);
    try {
      const payload = { ...selectedInstance } as Partial<JenkinsInstanceFormValue>; delete payload.testStatus;
      await testJenkinsConnection(payload as Omit<JenkinsInstanceFormValue, 'testStatus'>);
      message.success(t('tool.jenkins.status.success'));
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'success' } : inst)));
    } catch {
      setInstances((p) => p.map((inst) => (inst.id === selectedInstance.id ? { ...inst, testStatus: 'failed' } : inst)));
    } finally { setTesting(false); }
  };

  const renderStatus = (status: JenkinsTestStatus) => <Tag color={statusColorMap[status]}>{t(`tool.jenkins.status.${status}`)}</Tag>;

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.jenkins.instances')}</span>
          <Button type="primary" ghost size="small" onClick={handleAdd}>+ {t('common.add')}</Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.jenkins.noInstances')} />
          ) : instances.map((instance) => {
            const isActive = instance.id === selectedId;
            return (
              <button key={instance.id} type="button"
                className={`w-full rounded border p-3 text-left transition ${isActive ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'}`}
                onClick={() => setSelectedId(instance.id)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{instance.name || t('tool.jenkins.unnamedInstance')}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                      {instance.jenkins_url || t('tool.jenkins.addressNotConfigured')}
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
              <div className="text-lg font-medium">{t('tool.jenkins.configTitle').replace('{name}', selectedInstance.name || t('tool.jenkins.unnamedInstance'))}</div>
              {renderStatus(selectedInstance.testStatus)}
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.instanceName')}</div>
              <Input value={selectedInstance.name} onChange={(e) => handleChange(selectedInstance.id, 'name', e.target.value)} placeholder={t('tool.jenkins.instanceNamePlaceholder')} />
            </div>
            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.jenkinsUrl')}</div>
              <Input value={selectedInstance.jenkins_url} onChange={(e) => handleChange(selectedInstance.id, 'jenkins_url', e.target.value)} placeholder="http://jenkins:8080" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.jenkinsUsername')}</div>
                <Input value={selectedInstance.jenkins_username} onChange={(e) => handleChange(selectedInstance.id, 'jenkins_username', e.target.value)} placeholder={t('tool.jenkins.jenkinsUsernamePlaceholder')} />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.jenkinsPassword')}</div>
                <Input.Password value={selectedInstance.jenkins_password} onChange={(e) => handleChange(selectedInstance.id, 'jenkins_password', e.target.value)} placeholder={t('tool.jenkins.jenkinsPasswordPlaceholder')} />
              </div>
            </div>
            <div className="flex justify-end">
              <Button loading={testing} onClick={handleTest}>{t('tool.jenkins.testConnection')}</Button>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.jenkins.selectInstance')} />
          </div>
        )}
      </div>
    </div>
  );
});

JenkinsToolEditor.displayName = 'JenkinsToolEditor';
export default JenkinsToolEditor;
