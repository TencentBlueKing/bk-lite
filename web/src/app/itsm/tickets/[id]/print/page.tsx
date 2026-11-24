'use client';

import { PrinterOutlined } from '@ant-design/icons';
import { Alert, Button, Spin } from 'antd';
import { useParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { useItsmApi } from '../../../api/useItsmApi';
import { ItsmBackButton } from '../../../components/back-button';
import { PrintDocument } from '../../../components/print-document';

type TicketPrintState =
  | { status: 'loading' }
  | { status: 'ready'; html: string }
  | { status: 'error'; message: string };

export default function Page() {
  const id = Number(useParams<{ id: string }>().id);
  const { getTicketPrint, ready } = useItsmApi();
  const frame = useRef<HTMLIFrameElement>(null);
  const [preview, setPreview] = useState<TicketPrintState>({ status: 'loading' });
  const [canPrint, setCanPrint] = useState(false);

  useEffect(() => {
    if (!ready) return;
    let current = true;
    setPreview({ status: 'loading' });
    setCanPrint(false);
    void getTicketPrint(id).then(({ html }) => {
      if (current) setPreview({ status: 'ready', html });
    }).catch(error => {
      if (current) setPreview({ status: 'error', message: error instanceof Error ? error.message : '无法加载打印内容' });
    });
    return () => { current = false; };
  }, [getTicketPrint, id, ready]);

  return <section className="mx-auto flex w-full flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <header className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] pb-3">
      <ItsmBackButton label="返回工单详情" href={`/itsm/tickets/${id}`} />
      <h1 className="text-base font-semibold">打印工单</h1>
      <Button type="primary" icon={<PrinterOutlined />} className="ml-auto" disabled={preview.status !== 'ready' || !canPrint}
        onClick={() => frame.current?.contentWindow?.print()}>打印</Button>
    </header>
    {preview.status === 'error' && <Alert type="error" message={preview.message} />}
    {preview.status === 'loading' && <div className="flex justify-center py-12" role="status" aria-label="正在加载打印预览"><Spin /></div>}
    {preview.status === 'ready' && <PrintDocument title="工单打印预览" html={preview.html} frameRef={frame} onLoad={() => setCanPrint(true)} />}
  </section>;
}
