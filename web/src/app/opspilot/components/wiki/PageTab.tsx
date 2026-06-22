'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Drawer, List, Popconfirm, Space, Table, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { KnowledgePage, PageVersion } from '@/app/opspilot/types/wiki';

const PageTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchPages, deletePage, fetchPageVersions, restorePageVersion } = useWikiApi();
  const [data, setData] = useState<KnowledgePage[]>([]);
  const [loading, setLoading] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [active, setActive] = useState<KnowledgePage | null>(null);
  const [versions, setVersions] = useState<PageVersion[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchPages(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const openView = async (record: KnowledgePage) => {
    setActive(record);
    setDrawer(true);
    setVersions(await fetchPageVersions(record.id));
  };

  const handleRestore = async (versionId: number) => {
    if (!active) return;
    await restorePageVersion(active.id, versionId);
    message.success(t('wiki.saveSuccess'));
    setVersions(await fetchPageVersions(active.id));
    load();
  };

  const handleDelete = async (id: number) => {
    await deletePage(id);
    message.success(t('wiki.deleteSuccess'));
    load();
  };

  const columns: ColumnsType<KnowledgePage> = [
    { title: t('wiki.name'), dataIndex: 'title', key: 'title' },
    { title: 'Type', dataIndex: 'page_type', key: 'page_type', width: 120 },
    {
      title: 'Contribution',
      dataIndex: 'contribution',
      key: 'contribution',
      width: 120,
      render: (c: string) => <Tag>{c}</Tag>,
    },
    { title: t('wiki.status'), dataIndex: 'status', key: 'status', width: 110 },
    {
      title: '',
      key: 'action',
      width: 160,
      render: (_: unknown, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => openView(record)}>
            {t('common.edit')}
          </Button>
          <Popconfirm title={t('wiki.deleteConfirm')} onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger>
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Table<KnowledgePage> rowKey="id" loading={loading} columns={columns} dataSource={data} />
      <Drawer title={active?.title} open={drawer} width={640} onClose={() => setDrawer(false)}>
        <pre className="whitespace-pre-wrap text-sm mb-4">{active?.body}</pre>
        <List
          header="Versions"
          size="small"
          dataSource={versions}
          renderItem={(v) => (
            <List.Item
              actions={[
                v.is_current ? (
                  <Tag color="green" key="cur">
                    current
                  </Tag>
                ) : (
                  <Button type="link" size="small" key="restore" onClick={() => handleRestore(v.id)}>
                    restore
                  </Button>
                ),
              ]}
            >
              {`v${v.no} · ${v.change_type}`}
            </List.Item>
          )}
        />
      </Drawer>
    </div>
  );
};

export default PageTab;
