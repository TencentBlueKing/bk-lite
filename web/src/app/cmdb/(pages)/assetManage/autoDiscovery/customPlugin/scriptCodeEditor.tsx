'use client';

import React from 'react';
import ReactAce from 'react-ace';
import { Segmented } from 'antd';
import 'ace-builds/src-noconflict/mode-sh';
import 'ace-builds/src-noconflict/mode-powershell';
import 'ace-builds/src-noconflict/mode-batchfile';
import 'ace-builds/src-noconflict/theme-monokai';

const SCRIPT_MODE: Record<string, string> = {
  bash: 'sh',
  sh: 'sh',
  powershell: 'powershell',
  bat: 'batchfile',
};

export function ShellSwitch({
  osType,
  value,
  onChange,
}: {
  osType: string;
  value: string;
  onChange: (shell: string) => void;
}) {
  const windows = osType === 'windows';
  return (
    <Segmented
      value={value}
      onChange={(next) => onChange(String(next))}
      options={[
        { label: 'bash', value: 'bash', disabled: windows },
        { label: 'sh', value: 'sh', disabled: windows },
        { label: 'powershell', value: 'powershell', disabled: !windows },
        { label: 'bat', value: 'bat', disabled: !windows },
      ]}
    />
  );
}

export default function ScriptCodeEditor({
  value,
  onChange,
  shell,
}: {
  value?: string;
  onChange?: (value: string) => void;
  shell: string;
}) {
  return (
    <div className="overflow-hidden rounded-md border border-[var(--color-border-1)]">
      <ReactAce
        mode={SCRIPT_MODE[shell] || 'sh'}
        theme="monokai"
        width="100%"
        height="280px"
        value={value || ''}
        onChange={onChange}
        setOptions={{
          showPrintMargin: false,
          tabSize: 2,
          fontSize: 14,
          useWorker: false,
        }}
        editorProps={{ $blockScrolling: true }}
      />
    </div>
  );
}
