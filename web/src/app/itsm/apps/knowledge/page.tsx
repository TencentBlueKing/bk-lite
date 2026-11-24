'use client';

import { DownloadOutlined, PaperClipOutlined } from '@ant-design/icons';
import { Alert, App, AutoComplete, Button, Input, Popconfirm, Select, Tag, Upload } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import CustomTable from '@/components/custom-table';
import useApiClient from '@/utils/request';
import { ItsmDrawer } from '../../components/interaction-surfaces';
import { ItsmCreateButton, ItsmListTabs, ItsmListToolbar, ItsmRowActions } from '../../components/list-controls';
import { ItsmListEntry } from '../../components/list-entry';
import { ArticleBody, ArticleBodyEditor, type ArticleFormat } from './article-body';
import { ArticleTicketPicker, type ArticleTicket } from './article-ticket-picker';

const articlesPath = '/itsm/api/resources/knowledge';
type Status = 'draft' | 'published';
type Filter = 'all' | Status;

interface Article {
  id: number;
  title: string;
  status: Status;
  updated_at: string;
  category?: string;
}

interface ArticleDetail extends Article {
  content: string;
  content_format?: ArticleFormat;
  tickets?: ArticleTicket[];
  attachments?: ArticleAttachment[];
  can_link_tickets?: boolean;
  can_upload?: boolean;
}

interface ArticleAttachment {
  id: number;
  name: string;
  size: number;
  can_delete?: boolean;
}

interface PendingAttachment {
  key: string;
  file: File;
}

interface ArticlePage {
  items: Article[];
  count: number;
  categories?: string[];
  can_link_tickets?: boolean;
  can_add?: boolean;
  can_edit?: boolean;
  can_delete?: boolean;
}

interface ArticleDrawer {
  mode: 'read' | 'edit' | 'create';
  id?: number;
  title: string;
  category: string;
  content: string;
  format: ArticleFormat;
  tickets: ArticleTicket[];
  attachments: ArticleAttachment[];
  pendingFiles: PendingAttachment[];
  canLink: boolean;
  canUpload: boolean;
}

function StatusTag({ status }: { status: Status }) {
  return <Tag color={status === 'published' ? 'success' : undefined}>{status === 'published' ? '已发布' : '草稿'}</Tag>;
}

