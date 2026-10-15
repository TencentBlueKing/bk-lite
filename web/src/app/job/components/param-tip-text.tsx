'use client';

import React from 'react';

const URL_RE = /(https?:\/\/[^\s]+)/g;

interface ParamTipTextProps {
  text: string;
  className?: string;
}

/** 将提示信息中的 http(s) URL 渲染为可点击链接（新窗口打开）。 */
const ParamTipText: React.FC<ParamTipTextProps> = ({ text, className }) => {
  const parts = text.split(URL_RE);
  if (parts.length === 1) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span className={className}>
      {parts.map((part, index) => {
        if (/^https?:\/\//.test(part)) {
          return (
            <a
              key={`${part}-${index}`}
              href={part}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-primary)] hover:underline break-all"
              onClick={(e) => e.stopPropagation()}
            >
              {part}
            </a>
          );
        }
        return <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>;
      })}
    </span>
  );
};

export default ParamTipText;
