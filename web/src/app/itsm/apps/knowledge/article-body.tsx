'use client';

import { App, Button, Input, Segmented, Skeleton } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import type { AiEditor } from 'aieditor';
import MarkdownIt from 'markdown-it';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import MarkdownRenderer from '@/components/markdown';
import { sanitizeArticleHtml } from './article-html';

const RichTextEditor = dynamic(() => import('./rich-text-editor'), { ssr: false, loading: () => <Skeleton active /> });
const markdown = new MarkdownIt();

export type ArticleFormat = 'text' | 'richtext' | 'markdown';

interface ArticleBodyProps {
  content: string;
  format: ArticleFormat;
}

export function ArticleBody({ content, format }: ArticleBodyProps) {
  const { t } = useTranslation();
  if (!content.trim()) return <p className="text-sm text-[var(--color-text-3)]">{t('itsm.knowledge.emptyBody')}</p>;
  if (format === 'markdown') return <MarkdownRenderer content={content} enableCodeCopy />;
  if (format === 'richtext') return <div className="markdown-body break-words" dangerouslySetInnerHTML={{ __html: sanitizeArticleHtml(content) }} />;
  return <div className="whitespace-pre-wrap break-words">{content}</div>;
}

interface ArticleBodyEditorProps extends ArticleBodyProps {
  disabled: boolean;
  onContentChange: (content: string) => void;
  onFormatChange: (format: ArticleFormat, content: string) => void;
}

export function ArticleBodyEditor({ content, format, disabled, onContentChange, onFormatChange }: ArticleBodyEditorProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const editor = useRef<AiEditor | null>(null);
  const importFile = useRef<HTMLInputElement>(null);
  const importing = useRef<AbortController | null>(null);
  const [preview, setPreview] = useState(false);
  useEffect(() => () => importing.current?.abort(), [format, disabled]);

  const changeFormat = (next: ArticleFormat) => {
    if (next === format) return;
    let converted = content;
    if (next === 'richtext' && content) {
      if (format === 'markdown') converted = markdown.render(content);
      else {
        const text = document.createElement('div');
        text.textContent = content;
        converted = `<p>${text.innerHTML.replace(/\r?\n/g, '<br>')}</p>`;
      }
    } else if (format === 'richtext') {
      if (!editor.current && content) {
        message.warning(t('itsm.knowledge.editorLoading'));
        return;
      }
      converted = editor.current?.isEmpty() ? '' : String(editor.current?.getMarkdown() ?? '');
    }
    setPreview(false);
    onFormatChange(next, converted);
  };

  return <div className="flex flex-col gap-2">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span>{t('itsm.knowledge.body')}</span>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented<ArticleFormat> aria-label={t('itsm.knowledge.bodyFormat')} value={format} disabled={disabled} onChange={changeFormat} options={[
          ...(format === 'text' ? [{ label: t('itsm.knowledge.plainText'), value: 'text' as const }] : []),
          { label: t('itsm.knowledge.richText'), value: 'richtext' }, { label: 'Markdown', value: 'markdown' },
        ]} />
        {format === 'markdown' && <Button size="small" disabled={disabled} icon={<UploadOutlined />}
          onClick={() => importFile.current?.click()}>{t('itsm.knowledge.importMarkdown')}</Button>}
        {format === 'markdown' && <Button size="small" autoInsertSpace={false} onClick={() => setPreview(value => !value)}>
          {preview ? t('itsm.knowledge.continueEditing') : t('itsm.knowledge.preview')}
        </Button>}
      </div>
    </div>
    <input ref={importFile} type="file" accept=".md,.markdown" aria-label={t('itsm.knowledge.markdownFile')} disabled={disabled} hidden tabIndex={-1} onChange={event => {
      const file = event.currentTarget.files?.[0];
      event.currentTarget.value = '';
      if (!file) return;
      importing.current?.abort();
      const request = new AbortController();
      importing.current = request;
      void file.text().then(source => {
        if (request.signal.aborted) return;
        setPreview(false);
        onContentChange(source);
      }).catch(() => { if (!request.signal.aborted) message.error(t('itsm.knowledge.markdownReadFailed')); });
    }} />
    {format === 'richtext' && <RichTextEditor editorRef={editor} value={content} onChange={onContentChange} disabled={disabled} />}
    {format === 'markdown' && preview && <div className="min-h-48 rounded-md border border-[var(--color-border)] p-3">
      <ArticleBody content={content} format={format} />
    </div>}
    {format !== 'richtext' && (format !== 'markdown' || !preview) && <Input.TextArea aria-label={t('itsm.knowledge.body')} value={content}
      disabled={disabled} autoSize={{ minRows: 10, maxRows: 20 }} onChange={event => onContentChange(event.target.value)} />}
  </div>;
}
