import React, { useEffect } from 'react';
import { Empty } from 'antd';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';

interface ComTextProps {
  rawData?: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

// 行内：**粗体** 与 [文本](url) 链接 → React 节点（不使用 innerHTML，无 XSS 面）
const renderInline = (text: string, keyPrefix: string): React.ReactNode[] => {
  const nodes: React.ReactNode[] = [];
  // 先按链接切，再处理粗体
  const linkRe = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  const pushText = (s: string) => {
    // 粗体
    const parts = s.split(/\*\*([^*]+)\*\*/g);
    parts.forEach((p, idx) => {
      if (idx % 2 === 1) {
        nodes.push(<strong key={`${keyPrefix}-b-${i++}`}>{p}</strong>);
      } else if (p) {
        nodes.push(<React.Fragment key={`${keyPrefix}-t-${i++}`}>{p}</React.Fragment>);
      }
    });
  };
  while ((m = linkRe.exec(text)) !== null) {
    if (m.index > last) pushText(text.slice(last, m.index));
    nodes.push(
      <a
        key={`${keyPrefix}-a-${i++}`}
        href={m[2]}
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: 'var(--color-primary, #366ce4)' }}
      >
        {m[1]}
      </a>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) pushText(text.slice(last));
  return nodes;
};

// 轻量 markdown：#/##/### 标题、- 列表、空行、其余为段落
const renderMarkdown = (content: string): React.ReactNode => {
  const lines = content.split('\n');
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flushList = (k: number) => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${k}`} style={{ paddingLeft: 18, margin: '4px 0', listStyle: 'disc' }}>
          {list.map((li, idx) => (
            <li key={idx}>{renderInline(li, `li-${k}-${idx}`)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  lines.forEach((raw, idx) => {
    const line = raw.replace(/\s+$/, '');
    if (/^#{1,3}\s+/.test(line)) {
      flushList(idx);
      const level = line.match(/^#+/)![0].length;
      const txt = line.replace(/^#+\s+/, '');
      const size = level === 1 ? 18 : level === 2 ? 16 : 14;
      blocks.push(
        <div key={`h-${idx}`} style={{ fontSize: size, fontWeight: 600, margin: '6px 0 2px' }}>
          {renderInline(txt, `h-${idx}`)}
        </div>,
      );
    } else if (/^[-*]\s+/.test(line)) {
      list.push(line.replace(/^[-*]\s+/, ''));
    } else if (line.trim() === '') {
      flushList(idx);
    } else {
      flushList(idx);
      blocks.push(
        <p key={`p-${idx}`} style={{ margin: '2px 0' }}>
          {renderInline(line, `p-${idx}`)}
        </p>,
      );
    }
  });
  flushList(lines.length);
  return blocks;
};

/**
 * Text / Markdown 说明面板（对齐 Grafana Text panel）：渲染 config.content 静态内容，
 * 无需数据源。支持轻量 markdown（标题/粗体/列表/链接）。
 */
const ComText: React.FC<ComTextProps> = ({ config, onReady }) => {
  const content = config?.content || '';

  useEffect(() => {
    onReady?.(true);
  }, [onReady]);

  if (!content.trim()) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div
      className="h-full w-full overflow-auto px-3 py-2 text-sm leading-relaxed text-(--color-text-1)"
    >
      {renderMarkdown(content)}
    </div>
  );
};

export default ComText;
