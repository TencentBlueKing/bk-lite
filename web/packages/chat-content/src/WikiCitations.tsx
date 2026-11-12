'use client';

import React, { useState } from 'react';
import { Drawer, Empty, Spin, Tag, Tooltip } from 'antd';
import { ChatMarkdown } from './Markdown';
import { useTranslation } from './host';
import { useChatContentHost } from './host';
import { WikiCitation } from './types';



// 知识引用:答案中的 [n] 对应的资料/页面来源。点击 [n] 或资料名在抽屉中展示
// 实际引用的内容。
const WikiCitations: React.FC<{ citations: WikiCitation[]; content?: string }> = ({ citations, content }) => {
  const { t } = useTranslation();
  const { loadCitation } = useChatContentHost();
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

  const open = async (c: WikiCitation) => {
    setActive(c);
    setBody('');
    setLoading(true);
    try {
      if (!loadCitation) throw new Error('Citation loader unavailable');
      setBody(await loadCitation(c));
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
        <Tooltip key={`${c.kind}:${c.id}`} title={c.title}>
          <Tag
            color="processing"
            className="m-0 max-w-[280px] cursor-pointer truncate hover:opacity-80"
            onClick={() => open(c)}
          >
            {c.n != null && <span className="mr-1 font-semibold">[{c.n}]</span>}
            {c.title}
          </Tag>
        </Tooltip>
      ))}
      <Drawer title={active?.title} open={!!active} width="min(600px, 100vw)" onClose={() => setActive(null)} destroyOnHidden>
        <Spin spinning={loading}>
          {body ? (
            <ChatMarkdown content={body} />
          ) : (
            !loading && <Empty />
          )}
        </Spin>
      </Drawer>
    </div>
  );
};

export default WikiCitations;