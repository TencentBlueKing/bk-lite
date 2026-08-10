'use client';

import React, { useRef, useEffect } from 'react';
import { Button, Empty, Input, InputNumber, Switch } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import ToolConnectionStatusTag from '@/app/opspilot/components/opspilot-tool-editor/tool-connection-status-tag';

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

interface MysqlToolEditorProps {
  instances: MysqlInstanceFormValue[];
  selectedInstanceId: string | null;
  testing: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onChange: <K extends keyof MysqlInstanceFormValue>(id: string, field: K, value: MysqlInstanceFormValue[K]) => void;
  onTest: () => void;
}


const MysqlToolEditor: React.FC<MysqlToolEditorProps> = ({
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
          <span className="font-medium">{t('tool.mysql.instances')}</span>
          <Button type="primary" ghost size="small" onClick={onAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.mysql.noInstances')} />
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
                      <div className="truncate font-medium">{instance.name || t('tool.mysql.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.host ? `${instance.host}:${instance.port}` : t('tool.mysql.addressNotConfigured')}
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
                {t('tool.mysql.configTitle').replace('{name}', selectedInstance.name || t('tool.mysql.unnamedInstance'))}
              </div>
              <ToolConnectionStatusTag scope="tool.mysql" status={selectedInstance.testStatus} />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(event) => onChange(selectedInstance.id, 'name', event.target.value)}
                placeholder={t('tool.mysql.instanceNamePlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.host')}</div>
                <Input
                  value={selectedInstance.host}
                  onChange={(event) => onChange(selectedInstance.id, 'host', event.target.value)}
                  placeholder={t('tool.mysql.hostPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.port')}</div>
                <InputNumber
                  style={{ width: '100%' }}
                  value={selectedInstance.port}
                  min={1}
                  max={65535}
                  onChange={(value) => onChange(selectedInstance.id, 'port', value ?? 3306)}
                  placeholder="3306"
                />
              </div>
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.database')}</div>
              <Input
                value={selectedInstance.database}
                onChange={(event) => onChange(selectedInstance.id, 'database', event.target.value)}
                placeholder={t('tool.mysql.databasePlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.user')}</div>
                <Input
                  value={selectedInstance.user}
                  onChange={(event) => onChange(selectedInstance.id, 'user', event.target.value)}
                  placeholder={t('tool.mysql.userPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.password')}</div>
                <Input.Password
                  value={selectedInstance.password}
                  onChange={(event) => onChange(selectedInstance.id, 'password', event.target.value)}
                  placeholder={t('tool.mysql.passwordPlaceholder')}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.charset')}</div>
                <Input
                  value={selectedInstance.charset}
                  onChange={(event) => onChange(selectedInstance.id, 'charset', event.target.value)}
                  placeholder="utf8mb4"
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.collation')}</div>
                <Input
                  value={selectedInstance.collation}
                  onChange={(event) => onChange(selectedInstance.id, 'collation', event.target.value)}
                  placeholder="utf8mb4_unicode_ci"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Switch checked={selectedInstance.ssl} onChange={(checked) => onChange(selectedInstance.id, 'ssl', checked)} />
              <span>{t('tool.mysql.ssl')}</span>
            </div>

            {selectedInstance.ssl && (
              <>
                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.sslCa')}</div>
                  <Input
                    value={selectedInstance.ssl_ca}
                    onChange={(event) => onChange(selectedInstance.id, 'ssl_ca', event.target.value)}
                    placeholder={t('tool.mysql.sslCaPlaceholder')}
                  />
                </div>

                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.sslCert')}</div>
                  <Input
                    value={selectedInstance.ssl_cert}
                    onChange={(event) => onChange(selectedInstance.id, 'ssl_cert', event.target.value)}
                    placeholder={t('tool.mysql.sslCertPlaceholder')}
                  />
                </div>

                <div>
                  <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.mysql.sslKey')}</div>
                  <Input
                    value={selectedInstance.ssl_key}
                    onChange={(event) => onChange(selectedInstance.id, 'ssl_key', event.target.value)}
                    placeholder={t('tool.mysql.sslKeyPlaceholder')}
                  />
                </div>
              </>
            )}

            <div className="flex justify-end">
              <Button loading={testing} onClick={onTest}>
                {t('tool.mysql.testConnection')}
              </Button>
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
};

export default MysqlToolEditor;
