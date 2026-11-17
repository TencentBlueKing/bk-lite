'use client';

import { ItsmListToolbar, ItsmCreateButton, ItsmRowActions } from '@/app/itsm/components/list-controls';

import { Input, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import { FieldRow } from '../components/field-row';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import CustomTable from '@/app/itsm/components/itsm-list-table';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi } from '../api/useItsmApi';
import type { NamedItem } from '../types';

export default function FormListPage() {
  const { t } = useTranslation();
  const api = useItsmApi();
  const router = useRouter();
  const [items, setItems] = useState<NamedItem[]>([]);
  const [name, setName] = useState('');
  const [keyword, setKeyword] = useState('');
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    const data = await api.listForms() as { items?: NamedItem[] };
    setItems(data.items || []);
  }, [api.listForms]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, load]);

  const create = async () => {
    if (!name.trim()) {
      message.warning(t('itsm.admin.needFormName'));
      return;
    }
    const created = await api.createForm({ name: name.trim(), key: `form_${Date.now()}` }) as { id: number };
    router.push(`/itsm/form/designer/${created.id}`);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
        <ItsmListToolbar search={{value: keyword, onChange: setKeyword, label: '搜索表单', placeholder: '搜索名称或标识'}} actions={<>
<ItsmCreateButton onClick={() => setCreateOpen(true)}>新建</ItsmCreateButton>
</>} />
        <CustomTable queryKey={keyword}
          rowKey="id"
          dataSource={items.filter((item) => !keyword.trim() || `${item.name} ${item.key}`.toLowerCase().includes(keyword.trim().toLowerCase()))}
          locale={{ emptyText: t('itsm.admin.emptyForm') }}
          columns={[
            { title: t('itsm.portal.name'), dataIndex: 'name', key: 'name' },
            { title: t('itsm.admin.key'), dataIndex: 'key', key: 'key' },
            {
              title: t('itsm.ticket.action'),
              key: 'action',
              fixed: 'right', width: 120,
              render: (_value, record: NamedItem) => <ItsmRowActions items={[
                {key: 'design', label: t('itsm.admin.designForm'), kind: 'edit', onClick: () => router.push(`/itsm/form/designer/${record.id}`)},
              ]} />,
            },
          ]}
        />
      </div>
      <OperateModal title={t('itsm.admin.newForm')} open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => { void create(); }}>
        <FieldRow label={t('itsm.admin.formName')}><Input aria-label="表单名称" value={name} onChange={event => setName(event.target.value)} placeholder={t('itsm.admin.formName')} /></FieldRow>
      </OperateModal>
    </div>
  );
}
