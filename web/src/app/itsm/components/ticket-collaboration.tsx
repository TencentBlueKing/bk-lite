'use client';

import { App, Button, Empty, Input, Modal, Popconfirm, Tabs, Tag, Upload, type TabsProps } from 'antd';
import { PaperClipOutlined, PictureOutlined, DownloadOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import type { TicketAttachmentItem, TicketCommentItem } from '../types';

export const formatTicketTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';

export function TicketCollaboration({ ticketId, extraTabs = [], historyFirst = false }: { ticketId: number; extraTabs?: TabsProps['items']; historyFirst?: boolean }) {
  const api = useItsmApi();
  const { message } = App.useApp();
  const [notes, setNotes] = useState<TicketCommentItem[]>([]);
  const [files, setFiles] = useState<TicketAttachmentItem[]>([]);
  const [content, setContent] = useState('');
  const [reply, setReply] = useState<TicketCommentItem>();
  const [draftFiles, setDraftFiles] = useState<number[]>([]);
  const [uploading, setUploading] = useState(0);
  const [publishing, setPublishing] = useState(false);
  const [preview, setPreview] = useState<{ name: string; url: string }>();
  const inFlight = useRef(0);
  const failed = useCallback((error: unknown) => { message.error(error instanceof Error ? error.message : '操作失败，请重试'); }, [message]);
  const refresh = useCallback(async () => {
    const [comments, attachments] = await Promise.all([
      api.listComments(ticketId) as Promise<{ items: TicketCommentItem[] }>,
      api.listAttachments(ticketId) as Promise<{ items: TicketAttachmentItem[] }>,
    ]);
    setNotes(comments.items);
    setFiles(attachments.items);
  }, [api.listComments, api.listAttachments, ticketId]);
  useEffect(() => { if (api.ready) void refresh().catch(failed); }, [api.ready, refresh, failed]);
  const download = async (file: TicketAttachmentItem, view = false) => {
    try {
      const data = await api.downloadAttachment(ticketId, file.id) as { url: string };
      if (view) setPreview({ name: file.name, url: data.url });
      else window.location.assign(data.url);
    } catch (error) { failed(error); }
  };
  const upload = (forComment: boolean, images = false) => (
    <Upload multiple accept={images ? 'image/png,image/jpeg,image/gif,image/webp' : undefined} showUploadList={false}
      beforeUpload={(file) => {
        if (file.size > 20 * 1024 * 1024) { message.error('附件不得超过 20 MB'); return Upload.LIST_IGNORE; }
        return true;
      }}
      customRequest={async (options) => {
        inFlight.current += 1;
        setUploading(inFlight.current);
        try {
          const file = options.file as File;
          const signed = await api.presignAttachment(file.name, ticketId) as { url: string; receipt: string };
          const response = await fetch(signed.url, { method: 'PUT', body: file });
          if (!response.ok) throw new Error('附件上传失败');
          const added = await api.addAttachment(ticketId, { receipt: signed.receipt }) as TicketAttachmentItem;
          if (forComment) setDraftFiles((ids) => [...ids, added.id]);
          await refresh();
          options.onSuccess?.(added);
        } catch (error) { failed(error); options.onError?.(error as Error); }
        finally { inFlight.current -= 1; setUploading(inFlight.current); }
      }}>
      <Button icon={images ? <PictureOutlined /> : <PaperClipOutlined />} disabled={publishing}>
        {images ? '添加图片' : forComment ? '添加附件' : '上传附件'}
      </Button>
    </Upload>
  );
  const fileLink = (file: TicketAttachmentItem) => (
    <div key={file.id} className="flex flex-wrap items-center gap-2">
      <Button type="link" className="!h-auto !whitespace-normal !px-0 !text-left" icon={<PaperClipOutlined />} onClick={() => void download(file)}>{file.name}</Button>
      {/\.(png|jpe?g|gif|webp)$/i.test(file.name) ? <Button type="link" size="small" onClick={() => void download(file, true)}>预览图片</Button> : null}
    </div>
  );
  const publish = async () => {
    if (inFlight.current || publishing || (!content.trim() && !draftFiles.length)) return;
    setPublishing(true);
    try {
      await api.addComment(ticketId, content.trim(), reply?.id, draftFiles);
      setContent(''); setReply(undefined); setDraftFiles([]);
      await refresh();
    } catch (error) { failed(error); } finally { setPublishing(false); }
  };
  return <>
    <Tabs className="h-full min-h-0 [&>.ant-tabs-nav]:shrink-0 [&>.ant-tabs-content-holder]:min-h-0 [&>.ant-tabs-content-holder]:flex-1 [&>.ant-tabs-content-holder]:overflow-y-auto [&>.ant-tabs-content-holder]:overscroll-contain" defaultActiveKey={historyFirst ? 'history' : 'comments'} items={[
      ...(historyFirst ? extraTabs.filter((item) => item.key === 'history' || item.key === 'sla') : []),
      { key: 'comments', label: `评论 (${notes.length})`, children: <div className="flex flex-col gap-4">
        {notes.length ? notes.map((item) => {
          const parent = notes.find((note) => note.id === item.parent_id);
          return <article key={item.id} className="border-b border-[var(--color-border)] pb-3">
            <div className="flex items-center justify-between gap-2 text-xs text-[var(--color-text-3)]">
              <span><span className="font-medium text-[var(--color-text-1)]">{item.operator}</span> · {formatTicketTime(item.created_at)}</span>
              <Button type="link" size="small" onClick={() => setReply(item)}>回复</Button>
            </div>
            {parent ? <blockquote className="my-2 border-l-2 border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2 text-xs text-[var(--color-text-3)]">回复 {parent.operator}：{parent.content || '附件评论'}</blockquote> : null}
            <p className="my-2 whitespace-pre-wrap break-words text-sm text-[var(--color-text-1)]">{item.content}</p>
            {files.filter((file) => item.attachment_ids.includes(file.id)).map(fileLink)}
          </article>;
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评论" />}
        <div className="rounded-lg border border-[var(--color-border)] p-3">
          {reply ? <div className="mb-2 flex items-center justify-between gap-2 text-xs text-[var(--color-text-3)]"><span className="truncate">回复 {reply.operator}：{reply.content || '附件评论'}</span><Button size="small" type="text" onClick={() => setReply(undefined)}>取消回复</Button></div> : null}
          <Input.TextArea aria-label="评论内容" placeholder={reply ? `回复 ${reply.operator}` : '填写评论，可添加图片和附件'} maxLength={10000} autoSize={{ minRows: 3, maxRows: 8 }} value={content} onChange={(event) => setContent(event.target.value)} />
          <div className="my-2 flex flex-wrap gap-2">{draftFiles.map((id) => <Tag key={id} closable onClose={() => setDraftFiles((ids) => ids.filter((value) => value !== id))}>{files.find((file) => file.id === id)?.name || '附件'}</Tag>)}</div>
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex flex-wrap gap-2">{upload(true, true)}{upload(true)}</div><Button type="primary" loading={publishing} disabled={uploading > 0 || (!content.trim() && !draftFiles.length)} onClick={() => void publish()}>发表评论</Button></div>
          {uploading ? <div role="status" className="mt-2 text-xs text-[var(--color-text-3)]">正在上传 {uploading} 个附件…</div> : null}
        </div>
      </div> },
      { key: 'files', label: `附件 (${files.length})`, children: <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">{upload(false)}<span className="text-xs text-[var(--color-text-3)]">单个文件不超过 20 MB{uploading ? ' · 上传中…' : ''}</span></div>
        {files.length ? files.map((file) => <div key={file.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] py-3">
          <div className="min-w-0">{fileLink(file)}<div className="text-xs text-[var(--color-text-3)]">{file.operator} · {formatTicketTime(file.created_at)} · {(file.size / 1024).toFixed(1)} KB · {file.comment_id ? '来自评论' : '工单附件'}</div></div>
          <div className="flex items-center gap-2"><Button size="small" icon={<DownloadOutlined />} onClick={() => void download(file)}>下载</Button>{file.can_delete ? <Popconfirm title="删除此附件？" description="评论中的附件引用也会移除。" onConfirm={async () => { try { await api.deleteAttachment(ticketId, file.id); setDraftFiles((ids) => ids.filter((id) => id !== file.id)); await refresh(); } catch (error) { failed(error); throw error; } }}><Button size="small" danger>删除</Button></Popconfirm> : null}</div>
        </div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无附件" />}
      </div> },
      ...extraTabs.filter((item) => !historyFirst || (item.key !== 'history' && item.key !== 'sla')),
    ]} />
    <Modal title={preview?.name} open={Boolean(preview)} footer={null} onCancel={() => setPreview(undefined)} destroyOnHidden>
      {/* 私有图片仅按需签发短期地址，不接受 HTML/SVG 作为图片预览。 */}
      {preview ? <img src={preview.url} alt={preview.name} className="max-h-[70vh] max-w-full object-contain" /> : null}
    </Modal>
  </>;
}
