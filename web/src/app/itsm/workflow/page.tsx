'use client';

import { Button, Input, Tag, message } from 'antd';
import Link from 'next/link';
import OperateModal from '@/components/operate-modal';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi } from '../api/useItsmApi';
import type { WorkflowListItem } from '../types';

export default function WorkflowListPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const router = useRouter();
  const [items, setItems] = useState<WorkflowListItem[]>([]);
  const [keyword, setKeyword] = useState('');
  const [versions, setVersions] = useState<Array<{ id: number; version_no: number; is_current: boolean; workflowId: number }>>([]);
  const [versionOpen, setVersionOpen] = useState(false);

  const load = useCallback(async () => {
    const data = await api.listWorkflows() as { items?: WorkflowListItem[] };
    setItems(data.items || []);
  }, [api.listWorkflows]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const create = async () => {
    const created = await api.createWorkflow({ name: t('itsm.design.defaultFlow'), key: `flow_${Date.now()}` }) as { id: number };
    router.push(`/itsm/workflow/designer/${created.id}`);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">{t('itsm.admin.workflow')}</div>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="w-52" placeholder={t('itsm.admin.searchName')} value={keyword} onChange={(event) => setKeyword(event.target.value)} allowClear />
          <Button type="primary" onClick={() => { void create(); }}>{t('itsm.admin.newWorkflow')}</Button>
        </div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <CustomTable
          rowKey="id"
          dataSource={items.filter((item) => !keyword.trim() || `${item.name} ${item.key}`.includes(keyword.trim()))}
          locale={{ emptyText: t('itsm.admin.emptyWorkflow') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.admin.key'), dataIndex: 'key', key: 'key' },
            {
              title: t('itsm.ticket.status'),
              key: 'status',
              render: (_value, record: WorkflowListItem) => (
                <Tag color={record.current_version_id ? 'processing' : 'default'}>
                  {record.current_version_id ? t('itsm.admin.published', undefined, { version: String(record.current_version_id) }) : t('itsm.admin.unpublished')}
                </Tag>
              ),
            },
            {
              title: t('itsm.ticket.action'),
              key: 'action',
              render: (_value, record: WorkflowListItem) => (
                <span className="inline-flex gap-3">
                  <Link href={`/itsm/workflow/designer/${record.id}`} className="text-[var(--color-primary)]">
                    {t('itsm.admin.design')}
                  </Link>
                  <button
                    type="button"
                    className="text-[var(--color-primary)]"
                    onClick={() => {
                      void api.exportWorkflow(record.id).then((data) => {
                        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.href = url;
                        link.download = `${record.key}.json`;
                        link.click();
                        URL.revokeObjectURL(url);
                      });
                    }}
                  >
                    {t('itsm.admin.export')}
                  </button>
                  <label className="cursor-pointer text-[var(--color-primary)]">
                    {t('itsm.admin.import')}
                    <input
                      className="hidden"
                      type="file"
                      accept="application/json"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (!file) {
                          return;
                        }
                        void file.text().then((text) => {
                          const parsed = JSON.parse(text) as { design?: unknown };
                          return api.importWorkflow(record.id, parsed.design || parsed);
                        }).then(() => message.success(t('itsm.admin.imported'))).catch((error: unknown) => {
                          message.error(error instanceof Error ? error.message : t('itsm.admin.importFailed'));
                        });
                        event.target.value = '';
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="text-[var(--color-primary)]"
                    onClick={() => {
                      void api.listWorkflowVersions(record.id).then((data) => {
                        const payload = data as { items?: Array<{ id: number; version_no: number; is_current: boolean }> };
                        setVersions((payload.items || []).map((item) => ({ ...item, workflowId: record.id })));
                        setVersionOpen(true);
                      }).catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.admin.versionFailed')));
                    }}
                  >
                    {t('itsm.admin.versions')}
                  </button>
                </span>
              ),
            },
          ]}
        />
        <OperateModal title={t('itsm.admin.versionTitle')} open={versionOpen} footer={null} onCancel={() => setVersionOpen(false)}>
          {versions.length ? versions.map((item) => (
            <div key={item.id} className="mb-2 flex items-center justify-between text-sm">
              <span>v{item.version_no}{item.is_current ? ` · ${t('itsm.admin.currentVersion')}` : ''}</span>
              {item.is_current ? null : (
                <Button size="small" onClick={() => { void api.enableWorkflowVersion(item.workflowId, item.id).then(() => { message.success(t('itsm.admin.enabled')); return load(); }); }}>{t('itsm.admin.enable')}</Button>
              )}
            </div>
          )) : <div className="text-sm text-[var(--color-text-3)]">{t('itsm.admin.noVersion')}</div>}
        </OperateModal>
      </div>
    </div>
  );
}
