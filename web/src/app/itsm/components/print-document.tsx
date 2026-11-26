'use client';

import DOMPurify from 'dompurify';
import { useMemo, type Ref } from 'react';
import { useIntl } from 'react-intl';

const FRAME_LAYOUT = 'mx-auto h-[70vh] min-h-[300px] w-full max-w-5xl overflow-hidden rounded border border-[var(--color-border)]';

const DOCUMENT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none'; base-uri 'none'";
const DOCUMENT_STYLE = `
  body { margin: 24px; color: #1f2329; font: 14px/1.5 system-ui, sans-serif; overflow-wrap: anywhere; }
  table { border-collapse: collapse; max-width: 100%; }
  img { max-width: 100%; }
  .itsm-print-fields { width: 100%; margin: 0 0 24px; table-layout: fixed; }
  .itsm-print-fields :is(th, td) { padding: 8px 12px; border: 1px solid #dce0e5; text-align: start; vertical-align: top; }
  .itsm-print-fields th { width: 28%; font-weight: 600; }
  .itsm-print-fields td { white-space: pre-wrap; }
  .itsm-print-fields tr { break-inside: avoid; }
`;

export function PrintDocument({ html, title, frameRef, onLoad }: {
  html: string;
  title: string;
  frameRef?: Ref<HTMLIFrameElement>;
  onLoad?: () => void;
}) {
  const language = useIntl().locale.split('-')[0] === 'zh' ? 'zh-CN' : 'en';
  const source = useMemo(() => {
    // 解析阶段也要隔离，避免清理前加载模板引用的资源。
    const inertDocument = document.createElement('template').content.ownerDocument;
    const fragment = inertDocument.createElement('div');
    fragment.innerHTML = html;
    DOMPurify.sanitize(fragment, {
      IN_PLACE: true,
      USE_PROFILES: { html: true },
      FORBID_TAGS: ['a', 'audio', 'base', 'button', 'embed', 'form', 'frame', 'iframe', 'input', 'link', 'meta', 'object', 'script', 'video'],
      FORBID_ATTR: ['srcset', 'action', 'formaction', 'ping', 'target', 'download'],
      ALLOWED_URI_REGEXP: /^data:image\/(?:png|jpeg|gif|webp);base64,[a-z0-9+/=]+$/i,
    });
    const documentTitle = inertDocument.createElement('title');
    documentTitle.textContent = title;
    return `<!doctype html><html lang="${language}"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${DOCUMENT_CSP}">${documentTitle.outerHTML}<style>${DOCUMENT_STYLE}</style></head><body>${fragment.innerHTML}</body></html>`;
  }, [html, language, title]);

  return <div className={FRAME_LAYOUT}>
    <iframe ref={frameRef} title={title} className="block h-full w-full bg-white"
      sandbox="allow-same-origin allow-modals" referrerPolicy="no-referrer" srcDoc={source} onLoad={onLoad} />
  </div>;
}

export function PrintDocumentSkeleton({ label }: { label: string }) {
  return <div className={`${FRAME_LAYOUT} space-y-6 p-6`} role="status" aria-label={label} aria-busy="true">
    <div aria-hidden="true" className="h-8 w-1/3 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
    {[4, 6].map(rows => <div key={rows} aria-hidden="true" className="divide-y divide-[var(--color-border)] rounded border border-[var(--color-border)]">
      {Array.from({ length: rows }, (_, row) => <div key={row} className="grid grid-cols-[28%_1fr] divide-x divide-[var(--color-border)]">
        <div className="p-3"><div className="h-3 w-3/4 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" /></div>
        <div className="p-3"><div className="h-3 w-1/2 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" /></div>
      </div>)}
    </div>)}
  </div>;
}
