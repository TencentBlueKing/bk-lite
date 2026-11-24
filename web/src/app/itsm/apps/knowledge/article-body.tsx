'use client';

import { App, Button, Input, Segmented, Skeleton } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import type { AiEditor } from 'aieditor';
import MarkdownIt from 'markdown-it';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState } from 'react';
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
  if (!content.trim()) return <p className="text-sm text-[var(--color-text-3)]">暂无正文</p>;
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
        message.warning('请等待富文本编辑器加载');
        return;
      }
      converted = editor.current?.isEmpty() ? '' : String(editor.current?.getMarkdown() ?? '');
    }
    setPreview(false);
    onFormatChange(next, converted);
  };

  return <div className="flex flex-col gap-2">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span>正文</span>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented<ArticleFormat> aria-label="正文格式" value={format} disabled={disabled} onChange={changeFormat} options={[
          ...(format === 'text' ? [{ label: '纯文本', value: 'text' as const }] : []),
          { label: '富文本', value: 'richtext' }, { label: 'Markdown', value: 'markdown' },
        ]} />
        {format === 'markdown' && <Button size="small" disabled={disabled} icon={<UploadOutlined />}
          onClick={() => importFile.current?.click()}>导入 Markdown</Button>}
        {format === 'markdown' && <Button size="small" autoInsertSpace={false} onClick={() => setPreview(value => !value)}>
          {preview ? '继续编辑' : '预览'}
        </Button>}
      </div>
    </div>
    <input ref={importFile} type="file" accept=".md,.markdown" aria-label="Markdown 文件" disabled={disabled} hidden tabIndex={-1} onChange={event => {
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
      }).catch(() => { if (!request.signal.aborted) message.error('读取 Markdown 文件失败'); });
    }} />
    {format === 'richtext' && <RichTextEditor editorRef={editor} value={content} onChange={onContentChange} disabled={disabled} />}
    {format === 'markdown' && preview && <div className="min-h-48 rounded-md border border-[var(--color-border)] p-3">
      <ArticleBody content={content} format={format} />
    </div>}
    {format !== 'richtext' && (format !== 'markdown' || !preview) && <Input.TextArea aria-label="正文" value={content}
      disabled={disabled} autoSize={{ minRows: 10, maxRows: 20 }} onChange={event => onContentChange(event.target.value)} />}
  </div>;
}
