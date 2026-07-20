'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AutoComplete, Button, Descriptions, Drawer, Form, Input, List, Modal, Popconfirm, Select, Space, Tag, Upload, message } from 'antd';
import { DeleteOutlined, DownloadOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import MarkdownRenderer from '@/components/markdown';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { KnowledgePage, MaterialInfo, MaterialType, PageVersion, WikiPageSource } from '@/app/opspilot/types/wiki';
import ContributionTag from './ContributionTag';
import { PAGE_STATUS_LABEL } from './wikiFormat';

const PAGE_STATUS_COLOR: Record<string, string> = { active: 'green', archived: 'default', source_invalid: 'red' };
const MATERIAL_TYPE_KEY: Record<MaterialType, string> = {
  file: 'wiki.materialFile',
  text: 'wiki.materialText',
  web: 'wiki.materialWeb',
};
const isArchivedPage = (record: KnowledgePage) => record.status === 'archived';
const SHOW_PAGE_REINDEX_ACTION = false;

const PageTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const {
    fetchPages,
    createPage,
    updatePage,
    deletePage,
    batchDeletePages,
    exportKnowledgeBaseMarkdown,
    importKnowledgeBaseMarkdown,
    reindexPage,
    fetchPageSources,
    fetchMaterialInfo,
    fetchPageVersions,
    restorePageVersion,
    restorePageFromArchive,
    fetchPageDiff,
  } = useWikiApi();
  const [data, setData] = useState<KnowledgePage[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [nameFilter, setNameFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [filterPageTypes, setFilterPageTypes] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState('active');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [exportingMarkdown, setExportingMarkdown] = useState(false);
  const [importingMarkdown, setImportingMarkdown] = useState(false);
  const [pageSourcesVisible, setPageSourcesVisible] = useState(false);
  const [pageSourcesLoading, setPageSourcesLoading] = useState(false);
  const [pageSourcesTitle, setPageSourcesTitle] = useState('');
  const [pageSources, setPageSources] = useState<WikiPageSource[]>([]);
  const [sourceMaterialDetail, setSourceMaterialDetail] = useState<MaterialInfo | null>(null);
  const [sourceMaterialDetailLoadingId, setSourceMaterialDetailLoadingId] = useState<number | null>(null);
  const [reindexingPageId, setReindexingPageId] = useState<number | null>(null);

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
      const res = await fetchPages(kbId, {
        page,
        page_size: pageSize,
        status: statusFilter,
        title: nameFilter.trim() || undefined,
        page_type: typeFilter.trim() || undefined,
      });
      setData(res.items);
      setTotal(res.count);
      const visibleIds = new Set(res.items.map((item) => item.id));
      setSelectedRowKeys((keys) => keys.filter((key) => visibleIds.has(Number(key))));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize, statusFilter, nameFilter, typeFilter]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize, statusFilter, nameFilter, typeFilter]);

  // 类型建议:取当前库已有的去重类型,便于人工建页时与 schema 对齐(仍允许自由输入)
  const typeOptions = useMemo(
    () => Array.from(new Set(data.map((d) => d.page_type).filter(Boolean))).map((v) => ({ value: v })),
    [data]
  );
  useEffect(() => {
    setFilterPageTypes([]);
  }, [kbId]);

  useEffect(() => {
    const nextTypes = typeOptions.map((option) => String(option.value));
    if (!nextTypes.length) return;
    setFilterPageTypes((current) => {
      const merged = Array.from(new Set([...current, ...nextTypes]));
      return merged.length === current.length ? current : merged;
    });
  }, [typeOptions]);

  const filterTypeOptions = useMemo(() => {
    return [
      { value: '', label: t('wiki.pageTypeAll') },
      ...filterPageTypes.map((value) => ({ value, label: value })),
    ];
  }, [filterPageTypes, t]);
  const statusOptions = useMemo(
    () => [
      { value: 'active', label: t('wiki.statusActive') },
      { value: 'source_invalid', label: t('wiki.statusSourceInvalid') },
      { value: 'archived', label: t('wiki.statusArchived') },
    ],
    [t]
  );
  const selectedPageIds = useMemo(() => selectedRowKeys.map((key) => Number(key)), [selectedRowKeys]);
  const hasSelectedPages = selectedPageIds.length > 0;

  const openCreate = () => {
    setEditing(null);
    setVersions([]);
    setDiffLines([]);
    setDiffVer(null);
    form.resetFields();
    setEditorOpen(true);
  };

  const openEdit = async (record: KnowledgePage) => {
    if (isArchivedPage(record)) {
      await openView(record);
      return;
    }
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

  const openView = async (record: KnowledgePage) => {
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
    if (editing && isArchivedPage(editing)) return;
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
    if (!editing || isArchivedPage(editing)) return;
    await restorePageVersion(editing.id, versionId);
    message.success(t('wiki.saveSuccess'));
    // 恢复后回填最新正文与版本列表,使抽屉内容与库一致
    const res = await fetchPages(kbId, {
      page,
      page_size: pageSize,
      status: statusFilter,
      title: nameFilter.trim() || undefined,
      page_type: typeFilter.trim() || undefined,
    });
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

  const resetSelectionAndPage = () => {
    setSelectedRowKeys([]);
    setPage(1);
  };

  const handleNameFilterSearch = (value: string) => {
    setNameFilter(value);
    resetSelectionAndPage();
  };

  const handleTypeFilterChange = (value: string) => {
    setTypeFilter(value || '');
    resetSelectionAndPage();
  };

  const handleDelete = async (id: number) => {
    await deletePage(id);
    message.success(t('wiki.deleteSuccess'));
    setSelectedRowKeys((keys) => keys.filter((key) => Number(key) !== id));
    load();
  };

  const handleRestoreFromArchive = async (record: KnowledgePage) => {
    await restorePageFromArchive(record.id);
    message.success(t('wiki.saveSuccess'));
    setSelectedRowKeys((keys) => keys.filter((key) => Number(key) !== record.id));
    load();
  };

  const handleBatchDelete = async () => {
    if (!hasSelectedPages) return;
    setBatchDeleting(true);
    try {
      const res = await batchDeletePages(kbId, selectedPageIds);
      message.success(`${t('wiki.batchDeleteDone')}: ${t('wiki.processed')} ${res.deleted}, ${t('wiki.skipped')} ${res.skipped}`);
      setSelectedRowKeys([]);
      load();
    } finally {
      setBatchDeleting(false);
    }
  };

  const handleExportMarkdown = async () => {
    setExportingMarkdown(true);
    try {
      const blob = await exportKnowledgeBaseMarkdown(kbId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `wiki-kb-${kbId}-markdown.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      message.success(t('wiki.exportMarkdownDone'));
    } catch {
      message.error(t('wiki.exportMarkdownFailed'));
    } finally {
      setExportingMarkdown(false);
    }
  };

  const handleImportMarkdown = async (file: File) => {
    setImportingMarkdown(true);
    try {
      const res = await importKnowledgeBaseMarkdown(kbId, file);
      message.success(
        `${t('wiki.importMarkdownDone')}: ${t('wiki.processed')} ${res.created + res.updated}, ${t('wiki.skipped')} ${res.skipped}`
      );
      resetSelectionAndPage();
      load();
    } catch {
      message.error(t('wiki.importMarkdownFailed'));
    } finally {
      setImportingMarkdown(false);
    }
  };

  const handleReindexPage = async (record: KnowledgePage) => {
    if (record.status !== 'active') return;
    setReindexingPageId(record.id);
    try {
      await reindexPage(record.id);
      message.success(t('wiki.reindexPageDone'));
      load();
    } finally {
      setReindexingPageId(null);
    }
  };

  const openPageSources = async (record: KnowledgePage) => {
    setPageSourcesTitle(record.title);
    setPageSources([]);
    setPageSourcesVisible(true);
    setPageSourcesLoading(true);
    try {
      const res = await fetchPageSources(record.id);
      setPageSourcesTitle(res.page_title || record.title);
      setPageSources(res.sources || []);
    } finally {
      setPageSourcesLoading(false);
    }
  };

  const openSourceMaterialDetail = async (materialId: number) => {
    setSourceMaterialDetailLoadingId(materialId);
    try {
      setSourceMaterialDetail(await fetchMaterialInfo(materialId));
    } finally {
      setSourceMaterialDetailLoadingId(null);
    }
  };
  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value);
    resetSelectionAndPage();
  };

  const isReadOnlyPage = !!editing && isArchivedPage(editing);
  const materialTypeLabel = (type: MaterialType) => (MATERIAL_TYPE_KEY[type] ? t(MATERIAL_TYPE_KEY[type]) : type);
  const renderPageSource = (source: WikiPageSource) => (
    <List.Item key={source.id}>
      <div className="w-full rounded border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="mb-1 text-xs text-[var(--color-text-3)]">{t('wiki.sourceMaterial')}</div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="link"
                size="small"
                className="h-auto max-w-full p-0 text-left font-medium text-[var(--color-text-1)]"
                loading={sourceMaterialDetailLoadingId === source.material.id}
                onClick={() => openSourceMaterialDetail(source.material.id)}
              >
                <span className="break-all">{source.material.name}</span>
              </Button>
              <Tag className="m-0">{materialTypeLabel(source.material.material_type)}</Tag>
              {source.material.status && <Tag className="m-0">{source.material.status}</Tag>}
            </div>
          </div>
        </div>
        {source.material_version && (
          <div className="mt-2 text-xs text-[var(--color-text-3)]">
            {t('wiki.sourceVersion')} #{source.material_version.id}
          </div>
        )}
        {typeof source.locator?.chunk_index === 'number' && (
          <Tag className="mt-2">
            {t('wiki.sourceChunk')} #{source.locator.chunk_index + 1}
            {typeof source.locator.chunk_count === 'number' ? ` / ${source.locator.chunk_count}` : ''}
          </Tag>
        )}
        {source.snippet && (
          <div className="mt-2">
            <div className="mb-1 text-xs text-[var(--color-text-3)]">{t('wiki.sourceSnippet')}</div>
            <div className="max-w-full overflow-x-auto text-sm text-[var(--color-text-2)]">
              <MarkdownRenderer content={source.snippet} />
            </div>
          </div>
        )}
        {source.locator_raw && (
          <div className="mt-2 break-words text-xs text-[var(--color-text-3)]">{source.locator_raw}</div>
        )}
      </div>
    </List.Item>
  );

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
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => (
        <Tag color={PAGE_STATUS_COLOR[s] || 'default'}>{PAGE_STATUS_LABEL[s] ? t(PAGE_STATUS_LABEL[s]) : s}</Tag>
      ),
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 300,
      render: (_: unknown, record) =>
        isArchivedPage(record) ? (
          <Space>
            <Button type="link" size="small" onClick={() => openView(record)}>
              {t('wiki.viewPage')}
            </Button>
            <Button type="link" size="small" onClick={() => openPageSources(record)}>
              {t('wiki.pageSources')}
            </Button>
            <Popconfirm title={t('wiki.restoreArchiveConfirm')} onConfirm={() => handleRestoreFromArchive(record)}>
              <Button type="link" size="small">
                {t('wiki.restoreArchive')}
              </Button>
            </Popconfirm>
            <Popconfirm title={t('wiki.deleteConfirm')} onConfirm={() => handleDelete(record.id)}>
              <Button type="link" size="small" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </Space>
        ) : (
          <Space>
            <Button type="link" size="small" onClick={() => openEdit(record)}>
              {t('common.edit')}
            </Button>
            <Button type="link" size="small" onClick={() => openPageSources(record)}>
              {t('wiki.pageSources')}
            </Button>
            {SHOW_PAGE_REINDEX_ACTION && record.status === 'active' && (
              <Button
                type="link"
                size="small"
                loading={reindexingPageId === record.id}
                disabled={reindexingPageId !== null && reindexingPageId !== record.id}
                onClick={() => handleReindexPage(record)}
              >
                {t('wiki.reindexPage')}
              </Button>
            )}
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
      <div className="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-2">
        <Space size={8} wrap>
          <span className="text-xs text-[var(--color-text-3)]">{t('wiki.filterName')}</span>
          <Input.Search
            allowClear
            value={nameFilter}
            placeholder={t('wiki.filterNamePlaceholder')}
            className="w-[180px]"
            onChange={(event) => handleNameFilterSearch(event.target.value)}
            onSearch={handleNameFilterSearch}
          />
          <span className="text-xs text-[var(--color-text-3)]">{t('wiki.filterType')}</span>
          <Select
            value={typeFilter}
            options={filterTypeOptions}
            placeholder={t('wiki.pageTypeAll')}
            className="min-w-[140px]"
            onChange={handleTypeFilterChange}
          />
          <span className="text-xs text-[var(--color-text-3)]">{t('wiki.filterStatus')}</span>
          <Select
            value={statusFilter}
            options={statusOptions}
            className="min-w-[132px]"
            onChange={handleStatusFilterChange}
          />
          <Popconfirm
            title={t('wiki.batchDeletePagesConfirm')}
            okText={t('wiki.confirm')}
            cancelText={t('common.cancel')}
            disabled={!hasSelectedPages}
            onConfirm={handleBatchDelete}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!hasSelectedPages} loading={batchDeleting}>
              {t('wiki.batchDeletePages')}
            </Button>
          </Popconfirm>
        </Space>
        <Space size={8} wrap>
          <Upload
            accept=".md,.markdown,.zip"
            showUploadList={false}
            beforeUpload={(file) => {
              handleImportMarkdown(file);
              return false;
            }}
          >
            <Button icon={<UploadOutlined />} loading={importingMarkdown}>
              {t('wiki.importMarkdown')}
            </Button>
          </Upload>
          <Button icon={<DownloadOutlined />} loading={exportingMarkdown} onClick={handleExportMarkdown}>
            {t('wiki.exportMarkdown')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('wiki.newPage')}
          </Button>
        </Space>
      </div>
      {/* flex-1 容器给表格确定高度,使分页时 CustomTable 自动算出的 scroll.y 稳定;
          scroll x:undefined 关闭默认强制横向滚动,列宽自适应容器 */}
      <div className="flex-1 min-h-0">
        <CustomTable<KnowledgePage>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
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
        title={isReadOnlyPage ? t('wiki.viewPage') : editing ? t('wiki.editPage') : t('wiki.newPage')}
        open={editorOpen}
        width={680}
        onClose={() => setEditorOpen(false)}
        extra={isReadOnlyPage ? null : (
          <Space>
            <Button onClick={() => setEditorOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>
              {t('common.save')}
            </Button>
          </Space>
        )}
      >
        {isReadOnlyPage && <div className="mb-3 text-xs text-[var(--color-text-3)]">{t('wiki.archivedReadOnlyTip')}</div>}
        <Form form={form} layout="vertical" disabled={isReadOnlyPage}>
          <Form.Item
            label={t('wiki.type')}
            name="page_type"
            rules={[{ required: true, message: t('wiki.typeRequired') }]}
            tooltip={editing ? t('wiki.typeLockedTip') : undefined}
          >
            {/* 编辑时类型不可改(后端 edit_page 不更新 page_type) */}
            <AutoComplete
              options={typeOptions}
              disabled={!!editing || isReadOnlyPage}
              placeholder={t('wiki.type')}
              filterOption={(input, option) =>
                String(option?.value ?? '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item label={t('wiki.name')} name="title" rules={[{ required: true, message: t('wiki.titleRequired') }]}>
            <Input disabled={isReadOnlyPage} />
          </Form.Item>
          <Form.Item label={t('wiki.tags')} name="tags">
            <Select mode="tags" open={false} placeholder={t('wiki.tagsPlaceholder')} disabled={isReadOnlyPage} />
          </Form.Item>
          <Form.Item label={t('wiki.body')} name="body">
            <Input.TextArea rows={12} placeholder={t('wiki.bodyPlaceholder')} disabled={isReadOnlyPage} />
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
                        !isReadOnlyPage && (
                          <Button type="link" size="small" key="restore" onClick={() => handleRestore(v.id)}>
                            {t('wiki.restore')}
                          </Button>
                        ),
                      ].filter(Boolean)
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
      <Drawer
        title={`${t('wiki.pageSources')}: ${pageSourcesTitle}`}
        open={pageSourcesVisible}
        width="min(960px, calc(100vw - 48px))"
        onClose={() => setPageSourcesVisible(false)}
      >
        <List
          loading={pageSourcesLoading}
          locale={{ emptyText: t('wiki.noPageSources') }}
          dataSource={pageSources}
          renderItem={renderPageSource}
        />
      </Drawer>
      <Modal
        title={`${t('wiki.detail')}: ${sourceMaterialDetail?.material?.name ?? ''}`}
        open={!!sourceMaterialDetail}
        width="min(960px, calc(100vw - 48px))"
        onCancel={() => setSourceMaterialDetail(null)}
        footer={null}
        destroyOnHidden
        styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto' } }}
      >
        {sourceMaterialDetail && (
          <>
            <Descriptions
              column={1}
              bordered
              size="small"
              className="mb-4"
              labelStyle={{ width: 144, whiteSpace: 'nowrap' }}
              contentStyle={{ minWidth: 0 }}
            >
              <Descriptions.Item label={t('wiki.materialType')}>
                {materialTypeLabel(sourceMaterialDetail.material.material_type)}
              </Descriptions.Item>
              {sourceMaterialDetail.material.material_type === 'web' && (
                <Descriptions.Item label={t('wiki.webSyncEnabled')}>
                  {sourceMaterialDetail.material.sync_policy?.enabled
                    ? `${t('wiki.webSyncInterval')} ${sourceMaterialDetail.material.sync_policy?.interval_hours ?? 24} ${t('wiki.hours')}`
                    : '--'}
                </Descriptions.Item>
              )}
              {sourceMaterialDetail.material.material_type === 'file' && (
                <Descriptions.Item label={t('wiki.imageEnhance')}>
                  {sourceMaterialDetail.material.ocr_enhance ? t('common.yes') : t('common.no')}
                </Descriptions.Item>
              )}
              <Descriptions.Item label={sourceMaterialDetail.file_url ? t('wiki.materialFile') : t('wiki.materialText')}>
                {sourceMaterialDetail.file_url ? (
                  <a href={sourceMaterialDetail.file_url} target="_blank" rel="noreferrer">
                    {t('wiki.downloadFile')}
                  </a>
                ) : sourceMaterialDetail.original ? (
                  <div className="max-w-full overflow-x-auto text-sm">
                    <MarkdownRenderer content={sourceMaterialDetail.original} />
                  </div>
                ) : (
                  '--'
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('wiki.aiSummary')}>
                {sourceMaterialDetail.ai_summary ? (
                  <div className="max-w-full overflow-x-auto text-xs">
                    <MarkdownRenderer content={sourceMaterialDetail.ai_summary} />
                  </div>
                ) : (
                  '--'
                )}
              </Descriptions.Item>
            </Descriptions>
            <div className="mb-2 font-medium">{t('wiki.versions')}</div>
            <List
              size="small"
              dataSource={sourceMaterialDetail.versions}
              renderItem={(version) => (
                <List.Item>{`#${version.id} ${version.content_hash || ''} ${version.created_at || ''}`}</List.Item>
              )}
            />
            <div className="mt-4 mb-2 font-medium">{t('wiki.contributedPages')}</div>
            <List
              size="small"
              dataSource={sourceMaterialDetail.contributed_pages}
              renderItem={(page) => <List.Item>{`${page.title} · ${page.page_type} · ${page.status}`}</List.Item>}
            />
          </>
        )}
      </Modal>
    </div>
  );
};

export default PageTab;
