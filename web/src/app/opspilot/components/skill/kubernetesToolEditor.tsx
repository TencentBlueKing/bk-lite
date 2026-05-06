'use client';

import React, { useRef, useEffect } from 'react';
import { Button, Empty, Input, Tag } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

export type KubernetesTestStatus = 'untested' | 'success' | 'failed';

export interface KubernetesInstanceFormValue {
  id: string;
  name: string;
  kubeconfig_data: string;
  testStatus: KubernetesTestStatus;
}

interface KubernetesToolEditorProps {
  instances: KubernetesInstanceFormValue[];
  selectedInstanceId: string | null;
  testing: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onChange: <K extends keyof KubernetesInstanceFormValue>(id: string, field: K, value: KubernetesInstanceFormValue[K]) => void;
  onTest: () => void;
}

const statusColorMap: Record<KubernetesTestStatus, string> = {
  untested: 'default',
  success: 'blue',
  failed: 'red',
};

const KubernetesToolEditor: React.FC<KubernetesToolEditorProps> = ({
  instances,
  selectedInstanceId,
  testing,
  onSelect,
  onAdd,
  onDelete,
  onChange,
  onTest,
}) => {
  const { t } = useTranslation();
  const selectedInstance = instances.find((instance) => instance.id === selectedInstanceId) || null;

  const listRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(instances.length);

  useEffect(() => {
    if (instances.length > prevLengthRef.current && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
    prevLengthRef.current = instances.length;
  }, [instances.length]);

  const renderStatus = (status: KubernetesTestStatus) => {
    return <Tag color={statusColorMap[status]}>{t(`tool.kubernetes.status.${status}`)}</Tag>;
  };

  const getKubeconfigPreview = (kubeconfigData: string) => {
    if (!kubeconfigData) {
      return t('tool.kubernetes.noKubeconfigData');
    }
    const firstLine = kubeconfigData.split('\n')[0].trim();
    return firstLine || t('tool.kubernetes.noKubeconfigData');
  };

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.kubernetes.instances')}</span>
          <Button type="primary" ghost size="small" onClick={onAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.kubernetes.noInstances')} />
          ) : (
            instances.map((instance) => {
              const isActive = instance.id === selectedInstanceId;
              return (
                <button
                  key={instance.id}
                  type="button"
                  className={`w-full rounded border p-3 text-left transition ${
                    isActive ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-bg-1)]'
                  }`}
                  onClick={() => onSelect(instance.id)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{instance.name || t('tool.kubernetes.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {getKubeconfigPreview(instance.kubeconfig_data)}
                      </div>
                    </div>
                    <DeleteOutlined
                      className="mt-1 text-[var(--color-text-3)] hover:text-[var(--color-error)]"
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(instance.id);
                      }}
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
                {t('tool.kubernetes.configTitle').replace('{name}', selectedInstance.name || t('tool.kubernetes.unnamedInstance'))}
              </div>
              {renderStatus(selectedInstance.testStatus)}
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.kubernetes.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(event) => onChange(selectedInstance.id, 'name', event.target.value)}
                placeholder={t('tool.kubernetes.instanceNamePlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.kubernetes.kubeconfigData')}</div>
              <Input.TextArea
                value={selectedInstance.kubeconfig_data}
                onChange={(event) => onChange(selectedInstance.id, 'kubeconfig_data', event.target.value)}
                placeholder={t('tool.kubernetes.kubeconfigDataPlaceholder')}
                rows={12}
                style={{ fontFamily: 'monospace', fontSize: '12px' }}
              />
            </div>

            <div className="flex justify-end">
              <Button loading={testing} onClick={onTest}>
                {t('tool.kubernetes.testConnection')}
              </Button>
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
};

export default KubernetesToolEditor;
