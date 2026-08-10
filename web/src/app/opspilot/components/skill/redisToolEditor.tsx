'use client';

import React, { useRef, useEffect } from 'react';
import { Button, Empty, Input, Switch } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import ToolConnectionStatusTag from '@/app/opspilot/components/opspilot-tool-editor/tool-connection-status-tag';

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

interface RedisToolEditorProps {
  instances: RedisInstanceFormValue[];
  selectedInstanceId: string | null;
  testing: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onChange: <K extends keyof RedisInstanceFormValue>(id: string, field: K, value: RedisInstanceFormValue[K]) => void;
  onTest: () => void;
}


const RedisToolEditor: React.FC<RedisToolEditorProps> = ({
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
          <span className="font-medium">{t('tool.redis.instances')}</span>
          <Button type="primary" ghost size="small" onClick={onAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.redis.noInstances')} />
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
                      <div className="truncate font-medium">{instance.name || t('tool.redis.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.url || t('tool.redis.addressNotConfigured')}
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
                {t('tool.redis.configTitle').replace('{name}', selectedInstance.name || t('tool.redis.unnamedInstance'))}
              </div>
              <ToolConnectionStatusTag scope="tool.redis" status={selectedInstance.testStatus} />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(event) => onChange(selectedInstance.id, 'name', event.target.value)}
                placeholder={t('tool.redis.instanceNamePlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.url')}</div>
              <Input
                value={selectedInstance.url}
                onChange={(event) => onChange(selectedInstance.id, 'url', event.target.value)}
                placeholder={t('tool.redis.urlPlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.username')}</div>
                <Input
                  value={selectedInstance.username}
                  onChange={(event) => onChange(selectedInstance.id, 'username', event.target.value)}
                  placeholder={t('tool.redis.usernamePlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.password')}</div>
                <Input.Password
                  value={selectedInstance.password}
                  onChange={(event) => onChange(selectedInstance.id, 'password', event.target.value)}
                  placeholder={t('tool.redis.passwordPlaceholder')}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-2">
                <Switch checked={selectedInstance.ssl} onChange={(checked) => onChange(selectedInstance.id, 'ssl', checked)} />
                <span>{t('tool.redis.ssl')}</span>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={selectedInstance.cluster_mode} onChange={(checked) => onChange(selectedInstance.id, 'cluster_mode', checked)} />
                <span>{t('tool.redis.clusterMode')}</span>
              </div>
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCaPath')}</div>
              <Input
                value={selectedInstance.ssl_ca_path}
                onChange={(event) => onChange(selectedInstance.id, 'ssl_ca_path', event.target.value)}
                placeholder={t('tool.redis.sslCaPathPlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslKeyfile')}</div>
              <Input
                value={selectedInstance.ssl_keyfile}
                onChange={(event) => onChange(selectedInstance.id, 'ssl_keyfile', event.target.value)}
                placeholder={t('tool.redis.sslKeyfilePlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCertfile')}</div>
              <Input
                value={selectedInstance.ssl_certfile}
                onChange={(event) => onChange(selectedInstance.id, 'ssl_certfile', event.target.value)}
                placeholder={t('tool.redis.sslCertfilePlaceholder')}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCertReqs')}</div>
                <Input
                  value={selectedInstance.ssl_cert_reqs}
                  onChange={(event) => onChange(selectedInstance.id, 'ssl_cert_reqs', event.target.value)}
                  placeholder={t('tool.redis.sslCertReqsPlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.redis.sslCaCerts')}</div>
                <Input
                  value={selectedInstance.ssl_ca_certs}
                  onChange={(event) => onChange(selectedInstance.id, 'ssl_ca_certs', event.target.value)}
                  placeholder={t('tool.redis.sslCaCertsPlaceholder')}
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button loading={testing} onClick={onTest}>
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
};

export default RedisToolEditor;
