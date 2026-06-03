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
    <div className="mt-3 rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm max-w-[700px]">
      {/* Header */}
      <div
        className="px-4 py-2 bg-gradient-to-r from-green-50 to-white border-b border-gray-200 flex items-center gap-2 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <CodeOutlined className="text-green-600 text-base" />
        <span className="font-semibold text-sm text-gray-800">修复命令</span>
        <span className="text-xs text-gray-500 ml-1">（{sections.length} 组）</span>
        <div className="ml-auto flex items-center gap-2">
          <Button
            size="small"
            type="text"
            icon={<CopyOutlined />}
            onClick={(e) => { e.stopPropagation(); handleCopyAll(); }}
            className="!text-xs"
          >
            全部复制
          </Button>
          {expanded ? <UpOutlined className="text-xs text-gray-400" /> : <DownOutlined className="text-xs text-gray-400" />}
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div className="px-4 py-3 space-y-3 max-h-[400px] overflow-y-auto">
          {sections.map((section, idx) => (
            <div key={idx}>
              {section.title && (
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-gray-600">{section.title}</span>
                  <Button
                    size="small"
                    type="link"
                    icon={<CopyOutlined />}
                    onClick={() => handleCopySection(section.code)}
                    className="!text-xs !p-0"
                  />
                </div>
              )}
              <pre className="bg-gray-900 text-green-300 text-xs p-3 rounded overflow-x-auto whitespace-pre-wrap break-all">
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
