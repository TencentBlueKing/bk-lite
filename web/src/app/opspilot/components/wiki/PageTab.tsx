'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AutoComplete, Button, Drawer, Form, Input, List, Popconfirm, Select, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { KnowledgePage, PageVersion } from '@/app/opspilot/types/wiki';
import ContributionTag from './ContributionTag';

const PageTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchPages, createPage, updatePage, deletePage, fetchPageVersions, restorePageVersion, fetchPageDiff } =
    useWikiApi();
  const [data, setData] = useState<KnowledgePage[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // 编辑器抽屉(新建/编辑共用)。editing=null → 新建模式
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<KnowledgePage | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 版本面板(仅编辑已存在页面时显示)
  const [versions, setVersions] = useState<PageVersion[]>([]);
  const [diffLines, setDiffLines] = useState<string[]>([]);
  const [diffVer, setDiffVer] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchPages(kbId, { page, page_size: pageSize });
      setData(res.items);
      setTotal(res.count);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize]);

  // 类型建议:取当前库已有的去重类型,便于人工建页时与 schema 对齐(仍允许自由输入)
  const typeOptions = useMemo(
    () => Array.from(new Set(data.map((d) => d.page_type).filter(Boolean))).map((v) => ({ value: v })),
    [data]
  );

  const openCreate = () => {
    setEditing(null);
    setVersions([]);
    setDiffLines([]);
    setDiffVer(null);
    form.resetFields();
    setEditorOpen(true);
  };

  const openEdit = async (record: KnowledgePage) => {
    setEditing(record);
    setDiffLines([]);
    setDiffVer(null);
    form.setFieldsValue({
      page_type: record.page_type,
      title: record.title,
      tags: record.tags || [],
      body: record.body || '',
    });
    setEditorOpen(true);
    setVersions(await fetchPageVersions(record.id));
  };

  const handleSave = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updatePage(editing.id, { title: v.title, tags: v.tags || [], body: v.body || '' });
      } else {
        await createPage({
          knowledge_base: kbId,
          page_type: v.page_type,
          title: v.title,
          tags: v.tags || [],
          body: v.body || '',
        });
      }
      message.success(t('wiki.saveSuccess'));
      setEditorOpen(false);
      load();
    } finally {
      setSaving(false);
    }
  };

  const showDiff = async (versionId: number) => {
    if (!editing?.current_version) return;
    const res = await fetchPageDiff(editing.id, versionId, editing.current_version);
    setDiffLines(res.diff);
    setDiffVer(versionId);
  };

  const diffColor = (line: string) =>
    line.startsWith('+') ? '#237804' : line.startsWith('-') ? '#a8071a' : 'inherit';

  const handleRestore = async (versionId: number) => {
    if (!editing) return;
    await restorePageVersion(editing.id, versionId);
    message.success(t('wiki.saveSuccess'));
    // 恢复后回填最新正文与版本列表,使抽屉内容与库一致
    const res = await fetchPages(kbId, { page, page_size: pageSize });
    setData(res.items);
    setTotal(res.count);
    const updated = res.items.find((p) => p.id === editing.id) || null;
    if (updated) {
      setEditing(updated);
      form.setFieldsValue({ body: updated.body || '' });
    }
    setVersions(await fetchPageVersions(editing.id));
    setDiffLines([]);
    setDiffVer(null);
  };

  const handleDelete = async (id: number) => {
    await deletePage(id);
    message.success(t('wiki.deleteSuccess'));
    load();
  };

  const columns: ColumnsType<KnowledgePage> = [
    { title: t('wiki.name'), dataIndex: 'title', key: 'title' },
    { title: t('wiki.type'), dataIndex: 'page_type', key: 'page_type', width: 120 },
    {
      title: t('wiki.contribution'),
      dataIndex: 'contribution',
      key: 'contribution',
      width: 120,
      render: (c: string) => <ContributionTag value={c} />,
    },
    { title: t('wiki.status'), dataIndex: 'status', key: 'status', width: 110 },
    {
      title: t('common.actions'),
      key: 'action',
      width: 160,
      render: (_: unknown, record) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(record)}>
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
    <div className="h-full flex flex-col">
      <div className="flex justify-end mb-3 shrink-0">
        <Button type="primary" onClick={openCreate}>
          {t('wiki.newPage')}
        </Button>
      </div>
      {/* flex-1 容器给表格确定高度,使分页时 CustomTable 自动算出的 scroll.y 稳定;
          scroll x:undefined 关闭默认强制横向滚动,列宽自适应容器 */}
      <div className="flex-1 min-h-0">
        <CustomTable<KnowledgePage>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
          scroll={{ x: undefined }}
        />
      </div>

      <Drawer
        title={editing ? t('wiki.editPage') : t('wiki.newPage')}
        open={editorOpen}
        width={680}
        onClose={() => setEditorOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setEditorOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label={t('wiki.type')}
            name="page_type"
            rules={[{ required: true, message: t('wiki.typeRequired') }]}
            tooltip={editing ? t('wiki.typeLockedTip') : undefined}
          >
            {/* 编辑时类型不可改(后端 edit_page 不更新 page_type) */}
            <AutoComplete
              options={typeOptions}
              disabled={!!editing}
              placeholder={t('wiki.type')}
              filterOption={(input, option) =>
                String(option?.value ?? '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item label={t('wiki.name')} name="title" rules={[{ required: true, message: t('wiki.titleRequired') }]}>
            <Input />
          </Form.Item>
          <Form.Item label={t('wiki.tags')} name="tags">
            <Select mode="tags" open={false} placeholder={t('wiki.tagsPlaceholder')} />
          </Form.Item>
          <Form.Item label={t('wiki.body')} name="body">
            <Input.TextArea rows={12} placeholder={t('wiki.bodyPlaceholder')} />
          </Form.Item>
        </Form>

        {editing && (
          <div className="mt-2">
            <List
              header={t('wiki.versionHistory')}
              size="small"
              dataSource={versions}
              renderItem={(v) => (
                <List.Item
                  actions={
                    v.is_current
                      ? [
                        <Tag color="green" key="cur">
                          {t('wiki.current')}
                        </Tag>,
                      ]
                      : [
                        <Button type="link" size="small" key="diff" onClick={() => showDiff(v.id)}>
                          {t('wiki.diff')}
                        </Button>,
                        <Button type="link" size="small" key="restore" onClick={() => handleRestore(v.id)}>
                          {t('wiki.restore')}
                        </Button>,
                      ]
                  }
                >
                  {`v${v.no} · ${v.change_type}`}
                </List.Item>
              )}
            />
            {!!diffLines.length && (
              <div className="mt-3">
                <div className="text-xs text-gray-500 mb-1">{`v${versions.find((x) => x.id === diffVer)?.no ?? '?'} → current`}</div>
                <pre className="text-xs whitespace-pre-wrap">
                  {diffLines.map((ln, i) => (
                    <div key={i} style={{ color: diffColor(ln) }}>
                      {ln}
                    </div>
                  ))}
                </pre>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default PageTab;
