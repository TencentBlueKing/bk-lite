'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useIntl } from 'react-intl';
import { Alert, Button, Pagination, Spin, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import usePermissions from '@/hooks/usePermissions';
import { Memory, useMemoryApi } from '@/app/opspilot/api/memory';
import PermissionWrapper from '@/components/permission';
import MarkdownRenderer from '@/components/markdown';
import { HandledRequestError } from '@/utils/request';
import {
  MEMORY_DOCUMENT_PAGE_CHARS,
  MEMORY_PREVIEW_CONTENT_LIMIT,
  formatMemoryContentSize,
  memoryContentLength,
  memoryDocumentPageCount,
  memoryDocumentPageOffset,
  shouldMarkdownRenderMemory,
  shouldPageMemoryDocument,
} from '@/app/opspilot/utils/memoryContent';

export default function MemoryDocumentPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const searchParams = useSearchParams();
  const { fetchMemory, updateMemory } = useMemoryApi();
  const { hasPermission } = usePermissions('/opspilot/memory/detail/memories');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pageBodyRef = useRef<HTMLDivElement>(null);
  const enteredEditFromQuery = useRef(false);

  const memoryId = Number(searchParams.get('memoryId') || 0);
  const startInEdit = searchParams.get('edit') === '1';
  const [memory, setMemory] = useState<Memory | null>(null);
  const [page, setPage] = useState(1);
  const [boundMemoryId, setBoundMemoryId] = useState(memoryId);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  if (boundMemoryId !== memoryId) {
    setBoundMemoryId(memoryId);
    setPage(1);
    setEditing(false);
    setMemory(null);
    enteredEditFromQuery.current = false;
  }

  const fetchPage = boundMemoryId === memoryId ? page : 1;

  useEffect(() => {
    if (!memoryId) {
      setMemory(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const offset = memoryDocumentPageOffset(fetchPage);

    const load = async () => {
      let res = await fetchMemory(memoryId, {
        contentOffset: offset,
        contentLimit: MEMORY_DOCUMENT_PAGE_CHARS,
      });
      const length = res.content_length ?? res.content?.length ?? 0;
      const maxPage = memoryDocumentPageCount(length);
      if (fetchPage > maxPage) {
        setPage(maxPage);
        return null;
      }
      if (fetchPage === 1 && !shouldPageMemoryDocument(length) && res.content_truncated) {
        res = await fetchMemory(memoryId, { contentLimit: MEMORY_PREVIEW_CONTENT_LIMIT });
      }
      return res;
    };

    load()
      .then((res) => {
        if (!cancelled && res) {
          setMemory(res);
          pageBodyRef.current?.scrollTo({ top: 0 });
        }
      })
      .catch((error) => {
        console.error(error);
        if (!cancelled) {
          setMemory(null);
          message.error(t('common.fetchFailed'));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [memoryId, fetchPage, reloadNonce]);

  useEffect(() => {
    if (!memory || enteredEditFromQuery.current || !startInEdit) {
      return;
    }
    if (!hasPermission(['Edit'])) {
      return;
    }
    setEditing(true);
    enteredEditFromQuery.current = true;
  }, [memory, startInEdit, hasPermission]);

  const locale = intl.locale?.startsWith('en') ? 'en' : 'zh';
  const contentLength = memory?.content_length ?? memory?.content?.length ?? 0;
  const contentSize = formatMemoryContentSize(contentLength, locale);
  const paged = shouldPageMemoryDocument(contentLength);
  const totalPages = memoryDocumentPageCount(contentLength);
  const useMarkdown = !paged && shouldMarkdownRenderMemory(contentLength);

  const handleEdit = () => {
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
  };

  const handleSave = async () => {
    if (!memory) {
      return;
    }
    const nextContent = textareaRef.current?.value ?? '';
    const offset = paged ? (memory.content_offset ?? memoryDocumentPageOffset(fetchPage)) : 0;
    setSaving(true);
    try {
      if (paged) {
        await updateMemory(memory.id, {
          content: nextContent,
          content_offset: offset,
          content_replace_length: memoryContentLength(memory.content || ''),
          expected_updated_at: memory.updated_at,
        });
      } else {
        await updateMemory(memory.id, { content: nextContent });
      }
      // 留在当前页，按新字数重拉本页；后续页码和内容随总长度一起更新。
      setEditing(false);
      setReloadNonce((n) => n + 1);
      message.success(t('memory.saveSuccess'));
    } catch (error) {
      if (error instanceof HandledRequestError && error.status === 409) {
        message.warning(t('memory.documentVersionConflict'));
        setEditing(false);
        setReloadNonce((n) => n + 1);
      } else {
        console.error(error);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-screen w-full min-w-0 flex-col bg-(--color-bg)">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-(--color-border-1) bg-(--color-fill-1) px-4">
        <div className="min-w-0">
          <div className="truncate text-[14px] font-semibold text-(--color-text-1)">
            {memory ? `m-${memory.id}` : t('memory.documentTitle')}
          </div>
          {memory ? (
            <div className="text-[11px] text-(--color-text-3)">
              {t('memory.documentSize', undefined, { size: contentSize })}
            </div>
          ) : null}
        </div>
        {memory && !editing && !loading ? (
          <PermissionWrapper requiredPermissions={['Edit']} permissionPath="/opspilot/memory/detail/memories">
            <Button type="primary" size="small" onClick={handleEdit}>
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
        ) : null}
        {editing ? (
          <div className="flex gap-2">
            <Button size="small" onClick={handleCancel}>
              {t('common.cancel')}
            </Button>
            <Button type="primary" size="small" loading={saving} onClick={handleSave}>
              {t('common.confirm')}
            </Button>
          </div>
        ) : null}
      </header>
      <main ref={pageBodyRef} className="min-h-0 flex-1 overflow-auto p-4">
        {loading && !memory ? (
          <div className="flex h-full items-center justify-center">
            <Spin />
          </div>
        ) : !memoryId || !memory ? (
          <div className="flex h-full items-center justify-center text-[13px] text-(--color-text-3)">
            {t('memory.noMemories')}
          </div>
        ) : editing ? (
          <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-3">
            {paged ? (
              <Alert type="info" showIcon message={t('memory.documentEditPageHint')} />
            ) : null}
            <textarea
              ref={textareaRef}
              key={`${memory.updated_at}-${memory.content_offset ?? fetchPage}`}
              defaultValue={memory.content || ''}
              className="min-h-0 w-full flex-1 resize-none rounded-lg border border-(--color-border-1) bg-(--color-fill-1) p-3 font-mono text-[13px] leading-relaxed text-(--color-text-2) outline-none"
            />
          </div>
        ) : (
          <div className="flex min-h-full w-full min-w-0 flex-col gap-3">
            {!paged && !useMarkdown ? (
              <Alert
                type="info"
                showIcon
                message={t('memory.documentPlainTextHint', undefined, { size: contentSize })}
              />
            ) : null}
            {paged ? (
              <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
                <div className="text-[12px] text-(--color-text-3)">
                  {t('memory.documentPageStatus', undefined, {
                    current: fetchPage,
                    total: totalPages,
                    from: formatMemoryContentSize(memoryDocumentPageOffset(fetchPage) + 1, locale),
                    to: formatMemoryContentSize(Math.min(fetchPage * MEMORY_DOCUMENT_PAGE_CHARS, contentLength), locale),
                    size: contentSize,
                  })}
                </div>
                <Pagination
                  size="small"
                  current={fetchPage}
                  pageSize={MEMORY_DOCUMENT_PAGE_CHARS}
                  total={contentLength}
                  showSizeChanger={false}
                  showQuickJumper
                  onChange={setPage}
                />
              </div>
            ) : null}
            <div className="relative">
              {loading ? (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-(--color-bg)/60">
                  <Spin />
                </div>
              ) : null}
              {useMarkdown ? (
                <div className="prose dark:prose-invert max-w-none text-[13px] text-(--color-text-2) leading-relaxed">
                  <MarkdownRenderer content={memory.content || ''} />
                </div>
              ) : (
                <pre
                  key={`${memory.id}-${memory.content_offset ?? fetchPage}`}
                  className="whitespace-pre-wrap break-words rounded-lg border border-(--color-border-1) bg-(--color-fill-1) p-3 font-mono text-[13px] leading-relaxed text-(--color-text-2)"
                >
                  {memory.content || ''}
                </pre>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