export default function KnowledgePage() {
  const { message } = App.useApp();
  const { get, post, put, del, isLoading } = useApiClient();
  const [data, setData] = useState<ArticlePage>({ items: [], count: 0 });
  const [query, setQuery] = useState({ page: 1, page_size: 20, q: '', status: 'all' as Filter, category: '' });
  const [keyword, setKeyword] = useState('');
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [drawer, setDrawer] = useState<ArticleDrawer | null>(null);
  const [opening, setOpening] = useState(false);
  const openingRequest = useRef<AbortController | null>(null);
  const [pending, setPending] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [attachmentPending, setAttachmentPending] = useState<number | null>(null);
  const drawerBusy = saving || attachmentPending !== null;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const q = keyword.trim();
      setQuery(current => current.q === q ? current : { ...current, q, page: 1 });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [keyword]);

  useEffect(() => {
    if (isLoading) return;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    void get<ArticlePage>(articlesPath, { params: query, signal: controller.signal, suppressErrorNotification: true }).then(result => {
      if (!controller.signal.aborted) setData(result);
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '加载文章失败');
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [get, isLoading, query, revision]);

  useEffect(() => () => openingRequest.current?.abort(), []);
  const reload = () => setRevision(current => current + 1);
  const editDrawer = useCallback((patch: Partial<ArticleDrawer>) => {
    setDrawer(current => current && { ...current, ...patch });
  }, []);
  const changeContent = useCallback((content: string) => editDrawer({ content }), [editDrawer]);

  function createDrawer() {
    setDrawer({
      mode: 'create', title: '', category: query.category, content: '', format: 'richtext',
      tickets: [], attachments: [], pendingFiles: [], canLink: data.can_link_tickets === true, canUpload: true,
    });
  }

  async function openArticle(article: Article, mode: 'read' | 'edit') {
    openingRequest.current?.abort();
    const controller = new AbortController();
    openingRequest.current = controller;
    setOpening(true);
    try {
      const detail = await get<ArticleDetail>(`${articlesPath}/${article.id}`, { signal: controller.signal });
      if (!controller.signal.aborted) setDrawer({
        mode, id: detail.id, title: detail.title, content: detail.content, category: detail.category ?? '',
        format: detail.content_format ?? 'text', tickets: detail.tickets ?? [],
        attachments: detail.attachments ?? [], pendingFiles: [], canLink: detail.can_link_tickets === true,
        canUpload: detail.can_upload === true,
      });
    } catch (reason) {
      if (!controller.signal.aborted) message.error(reason instanceof Error ? reason.message : '读取文章失败');
    } finally {
      if (!controller.signal.aborted) setOpening(false);
    }
  }

  async function saveArticle() {
    if (!drawer || drawer.mode === 'read') return;
    const title = drawer.title.trim();
    if (!title) throw new Error('请填写标题');
    const payload = {
      title, content: drawer.content, category: drawer.category.trim(), content_format: drawer.format,
      ...(drawer.canLink ? { ticket_ids: drawer.tickets.map(ticket => ticket.id) } : {}),
    };
    const request = { suppressErrorNotification: true };
    setSaving(true);
    try {
      let articleId = drawer.id;
      if (articleId === undefined) {
        const saved = await post<ArticleDetail>(articlesPath, payload, request);
        articleId = saved.id;
        editDrawer({ id: articleId });
        reload();
      } else if (drawer.mode === 'edit' || data.can_edit) {
        await put(`${articlesPath}/${articleId}`, payload, request);
        reload();
      }

      for (const pendingFile of drawer.pendingFiles) {
        const form = new FormData();
        form.append('file', pendingFile.file);
        try {
          const saved = await post<ArticleAttachment>(`/itsm/api/knowledge/${articleId}/attachments`, form, {
            ...request, headers: { 'Content-Type': 'multipart/form-data' },
          });
          setDrawer(current => current && {
            ...current,
            attachments: [...current.attachments, saved],
            pendingFiles: current.pendingFiles.filter(file => file.key !== pendingFile.key),
          });
        } catch (reason) {
          const detail = reason instanceof Error ? reason.message : '请重试';
          throw new Error(`文章已保存，附件「${pendingFile.file.name}」上传失败（${detail}）`);
        }
      }
      setDrawer(null);
      message.success(drawer.mode === 'create' ? '草稿已保存' : '文章已保存');
    } finally {
      setSaving(false);
    }
  }

  async function handleAttachment(attachment: ArticleAttachment, operation: 'download' | 'delete') {
    if (drawer?.id === undefined || drawerBusy) return;
    setAttachmentPending(attachment.id);
    const path = `/itsm/api/knowledge/${drawer.id}/attachments/${attachment.id}`;
    try {
      if (operation === 'download') {
        const { url } = await get<{ url: string }>(`${path}/download`, { suppressErrorNotification: true });
        window.location.assign(url);
      } else {
        await del(path, { suppressErrorNotification: true });
        editDrawer({ attachments: drawer.attachments.filter(file => file.id !== attachment.id) });
        message.success('附件已删除');
      }
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '附件操作失败');
    } finally {
      setAttachmentPending(null);
    }
  }

  async function updateStatus(article: Article, status?: Status) {
    if (pending !== null) return;
    setPending(article.id);
    try {
      const path = `${articlesPath}/${article.id}`;
      if (status) await put(path, { status }, { suppressErrorNotification: true });
      else await del(path, { suppressErrorNotification: true });
      message.success(status === 'published' ? '文章已发布' : status === 'draft' ? '已撤回为草稿' : '已删除文章');
      reload();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : '操作失败');
    } finally {
      setPending(null);
    }
  }

  const categories = (data.categories ?? []).map(category => ({ value: category, label: category }));
  const editorDisabled = drawerBusy || (drawer?.mode === 'create' && drawer.id !== undefined && !data.can_edit);

  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <ItsmListToolbar
      leading={(data.can_add || data.can_edit || data.can_delete) && <ItsmListTabs activeKey={query.status}
        onChange={status => setQuery(current => ({ ...current, status: status as Filter, page: 1 }))}
        items={[{ key: 'all', label: '全部' }, { key: 'published', label: '已发布' }, { key: 'draft', label: '草稿' }]} />}
      filters={<Select className="w-40" aria-label="筛选分类" placeholder="全部分类" allowClear showSearch optionFilterProp="label"
        options={categories} value={query.category || undefined}
        onChange={category => setQuery(current => ({ ...current, category: category ?? '', page: 1 }))} />}
      search={{ value: keyword, onChange: setKeyword, placeholder: '搜索文章标题' }}
      actions={data.can_add && <ItsmCreateButton onClick={createDrawer} />}
    />
    {error && <Alert className="mb-3" showIcon type="error" message={error} action={<Button onClick={reload}>重试</Button>} />}
    <CustomTable<Article> rowKey="id" dataSource={data.items} loading={loading || opening} scroll={{ y: 'calc(100vh - 320px)' }}
      pagination={{ current: query.page, pageSize: query.page_size, total: data.count, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100],
        onChange: (page, size) => setQuery(current => ({ ...current, page: size === current.page_size ? page : 1, page_size: size })) }}
      columns={[
        { title: '文章标题', key: 'title', render: (_, article) => <ItsmListEntry onClick={() => void openArticle(article, 'read')}>{article.title}</ItsmListEntry> },
        { title: '分类', dataIndex: 'category', key: 'category', width: 150, ellipsis: true, render: category => category || '未分类' },
        { title: '状态', key: 'status', width: 120, render: (_, article) => <StatusTag status={article.status} /> },
        { title: '更新时间', key: 'updated_at', width: 200, render: (_, article) => new Date(article.updated_at).toLocaleString() },
        ...(data.can_edit || data.can_delete ? [{
          title: '操作', key: 'actions', width: 120, render: (_: unknown, article: Article) => <ItsmRowActions items={[
            { key: 'edit', label: '编辑', kind: 'edit', hidden: !data.can_edit, onClick: () => void openArticle(article, 'edit') },
            { key: 'publish', label: '发布', kind: 'publish', hidden: !data.can_edit || article.status === 'published', disabled: pending !== null,
              onClick: () => void updateStatus(article, 'published') },
            { key: 'withdraw', label: '撤回为草稿', kind: 'history', hidden: !data.can_edit || article.status === 'draft', disabled: pending !== null,
              confirm: { title: '撤回为草稿', content: article.title }, onClick: () => updateStatus(article, 'draft') },
            { key: 'delete', label: '删除', kind: 'delete', hidden: !data.can_delete, disabled: pending !== null,
              danger: true, confirm: { title: '删除文章', content: article.title }, onClick: () => updateStatus(article) },
          ]} />,
        }] : []),
      ]} />
    <ItsmDrawer open={Boolean(drawer)} width={860} formValue={drawer} onCancel={() => setDrawer(null)} confirmLoading={drawerBusy} destroyOnHidden
      onOk={drawer?.mode === 'read' ? undefined : saveArticle} okText={drawer?.mode === 'create' ? '保存草稿' : '保存'}
      title={drawer?.mode === 'read' ? drawer.title : drawer?.mode === 'edit' ? '编辑文章' : '新建文章'}>
      {drawer && <div className="flex min-w-0 flex-col gap-4">
        {drawer.mode === 'read' ? <>
          {drawer.category && <div><Tag>{drawer.category}</Tag></div>}
          <ArticleBody content={drawer.content} format={drawer.format} />
          {drawer.tickets.length > 0 && <section className="space-y-2">
            <h3 className="text-sm font-medium">关联工单</h3>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {drawer.tickets.map(ticket => <li key={ticket.id}><Link className="break-words text-[var(--color-primary)]"
                href={`/itsm/tickets/${ticket.id}`}>{ticket.title}（{ticket.sn}）</Link></li>)}
            </ul>
          </section>}
        </> : <>
          <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
            <label className="flex min-w-0 flex-col gap-2">标题
              <Input value={drawer.title} maxLength={200} disabled={editorDisabled} onChange={event => editDrawer({ title: event.target.value })} />
            </label>
            <label className="flex min-w-0 flex-col gap-2">分类
              <AutoComplete options={categories} value={drawer.category} allowClear disabled={editorDisabled}
                filterOption={(value, option) => (option?.value ?? '').toLowerCase().includes(value.toLowerCase())}
                onChange={category => editDrawer({ category: category?.slice(0, 128) ?? '' })}>
                <Input aria-label="分类" placeholder="选择或输入分类" />
              </AutoComplete>
            </label>
          </div>
          {drawer.canLink && <ArticleTicketPicker tickets={drawer.tickets} disabled={editorDisabled} onChange={tickets => editDrawer({ tickets })} />}
          <ArticleBodyEditor content={drawer.content} format={drawer.format} disabled={editorDisabled} onContentChange={changeContent}
            onFormatChange={(format, content) => editDrawer({ format, content })} />
        </>}
        {(drawer.canUpload && drawer.mode !== 'read' || drawer.attachments.length > 0) && <section className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="m-0 text-sm font-medium">附件</h3>
            {drawer.canUpload && drawer.mode !== 'read' && <Upload name="file" multiple showUploadList={false} disabled={drawerBusy}
              beforeUpload={file => {
                if (file.size > 20 * 1024 * 1024) message.error('附件不得超过 20 MB');
                else setDrawer(current => current && { ...current, pendingFiles: [...current.pendingFiles, { key: file.uid, file }] });
                return Upload.LIST_IGNORE;
              }}>
              <Button icon={<PaperClipOutlined />} disabled={drawerBusy}>上传附件</Button>
            </Upload>}
          </div>
          <ul className="m-0 list-none p-0">
            {drawer.attachments.map(file => <li className="flex items-center gap-2 py-1" key={file.id}>
              <Button type="link" icon={<DownloadOutlined />} disabled={drawerBusy} onClick={() => void handleAttachment(file, 'download')}
                className="max-w-full truncate px-0">{file.name}</Button>
              {drawer.mode !== 'read' && file.can_delete && <Popconfirm title="删除附件" description={file.name} okText="删除" cancelText="取消"
                onConfirm={() => handleAttachment(file, 'delete')}>
                <Button size="small" type="text" danger disabled={drawerBusy} aria-label={`删除附件 ${file.name}`}>删除</Button>
              </Popconfirm>}
            </li>)}
            {drawer.pendingFiles.map(file => <li className="flex items-center gap-2 py-1" key={file.key}>
              <span className="min-w-0 truncate">{file.file.name}</span>
              <Tag>待上传</Tag>
              <Button size="small" type="text" disabled={drawerBusy} aria-label={`移除待上传附件 ${file.file.name}`}
                onClick={() => editDrawer({ pendingFiles: drawer.pendingFiles.filter(item => item.key !== file.key) })}>移除</Button>
            </li>)}
          </ul>
        </section>}
      </div>}
    </ItsmDrawer>
  </div>;
}
