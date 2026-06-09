'use client';

import React, { useMemo, useState } from 'react';
import { Button, message } from 'antd';
import { CopyOutlined, DownOutlined, UpOutlined, CodeOutlined } from '@ant-design/icons';
import { RepairCommands } from '@/app/opspilot/types/global';

interface RepairCommandsCardProps {
  commands: RepairCommands;
}

const RepairCommandsCard: React.FC<RepairCommandsCardProps> = ({ commands }) => {
  const [expanded, setExpanded] = useState(true);

  // Parse markdown: extract code blocks and titles
  const sections = useMemo(() => {
    const parts: Array<{ title: string; code: string }> = [];
    const lines = commands.commands_markdown.split('\n');
    let currentTitle = '';
    let currentCode = '';
    let inCode = false;

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('```')) {
        if (inCode) {
          parts.push({ title: currentTitle, code: currentCode.trim() });
          currentCode = '';
          currentTitle = '';
        }
        inCode = !inCode;
      } else if (inCode) {
        currentCode += line + '\n';
      } else if (trimmed.startsWith('**')) {
        currentTitle = trimmed.replace(/\*\*/g, '');
      }
    }
    return parts;
  }, [commands.commands_markdown]);

  const allCode = sections.map(s => s.code).join('\n\n');

  const handleCopyAll = () => {
    navigator.clipboard.writeText(allCode).then(() => {
      message.success('已复制所有修复命令');
    });
  };

  const handleCopySection = (code: string) => {
    navigator.clipboard.writeText(code).then(() => {
      message.success('已复制');
    });
  };

  return (
    <div className="mt-3 max-w-[700px] overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-sm">
      {/* Header */}
      <div
        className="flex cursor-pointer items-center gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-4 py-2"
        onClick={() => setExpanded(!expanded)}
      >
        <CodeOutlined className="text-base text-[var(--color-success)]" />
        <span className="text-sm font-semibold text-[var(--color-text-1)]">修复命令</span>
        <span className="ml-1 text-xs text-[var(--color-text-3)]">（{sections.length} 组）</span>
        <div className="ml-auto flex items-center gap-2">
          <Button
            size="small"
            type="text"
            icon={<CopyOutlined />}
            onClick={(e) => { e.stopPropagation(); handleCopyAll(); }}
            className="!text-xs !text-[var(--color-text-2)] hover:!text-[var(--color-primary)]"
          >
            全部复制
          </Button>
          {expanded ? <UpOutlined className="text-xs text-[var(--color-text-4)]" /> : <DownOutlined className="text-xs text-[var(--color-text-4)]" />}
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div className="max-h-[400px] space-y-3 overflow-y-auto px-4 py-3">
          {sections.map((section, idx) => (
            <div key={idx}>
              {section.title && (
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-medium text-[var(--color-text-2)]">{section.title}</span>
                  <Button
                    size="small"
                    type="link"
                    icon={<CopyOutlined />}
                    onClick={() => handleCopySection(section.code)}
                    className="!p-0 !text-xs !text-[var(--color-primary)]"
                  />
                </div>
              )}
              <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3 font-mono text-xs leading-5 text-[var(--color-text-1)]">
                {section.code}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RepairCommandsCard;
