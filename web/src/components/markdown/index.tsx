'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Spin, message } from 'antd';
import DOMPurify from 'dompurify';
import { remark } from 'remark';
import html from 'remark-html';
import gfm from 'remark-gfm';
import 'github-markdown-css/github-markdown.css';
import styles from './index.module.scss';
import { stripLeadingH1 } from './sectionMarkdown';
import { getClientIdFromRoute } from '@/utils/route';
import { useTranslation } from '@/utils/i18n';

interface MarkdownRendererProps {
  filePath?: string;
  fileName?: string;
  content?: string;
  /** 去掉文首 H1，避免与外层抽屉标题重复（监控指南场景）。 */
  stripDocumentTitle?: boolean;
  enableCodeCopy?: boolean;
}

const COPY_ICON_SVG =
  '<svg viewBox="64 64 896 896" focusable="false" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M832 64H296c-4.4 0-8 3.6-8 8v56c0 4.4 3.6 8 8 8h496v688c0 4.4 3.6 8 8 8h56c4.4 0 8-3.6 8-8V96c0-17.7-14.3-32-32-32z"></path><path d="M704 192H192c-17.7 0-32 14.3-32 32v530.7c0 8.5 3.4 16.6 9.4 22.6l173.3 173.3c2.2 2.2 4.7 4 7.4 5.5v-79.1c0-4.4 3.6-8 8-8h79.1c13.5 0 26.4-5.4 36-14.9l173.3-173.3c6-6 9.4-14.1 9.4-22.6V224c0-17.7-14.3-32-32-32zM350 856.2L263.9 770H350v86.2zM664 666.7L505.3 826.3c-2.9 2.9-6.4 5-10.2 6.3V744c0-22.1-17.9-40-40-40H295.3c-4.4 0-8-3.6-8-8V302c0-4.4 3.6-8 8-8h360.7c4.4 0 8 3.6 8 8v364.7z"></path></svg>';

const CHECK_ICON_SVG =
  '<svg viewBox="64 64 896 896" focusable="false" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M912 190h-69.9c-9.8 0-19.1 4.5-25.1 12.2L404.7 724.5 207 474a32 32 0 00-25.1-12.2H112c-6.7 0-10.4 7.7-6.3 12.9l273.9 347c12.8 16.2 37.4 16.2 50.3 0l488.4-618.9c4.1-5.1.4-12.8-6.3-12.8z"></path></svg>';

const sanitizeMarkdownHtml = (unsafeHtml: string): string => (
  DOMPurify.sanitize(unsafeHtml, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'code', 'pre', 'span', 'div', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'hr', 'del', 'ins', 'sup', 'sub'],
    ALLOWED_ATTR: ['class', 'href', 'target', 'rel', 'src', 'alt', 'width', 'height', 'id'],
    ALLOW_DATA_ATTR: false
  })
);

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  filePath,
  fileName,
  content: externalContent,
  stripDocumentTitle = false,
  enableCodeCopy = false
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState<boolean>(true);
  const [content, setContent] = useState<string>('');
  const hostRef = useRef<HTMLDivElement>(null);

  const locale = typeof window !== 'undefined' && localStorage.getItem('locale');

  const processedContent = useMemo(() => {
    if (!externalContent) {
      return '';
    }
    if (!stripDocumentTitle) {
      return externalContent;
    }
    return stripLeadingH1(externalContent);
  }, [externalContent, stripDocumentTitle]);

  const processMarkdown = async () => {
    try {
      setLoading(true);
      if (processedContent) {
        const processedContentResult = await remark()
          .use(gfm)
          .use(html)
          .process(processedContent);
        let htmlString = sanitizeMarkdownHtml(processedContentResult.toString());
        // 二次兜底：消毒后若仍残留 H1，一律去掉。
        if (stripDocumentTitle) {
          htmlString = htmlString.replace(/<h1\b[^>]*>[\s\S]*?<\/h1>\s*/gi, '');
        }
        setContent(htmlString);
      } else {
        setContent('');
      }
    } catch (error) {
      message.error(t('common.markdownProcessFailed'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchMarkdown = async () => {
    if (!filePath || !fileName) return;

    try {
      let requestUrl: string;

      if (filePath === 'versions') {
        const clientId = getClientIdFromRoute();
        requestUrl = `/api/markdown?filePath=${filePath}/${clientId}/${locale === 'en' ? 'en' : 'zh'}/${fileName}.md`;
      } else {
        requestUrl = `/api/markdown?filePath=${filePath}${filePath.endsWith('/') ? '' : '/'}${locale === 'en' ? 'en' : 'zh'}/${fileName}.md`;
      }

      const response = await fetch(requestUrl);
      if (!response.ok) {
        throw new Error('Network response was not ok');
      }
      const data = await response.json();
      const processed = await remark()
        .use(gfm)
        .use(html)
        .process(data.content);
      setContent(sanitizeMarkdownHtml(processed.toString()));
    } catch (error) {
      message.error(t('common.markdownLoadFailed'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (processedContent !== undefined && processedContent !== '') {
      processMarkdown();
      return;
    }

    if (!filePath || !fileName) {
      setLoading(false);
      return;
    }

    fetchMarkdown();
  }, [processedContent, filePath, fileName]);

  // 在 dangerouslySetInnerHTML 渲染后为代码块挂载复制按钮（事件委托）。
  useEffect(() => {
    if (!enableCodeCopy || !content || !hostRef.current) {
      return;
    }
    const root = hostRef.current;
    const copyLabel = t('common.copy');
    const copiedLabel = t('common.copySuccess');

    root.querySelectorAll('pre').forEach((pre) => {
      if (pre.parentElement?.classList.contains('md-code-block')) {
        return;
      }
      const wrapper = document.createElement('div');
      wrapper.className = 'md-code-block';
      pre.parentNode?.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'md-code-copy';
      btn.setAttribute('aria-label', copyLabel);
      btn.title = copyLabel;
      btn.innerHTML = COPY_ICON_SVG;
      wrapper.appendChild(btn);
    });

    const onClick = async (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const btn = target?.closest('.md-code-copy') as HTMLButtonElement | null;
      if (!btn || !root.contains(btn)) {
        return;
      }
      event.preventDefault();
      const pre = btn.parentElement?.querySelector('pre');
      const text = pre?.textContent || '';
      if (!text) {
        return;
      }
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          const textarea = document.createElement('textarea');
          textarea.value = text;
          textarea.setAttribute('readonly', '');
          textarea.style.position = 'fixed';
          textarea.style.left = '-9999px';
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand('copy');
          document.body.removeChild(textarea);
        }
        btn.classList.add('is-copied');
        btn.setAttribute('aria-label', copiedLabel);
        btn.title = copiedLabel;
        btn.innerHTML = CHECK_ICON_SVG;
        message.success(copiedLabel);
        window.setTimeout(() => {
          if (!btn.isConnected) {
            return;
          }
          btn.classList.remove('is-copied');
          btn.setAttribute('aria-label', copyLabel);
          btn.title = copyLabel;
          btn.innerHTML = COPY_ICON_SVG;
        }, 1500);
      } catch (error) {
        console.error(error);
        message.error(t('common.copyFailed'));
      }
    };

    root.addEventListener('click', onClick);
    return () => {
      root.removeEventListener('click', onClick);
    };
  }, [enableCodeCopy, content, t]);

  return (
    <Spin spinning={loading}>
      <div
        ref={hostRef}
        className={`markdown-body ${styles.markdown}`}
        dangerouslySetInnerHTML={{ __html: content }}
      />
    </Spin>
  );
};

export default MarkdownRenderer;
