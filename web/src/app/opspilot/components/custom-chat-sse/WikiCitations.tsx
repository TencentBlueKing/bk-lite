'use client';

import React, { useState } from 'react';
import { Drawer, Empty, Spin, Tag, Tooltip } from 'antd';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiCitation } from '@/app/opspilot/types/global';

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });

// 答案中的 [n] 对应的来源:渲染为可点「来源」标签,点击在抽屉中展示对应知识页面/资料内容
const WikiCitations: React.FC<{ citations: WikiCitation[]; content?: string }> = ({ citations, content }) => {
  const { t } = useTranslation();
  const { fetchPage, fetchMaterialInfo } = useWikiApi();
  const [active, setActive] = useState<WikiCitation | null>(null);
  const [loading, setLoading] = useState(false);
  const [body, setBody] = useState('');

  // 只保留答案文本里实际引用的来源:检索是 top-k 召回,LLM 往往只引用其中部分,把未被引用的多余来源过滤掉。
  // 智能体对话按 [n] 标注引用;概览问答助手按标题引用(无 n)。无 content 时兜底全部展示。
  const referenced = (c: WikiCitation) => {
    if (!content) return true;
    return c.n != null ? new RegExp(`\\[\\s*${c.n}\\s*\\]`).test(content) : content.includes(c.title);
  };
  const items = Array.from(new Map(citations.filter(referenced).map((c) => [`${c.kind}:${c.id}`, c])).values()).sort(
    (a, b) => (a.n ?? 0) - (b.n ?? 0)
  );
  const explanationLabels: Record<string, string> = {
    keyword: t('wiki.retrievalKeyword'),
    vector: t('wiki.retrievalVector'),
    chunk_vector: t('wiki.retrievalChunkVector'),
    graph: t('wiki.retrievalGraph'),
  };

  const open = async (c: WikiCitation) => {
    setActive(c);
    setBody('');
    setLoading(true);
    try {
      if (c.kind.includes('material')) {
        const info = await fetchMaterialInfo(c.id);
        setBody(info.original || info.ai_summary || '');
      } else {
        const page = await fetchPage(c.id);
        setBody(page.body || '');
      }
    } catch {
      setBody(t('wiki.qaError'));
    } finally {
      setLoading(false);
    }
  };

  if (!items.length) return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-[var(--color-border-2)] pt-2">
      <span className="text-xs text-[var(--color-text-3)]">{t('wiki.citations')}:</span>
      {items.map((c) => (
        <span key={`${c.kind}:${c.id}`} className="flex max-w-full items-center gap-1">
          <Tooltip title={c.title}>
            <Tag color="processing" className="m-0 max-w-[220px] cursor-pointer truncate hover:opacity-80" onClick={() => open(c)}>
              {c.n != null ? `[${c.n}] ` : ''}
              {c.title}
            </Tag>
          </Tooltip>
          {c.explanation?.matched_by?.map((mode) => (
            <Tag key={mode} className="m-0 text-[11px]">
              {explanationLabels[mode] || mode}
            </Tag>
          ))}
        </span>
      ))}
      <Drawer title={active?.title} open={!!active} width={600} onClose={() => setActive(null)} destroyOnHidden>
        <Spin spinning={loading}>
          {body ? (
            <div
              className="text-sm leading-7 break-words [&_h1]:text-base [&_h2]:text-[15px] [&_h3]:text-sm [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[var(--color-fill-1)] [&_code]:px-1"
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(md.render(body)) }}
            />
          ) : (
            !loading && <Empty />
          )}
        </Spin>
      </Drawer>
    </div>
  );
};

export default WikiCitations;
