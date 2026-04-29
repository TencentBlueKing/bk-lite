'use client';

import React, { useRef, useEffect } from 'react';
import { Button, Empty, Input, Tag } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

export type JenkinsTestStatus = 'untested' | 'success' | 'failed';

export interface JenkinsInstanceFormValue {
  id: string;
  name: string;
  jenkins_url: string;
  jenkins_username: string;
  jenkins_password: string;
  testStatus: JenkinsTestStatus;
}

interface JenkinsToolEditorProps {
  instances: JenkinsInstanceFormValue[];
  selectedInstanceId: string | null;
  testing: boolean;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onChange: <K extends keyof JenkinsInstanceFormValue>(id: string, field: K, value: JenkinsInstanceFormValue[K]) => void;
  onTest: () => void;
}

const statusColorMap: Record<JenkinsTestStatus, string> = {
  untested: 'default',
  success: 'blue',
  failed: 'red',
};

const JenkinsToolEditor: React.FC<JenkinsToolEditorProps> = ({
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

  const renderStatus = (status: JenkinsTestStatus) => {
    return <Tag color={statusColorMap[status]}>{t(`tool.jenkins.status.${status}`)}</Tag>;
  };

  return (
    <div className="flex gap-4 min-h-[480px]">
      <div className="w-[260px] rounded border border-[var(--color-border)] p-3 flex flex-col">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">{t('tool.jenkins.instances')}</span>
          <Button type="primary" ghost size="small" onClick={onAdd}>
            + {t('common.add')}
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2" ref={listRef}>
          {instances.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('tool.jenkins.noInstances')} />
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
                      <div className="truncate font-medium">{instance.name || t('tool.jenkins.unnamedInstance')}</div>
                      <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">
                        {instance.jenkins_url || t('tool.jenkins.addressNotConfigured')}
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
                {t('tool.jenkins.configTitle').replace('{name}', selectedInstance.name || t('tool.jenkins.unnamedInstance'))}
              </div>
              {renderStatus(selectedInstance.testStatus)}
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.instanceName')}</div>
              <Input
                value={selectedInstance.name}
                onChange={(event) => onChange(selectedInstance.id, 'name', event.target.value)}
                placeholder={t('tool.jenkins.instanceNamePlaceholder')}
              />
            </div>

            <div>
              <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.jenkinsUrl')}</div>
              <Input
                value={selectedInstance.jenkins_url}
                onChange={(event) => onChange(selectedInstance.id, 'jenkins_url', event.target.value)}
                placeholder="http://jenkins:8080"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.jenkinsUsername')}</div>
                <Input
                  value={selectedInstance.jenkins_username}
                  onChange={(event) => onChange(selectedInstance.id, 'jenkins_username', event.target.value)}
                  placeholder={t('tool.jenkins.jenkinsUsernamePlaceholder')}
                />
              </div>
              <div>
                <div className="mb-1 text-sm text-[var(--color-text-2)]">{t('tool.jenkins.jenkinsPassword')}</div>
                <Input.Password
                  value={selectedInstance.jenkins_password}
                  onChange={(event) => onChange(selectedInstance.id, 'jenkins_password', event.target.value)}
                  placeholder={t('tool.jenkins.jenkinsPasswordPlaceholder')}
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button loading={testing} onClick={onTest}>
                {t('tool.jenkins.testConnection')}
              </Button>
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
};

export default JenkinsToolEditor;
