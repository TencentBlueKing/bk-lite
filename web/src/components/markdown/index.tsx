'use client';

import React, { useEffect, useState } from 'react';
import { Spin, message } from 'antd';
import { remark } from 'remark';
import html from 'remark-html';
import gfm from 'remark-gfm';
import 'github-markdown-css/github-markdown.css';
import styles from './index.module.scss';
import { getClientIdFromRoute } from '@/utils/route';

interface MarkdownRendererProps {
  filePath?: string;
  fileName?: string;
  content?: string;
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  filePath,
  fileName,
  content: externalContent,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [content, setContent] = useState<string>('');

  const locale = typeof window !== 'undefined' && localStorage.getItem('locale');

  const processMarkdown = async () => {
    try {
      setLoading(true);
      if (externalContent) {
        const processedContent = await remark()
          .use(gfm)
          .use(html)
          .process(externalContent);
        setContent(processedContent.toString());
      } else {
        setContent('');
      }
    } catch (error) {
      message.error('Failed to process markdown content.');
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
      const processedContent = await remark()
        .use(gfm)
        .use(html)
        .process(data.content);
      setContent(processedContent.toString());
    } catch (error) {
      message.error('Failed to load markdown content.');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (externalContent !== undefined) {
      processMarkdown();
      return;
    }

    if (!filePath || !fileName) {
      setLoading(false);
      return;
    }

    fetchMarkdown();
  }, [filePath, fileName, externalContent]);

  return (
    <Spin spinning={loading}>
      <div className={`markdown-body ${styles.markdown}`} dangerouslySetInnerHTML={{ __html: content }} />
    </Spin>
  );
};

export default MarkdownRenderer;
