'use client';

import { CodeOutlined, CoffeeOutlined } from '@ant-design/icons';
import { Tag, Tooltip } from 'antd';

const LANGUAGE_LABELS: Record<string, string> = {
  cpp: 'C++',
  csharp: '.NET',
  dotnet: '.NET',
  go: 'Go',
  java: 'Java',
  javascript: 'JS',
  nodejs: 'Node.js',
  php: 'PHP',
  python: 'Python',
  ruby: 'Ruby',
  rust: 'Rust',
};

export default function ServiceLanguage({ language }: { language?: string }) {
  const normalized = language?.trim().toLowerCase() ?? '';
  const label = LANGUAGE_LABELS[normalized] ?? (language?.trim() || '未知');
  const icon = normalized === 'java'
    ? <CoffeeOutlined aria-hidden="true" />
    : <CodeOutlined aria-hidden="true" />;
  return (
    <Tooltip title={normalized ? `OpenTelemetry SDK 语言：${label}` : '暂未观测到 SDK 语言'}>
      <Tag bordered={false} className="!m-0 inline-flex items-center gap-1 !text-xs" icon={icon}>
        {label}
      </Tag>
    </Tooltip>
  );
}
