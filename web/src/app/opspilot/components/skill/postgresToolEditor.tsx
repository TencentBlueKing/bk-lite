'use client';

import React, { useRef, useEffect } from 'react';
import { Button, Empty, Input, InputNumber, Tag } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

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

interface PostgresToolEditorProps {
  instances: PostgresInstanceFormValue[];
  selectedInstanceId: string | null;
  testing: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onChange: <K extends keyof PostgresInstanceFormValue>(id: string, field: K, value: PostgresInstanceFormValue[K]) => void;
  onTest: () => void;
}

const statusColorMap: Record<PostgresTestStatus, string> = {
  untested: 'default',
  success: 'blue',
  failed: 'red',
};

const PostgresToolEditor: React.FC<PostgresToolEditorProps> = ({
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

  const renderStatus = (status: PostgresTestStatus) => {
    return <Tag color={statusColorMap[status]}>{t(`tool.postgres.status.${status}`)}</Tag>;
  };

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.postgres.instances')}</span>
          <Button type="primary" ghost size="small" onClick={onAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.postgres.noInstances')} />
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
                      <div className="truncate font-medium">{instance.name || t('tool.postgres.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.host ? `${instance.host}:${instance.port}` : t('tool.postgres.addressNotConfigured')}
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
                {t('tool.postgres.configTitle').replace('{name}', selectedInstance.name || t('tool.postgres.unnamedInstance'))}
              </div>
              {renderStatus(selectedInstance.testStatus)}
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(event) => onChange(selectedInstance.id, 'name', event.target.value)}
                placeholder={t('tool.postgres.instanceNamePlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.host')}</div>
                <Input
                  value={selectedInstance.host}
                  onChange={(event) => onChange(selectedInstance.id, 'host', event.target.value)}
                  placeholder={t('tool.postgres.hostPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.port')}</div>
                <InputNumber
                  style={{ width: '100%' }}
                  value={selectedInstance.port}
                  min={1}
                  max={65535}
                  onChange={(value) => onChange(selectedInstance.id, 'port', value ?? 5432)}
                  placeholder="5432"
                />
              </div>
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.database')}</div>
              <Input
                value={selectedInstance.database}
                onChange={(event) => onChange(selectedInstance.id, 'database', event.target.value)}
                placeholder="postgres"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.user')}</div>
                <Input
                  value={selectedInstance.user}
                  onChange={(event) => onChange(selectedInstance.id, 'user', event.target.value)}
                  placeholder={t('tool.postgres.userPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.postgres.password')}</div>
                <Input.Password
                  value={selectedInstance.password}
                  onChange={(event) => onChange(selectedInstance.id, 'password', event.target.value)}
                  placeholder={t('tool.postgres.passwordPlaceholder')}
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button loading={testing} onClick={onTest}>
                {t('tool.postgres.testConnection')}
              </Button>
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
};

export default PostgresToolEditor;
