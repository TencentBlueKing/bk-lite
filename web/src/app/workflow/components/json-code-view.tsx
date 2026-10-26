'use client';

import CodeEditor from '@/components/code-editor';

function serialize(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function JsonCodeView({
  value,
  label,
  height = '100%',
}: {
  value: unknown;
  label: string;
  height?: string;
}) {
  return (
    <CodeEditor
      appearance="token"
      aria-label={label}
      className="h-full min-h-0 w-full max-w-full overflow-hidden rounded-md border border-[var(--color-border-1)]"
      headerOptions={{ copy: true, fullscreen: true }}
      height={height}
      mode="json"
      readOnly
      setOptions={{ showPrintMargin: false, useWorker: false, tabSize: 2, fontSize: 12 }}
      theme="textmate"
      value={serialize(value)}
      width="100%"
    />
  );
}
