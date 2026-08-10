'use client';

import React, { useRef, useEffect } from 'react';
import { Button, Empty, Input, InputNumber } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import ToolConnectionStatusTag from '@/app/opspilot/components/opspilot-tool-editor/tool-connection-status-tag';

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

interface MssqlToolEditorProps {
  instances: MssqlInstanceFormValue[];
  selectedInstanceId: string | null;
  testing: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onChange: <K extends keyof MssqlInstanceFormValue>(id: string, field: K, value: MssqlInstanceFormValue[K]) => void;
  onTest: () => void;
}


const MssqlToolEditor: React.FC<MssqlToolEditorProps> = ({
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


  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.mssql.instances')}</span>
          <Button type="primary" ghost size="small" onClick={onAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.mssql.noInstances')} />
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
                      <div className="truncate font-medium">{instance.name || t('tool.mssql.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.host ? `${instance.host}:${instance.port}` : t('tool.mssql.addressNotConfigured')}
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
                {t('tool.mssql.configTitle').replace('{name}', selectedInstance.name || t('tool.mssql.unnamedInstance'))}
              </div>
              <ToolConnectionStatusTag scope="tool.mssql" status={selectedInstance.testStatus} />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(event) => onChange(selectedInstance.id, 'name', event.target.value)}
                placeholder={t('tool.mssql.instanceNamePlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.host')}</div>
                <Input
                  value={selectedInstance.host}
                  onChange={(event) => onChange(selectedInstance.id, 'host', event.target.value)}
                  placeholder={t('tool.mssql.hostPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.port')}</div>
                <InputNumber
                  style={{ width: '100%' }}
                  value={selectedInstance.port}
                  min={1}
                  max={65535}
                  onChange={(value) => onChange(selectedInstance.id, 'port', value ?? 1433)}
                  placeholder="1433"
                />
              </div>
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.database')}</div>
              <Input
                value={selectedInstance.database}
                onChange={(event) => onChange(selectedInstance.id, 'database', event.target.value)}
                placeholder="master"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.user')}</div>
                <Input
                  value={selectedInstance.user}
                  onChange={(event) => onChange(selectedInstance.id, 'user', event.target.value)}
                  placeholder={t('tool.mssql.userPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mssql.password')}</div>
                <Input.Password
                  value={selectedInstance.password}
                  onChange={(event) => onChange(selectedInstance.id, 'password', event.target.value)}
                  placeholder={t('tool.mssql.passwordPlaceholder')}
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button loading={testing} onClick={onTest}>
                {t('tool.mssql.testConnection')}
              </Button>
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
};

export default MssqlToolEditor;
