'use client';

import React, { useRef, useEffect } from 'react';
import { Button, Empty, Input, Switch, Tag } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

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

interface ElasticsearchToolEditorProps {
  instances: ElasticsearchInstanceFormValue[];
  selectedInstanceId: string | null;
  testing: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onChange: <K extends keyof ElasticsearchInstanceFormValue>(id: string, field: K, value: ElasticsearchInstanceFormValue[K]) => void;
  onTest: () => void;
}

const statusColorMap: Record<ElasticsearchTestStatus, string> = {
  untested: 'default',
  success: 'blue',
  failed: 'red',
};

const ElasticsearchToolEditor: React.FC<ElasticsearchToolEditorProps> = ({
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

  const renderStatus = (status: ElasticsearchTestStatus) => {
    return <Tag color={statusColorMap[status]}>{t(`tool.elasticsearch.status.${status}`)}</Tag>;
  };

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.elasticsearch.instances')}</span>
          <Button type="primary" ghost size="small" onClick={onAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.elasticsearch.noInstances')} />
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
                      <div className="truncate font-medium">{instance.name || t('tool.elasticsearch.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.url || t('tool.elasticsearch.addressNotConfigured')}
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
                {t('tool.elasticsearch.configTitle').replace('{name}', selectedInstance.name || t('tool.elasticsearch.unnamedInstance'))}
              </div>
              {renderStatus(selectedInstance.testStatus)}
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(event) => onChange(selectedInstance.id, 'name', event.target.value)}
                placeholder={t('tool.elasticsearch.instanceNamePlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.url')}</div>
              <Input
                value={selectedInstance.url}
                onChange={(event) => onChange(selectedInstance.id, 'url', event.target.value)}
                placeholder="http://127.0.0.1:9200"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.username')}</div>
                <Input
                  value={selectedInstance.username}
                  onChange={(event) => onChange(selectedInstance.id, 'username', event.target.value)}
                  placeholder={t('tool.elasticsearch.usernamePlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.password')}</div>
                <Input.Password
                  value={selectedInstance.password}
                  onChange={(event) => onChange(selectedInstance.id, 'password', event.target.value)}
                  placeholder={t('tool.elasticsearch.passwordPlaceholder')}
                />
              </div>
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.apiKey')}</div>
              <Input.Password
                value={selectedInstance.api_key}
                onChange={(event) => onChange(selectedInstance.id, 'api_key', event.target.value)}
                placeholder={t('tool.elasticsearch.apiKeyPlaceholder')}
              />
            </div>

            <div className="flex items-center gap-3">
              <div className="text-sm text-[var(--color-text-2)]">{t('tool.elasticsearch.verifyCerts')}</div>
              <Switch
                checked={selectedInstance.verify_certs}
                onChange={(value) => onChange(selectedInstance.id, 'verify_certs', value)}
              />
            </div>

            <div className="flex justify-end">
              <Button loading={testing} onClick={onTest}>
                {t('tool.elasticsearch.testConnection')}
              </Button>
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
};

export default ElasticsearchToolEditor;
