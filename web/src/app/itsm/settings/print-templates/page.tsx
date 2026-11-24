'use client';

import { Alert, Button, Spin } from 'antd';
import { useEffect, useState } from 'react';
import { useItsmApi } from '../../api/useItsmApi';
import { PrintDocument } from '../../components/print-document';

type PrintPreviewState =
  | { status: 'loading' }
  | { status: 'ready'; html: string }
  | { status: 'error'; message: string };

export default function PrintPreviewPage() {
  const { ready, previewPrintTemplate } = useItsmApi();
  const [preview, setPreview] = useState<PrintPreviewState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!ready) return;
    let current = true;
    setPreview({ status: 'loading' });
    void previewPrintTemplate().then(({ html }) => {
      if (current) setPreview({ status: 'ready', html });
    }).catch(error => {
      if (current) setPreview({ status: 'error', message: error instanceof Error ? error.message : '无法加载打印样例' });
    });
    return () => { current = false; };
  }, [attempt, previewPrintTemplate, ready]);

  return <section className="mx-auto flex w-full flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <header className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] pb-3">
      <h1 className="text-base font-semibold">打印预览</h1>
      <p className="text-sm text-[var(--color-text-2)]">此处使用示例数据，打印时填入工单的实际字段值。</p>
    </header>
    {preview.status === 'loading' && <div className="flex justify-center py-12" role="status" aria-label="正在加载打印预览"><Spin /></div>}
    {preview.status === 'error' && <Alert type="error" message={preview.message}
      action={<Button onClick={() => setAttempt(value => value + 1)}>重试</Button>} />}
    {preview.status === 'ready' && <PrintDocument title="打印样例预览" html={preview.html} />}
  </section>;
}
