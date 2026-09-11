import { toCanvas } from 'html-to-image';
import jsPDF from 'jspdf';
import type { OpenAPIFieldSpec } from '@/app/system-manager/api/settings';
import {
  fieldHasRange,
  formatChoices,
  formatFieldRange,
  generateCurlCommand,
  type OpenAPIDocRow,
} from '@/app/system-manager/utils/openapiDocs';

export interface OpenApiDocsPdfLabels {
  title: string;
  catalog: string;
  generatedAt: string;
  totalCount: string;
  kind: string;
  authHeader: string;
  authHeaderDesc: string;
  internal: string;
  external: string;
  service: string;
  method: string;
  path: string;
  summary: string;
  fieldName: string;
  fieldType: string;
  required: string;
  range: string;
  default: string;
  choices: string;
  yes: string;
  no: string;
  noParams: string;
  entryPrefix: string;
  docUrl: string;
  noDocUrl: string;
  externalDocHint: string;
  permissionControl: string;
  unrestricted: string;
  orgScope: string;
  tabExample: string;
  inject: (value: string) => string;
}

const PAGE_HEIGHT = 297;
const PAGE_MARGIN = 12;
const CONTENT_WIDTH = 210 - PAGE_MARGIN * 2;
const EXPORT_WIDTH_PX = 720;
const PIXEL_RATIO = 2.5;
const PNG_COMPRESSION = 'FAST';
const CUT_EPSILON = 0.5;
export const CATALOG_INDEX_CHUNK = 20;
const LINE_STRIDE_PX = 24;

const escapeHtml = (value: unknown): string =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const fieldHasDefault = (spec: OpenAPIFieldSpec): boolean =>
  spec.default !== undefined && spec.default !== null;

const fieldHasChoices = (spec: OpenAPIFieldSpec): boolean => {
  const text = formatChoices(spec.choices);
  return Boolean(text);
};

const kindLabel = (row: OpenAPIDocRow, labels: OpenApiDocsPdfLabels): string =>
  row.kind === 'external' ? labels.external : labels.internal;

const methodLabel = (row: OpenAPIDocRow): string =>
  row.kind === 'external' ? 'EXT' : row.method.toUpperCase() || '--';

const schemaEntries = (row: OpenAPIDocRow): Array<[string, OpenAPIFieldSpec]> =>
  Object.entries(row.requestSchema || {});

const renderSchemaTable = (row: OpenAPIDocRow, labels: OpenApiDocsPdfLabels): string => {
  const entries = schemaEntries(row);
  if (!entries.length) {
    return `<p class="hint">${escapeHtml(labels.noParams)}</p>`;
  }

  const showDefault = entries.some(([, spec]) => fieldHasDefault(spec));
  const showChoices = entries.some(([, spec]) => fieldHasChoices(spec));
  const showRange = entries.some(([, spec]) => fieldHasRange(spec));

  const head = [
    `<th>${escapeHtml(labels.fieldName)}</th>`,
    `<th>${escapeHtml(labels.fieldType)}</th>`,
    `<th>${escapeHtml(labels.required)}</th>`,
    showRange ? `<th>${escapeHtml(labels.range)}</th>` : '',
    showDefault ? `<th>${escapeHtml(labels.default)}</th>` : '',
    showChoices ? `<th>${escapeHtml(labels.choices)}</th>` : '',
  ].join('');

  const body = entries
    .map(([name, spec]) => {
      const cells = [
        `<td><code>${escapeHtml(name)}</code></td>`,
        `<td>${escapeHtml(spec.type || '--')}</td>`,
        `<td>${escapeHtml(spec.required ? labels.yes : labels.no)}</td>`,
        showRange
          ? `<td>${escapeHtml(formatFieldRange(spec.min_value, spec.max_value) || '--')}</td>`
          : '',
        showDefault
          ? `<td>${escapeHtml(fieldHasDefault(spec) ? spec.default : '--')}</td>`
          : '',
        showChoices
          ? `<td>${escapeHtml(formatChoices(spec.choices) || '--')}</td>`
          : '',
      ];
      return `<tr>${cells.join('')}</tr>`;
    })
    .join('');

  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
};

const renderPre = (value: string): string => {
  const lines = String(value ?? '').split('\n');
  return `<pre>${lines
    .map((line) => `<span data-pdf-line>${escapeHtml(line || ' ')}</span>`)
    .join('')}</pre>`;
};

const chunkItems = <T,>(items: T[], size: number): T[][] => {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks.length ? chunks : [[]];
};

const catalogTableHead = (labels: OpenApiDocsPdfLabels): string => `
  <thead>
    <tr>
      <th>${escapeHtml(labels.method)}</th>
      <th>${escapeHtml(labels.path)}</th>
      <th>${escapeHtml(labels.service)}</th>
      <th>${escapeHtml(labels.kind)}</th>
      <th>${escapeHtml(labels.summary)}</th>
    </tr>
  </thead>
`;

const renderCatalogIndex = (rows: OpenAPIDocRow[], labels: OpenApiDocsPdfLabels): string =>
  chunkItems(rows, CATALOG_INDEX_CHUNK)
    .map((chunk, index) => {
      const body = chunk
        .map(
          (row) => `
            <tr>
              <td>${escapeHtml(methodLabel(row))}</td>
              <td><code>${escapeHtml(row.path)}</code></td>
              <td>${escapeHtml(row.service)}</td>
              <td>${escapeHtml(kindLabel(row, labels))}</td>
              <td>${escapeHtml(row.summary || '--')}</td>
            </tr>
          `
        )
        .join('');
      return `
        <section data-pdf-block>
          ${index === 0 ? `<h2>${escapeHtml(labels.catalog)}</h2>` : ''}
          <table>
            ${catalogTableHead(labels)}
            <tbody>${body}</tbody>
          </table>
        </section>
      `;
    })
    .join('');

const renderEndpointBlock = (row: OpenAPIDocRow, labels: OpenApiDocsPdfLabels): string => {
  const heading = `${methodLabel(row)}  ${row.path}`;
  if (row.kind === 'external') {
    return `
      <section data-pdf-block>
        <h2>${escapeHtml(heading)}</h2>
        <p class="meta">${escapeHtml(labels.service)}：${escapeHtml(row.service)} · ${escapeHtml(kindLabel(row, labels))}</p>
        <p class="hint">${escapeHtml(labels.externalDocHint)}</p>
        <p><strong>${escapeHtml(labels.entryPrefix)}</strong></p>
        ${renderPre(row.path)}
        <p><strong>${escapeHtml(labels.docUrl)}</strong></p>
        ${renderPre(row.docUrl || labels.noDocUrl)}
      </section>
    `;
  }

  const curl = generateCurlCommand(row);
  const permission = row.permission || labels.unrestricted;
  const inject = row.inject ? labels.inject(row.inject) : '--';

  return `
    <section data-pdf-block>
      <h2>${escapeHtml(heading)}</h2>
      <p class="meta">${escapeHtml(labels.service)}：${escapeHtml(row.service)} · ${escapeHtml(kindLabel(row, labels))}</p>
      ${row.summary ? `<p>${escapeHtml(row.summary)}</p>` : ''}
      ${renderSchemaTable(row, labels)}
      <p><strong>${escapeHtml(labels.tabExample)}</strong></p>
      ${renderPre(curl)}
      <p><strong>${escapeHtml(labels.permissionControl)}</strong> ${escapeHtml(permission)}</p>
      <p><strong>${escapeHtml(labels.orgScope)}</strong> ${escapeHtml(inject)}</p>
    </section>
  `;
};

export const buildOpenApiDocsExportHtml = (
  rows: OpenAPIDocRow[],
  labels: OpenApiDocsPdfLabels
): string => {
  const endpoints = rows.map((row) => renderEndpointBlock(row, labels)).join('');

  return `
    <article class="openapi-pdf">
      <style>
        .openapi-pdf {
          width: ${EXPORT_WIDTH_PX}px;
          box-sizing: border-box;
          padding: 8px 4px 24px;
          color: #1f1f1f;
          background: #fff;
          font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif;
          font-size: 12px;
          line-height: 1.55;
        }
        .openapi-pdf h1 { font-size: 20px; margin: 0 0 8px; }
        .openapi-pdf h2 { font-size: 14px; margin: 0 0 8px; }
        .openapi-pdf p { margin: 0 0 8px; }
        .openapi-pdf .meta, .openapi-pdf .hint { color: #595959; }
        .openapi-pdf table { width: 100%; border-collapse: collapse; margin: 0 0 12px; }
        .openapi-pdf tr, .openapi-pdf h2, .openapi-pdf pre { break-inside: avoid; }
        .openapi-pdf th, .openapi-pdf td {
          border: 1px solid #d9d9d9;
          padding: 6px 8px;
          text-align: left;
          vertical-align: top;
        }
        .openapi-pdf th { background: #f5f5f5; font-weight: 600; }
        .openapi-pdf pre {
          margin: 0 0 12px;
          padding: 8px 10px;
          background: #fafafa;
          border: 1px solid #f0f0f0;
          white-space: pre-wrap;
          word-break: break-all;
          font-size: 11px;
        }
        .openapi-pdf pre [data-pdf-line] { display: block; }
        .openapi-pdf code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
        .openapi-pdf section { padding-bottom: 4px; }
      </style>
      <header data-pdf-block>
        <h1>${escapeHtml(labels.title)}</h1>
        <p class="meta">${escapeHtml(labels.totalCount)} · ${escapeHtml(labels.generatedAt)}</p>
        <p><strong>${escapeHtml(labels.authHeader)}</strong></p>
        <p>${escapeHtml(labels.authHeaderDesc)}</p>
      </header>
      ${renderCatalogIndex(rows, labels)}
      ${endpoints}
    </article>
  `;
};

const PAGE_CONTENT_HEIGHT = PAGE_HEIGHT - PAGE_MARGIN * 2;
const BLOCK_GAP = 3;

const waitForPaint = (): Promise<void> =>
  new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });

const yieldToMain = (): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, 0);
  });

const createExportRoot = (html: string): HTMLElement => {
  const container = document.createElement('div');
  container.setAttribute('aria-hidden', 'true');
  container.style.position = 'fixed';
  container.style.left = '-100000px';
  container.style.top = '0';
  container.style.zIndex = '-1';
  container.style.pointerEvents = 'none';
  container.style.background = '#ffffff';
  container.innerHTML = html;
  document.body.appendChild(container);
  return container;
};

export const choosePageCut = (
  start: number,
  maxEnd: number,
  contentEnd: number,
  breaks: number[]
): number => {
  const limit = Math.min(maxEnd, contentEnd);
  if (limit <= start + CUT_EPSILON) {
    return start;
  }
  const candidates = breaks.filter(
    (point) => point > start + CUT_EPSILON && point <= limit + CUT_EPSILON
  );
  if (contentEnd <= maxEnd + CUT_EPSILON) {
    candidates.push(contentEnd);
  }
  if (candidates.length) {
    return Math.max(...candidates);
  }
  return start;
};

export const collectBreakOffsets = (root: HTMLElement): number[] => {
  const origin = root.getBoundingClientRect().top;
  const height = root.offsetHeight;
  const points = new Set<number>([0, height]);
  root
    .querySelectorAll('[data-pdf-block], tr, pre, h2, table, p, [data-pdf-line]')
    .forEach((node) => {
      const rect = (node as HTMLElement).getBoundingClientRect();
      points.add(rect.top - origin);
      points.add(rect.bottom - origin);
    });
  for (let y = LINE_STRIDE_PX; y < height; y += LINE_STRIDE_PX) {
    points.add(y);
  }
  return [...points]
    .filter((point) => Number.isFinite(point) && point >= 0)
    .sort((a, b) => a - b);
};

const sliceCanvas = (
  canvas: HTMLCanvasElement,
  srcY: number,
  srcHeight: number
): HTMLCanvasElement => {
  const pageCanvas = document.createElement('canvas');
  pageCanvas.width = canvas.width;
  pageCanvas.height = srcHeight;
  const context = pageCanvas.getContext('2d');
  if (context) {
    context.imageSmoothingEnabled = false;
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, pageCanvas.width, pageCanvas.height);
    context.drawImage(
      canvas,
      0,
      srcY,
      canvas.width,
      srcHeight,
      0,
      0,
      canvas.width,
      srcHeight
    );
  }
  return pageCanvas;
};

const addPng = (
  pdf: jsPDF,
  canvas: HTMLCanvasElement,
  y: number,
  destHeight: number,
  alias: string
) => {
  pdf.addImage(
    canvas.toDataURL('image/png'),
    'PNG',
    PAGE_MARGIN,
    y,
    CONTENT_WIDTH,
    destHeight,
    alias,
    PNG_COMPRESSION
  );
};

const appendSlicedCanvas = async (
  pdf: jsPDF,
  canvas: HTMLCanvasElement,
  cssHeight: number,
  breaks: number[],
  nextAlias: () => string
): Promise<number> => {
  const destFullHeight = (canvas.height * CONTENT_WIDTH) / canvas.width;
  const scale = canvas.height / cssHeight;
  const cssPageHeight = (PAGE_CONTENT_HEIGHT / destFullHeight) * cssHeight;

  let cssY = 0;
  let cursorY = PAGE_MARGIN;
  let pageIndex = 0;
  while (cssY < cssHeight - CUT_EPSILON) {
    if (pageIndex > 0) {
      pdf.addPage();
      cursorY = PAGE_MARGIN;
      await yieldToMain();
    }
    const maxEnd = Math.min(cssHeight, cssY + cssPageHeight);
    let cut = choosePageCut(cssY, maxEnd, cssHeight, breaks);
    if (cut <= cssY + CUT_EPSILON) {
      cut = maxEnd;
    }
    const srcY = Math.round(cssY * scale);
    const srcEnd = Math.round(cut * scale);
    const srcHeight = Math.max(1, srcEnd - srcY);
    const destHeight = (srcHeight * CONTENT_WIDTH) / canvas.width;
    addPng(pdf, sliceCanvas(canvas, srcY, srcHeight), cursorY, destHeight, nextAlias());
    cssY = cut;
    cursorY = PAGE_MARGIN + destHeight + BLOCK_GAP;
    pageIndex += 1;
  }
  return cursorY;
};

const appendBlockCanvas = async (
  pdf: jsPDF,
  canvas: HTMLCanvasElement,
  cursorY: number,
  nextAlias: () => string,
  breaks: number[],
  cssHeight: number
): Promise<number> => {
  const destHeight = (canvas.height * CONTENT_WIDTH) / canvas.width;
  if (destHeight <= PAGE_CONTENT_HEIGHT) {
    if (cursorY + destHeight > PAGE_HEIGHT - PAGE_MARGIN) {
      pdf.addPage();
      cursorY = PAGE_MARGIN;
    }
    addPng(pdf, canvas, cursorY, destHeight, nextAlias());
    return cursorY + destHeight + BLOCK_GAP;
  }
  if (cursorY > PAGE_MARGIN + 1) {
    pdf.addPage();
  }
  return appendSlicedCanvas(pdf, canvas, cssHeight, breaks, nextAlias);
};

export const buildOpenApiDocsPdfFilename = (now: Date = new Date()): string => {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `openapi-docs-${year}-${month}-${day}`;
};

export const exportOpenApiDocsToPdf = async (
  rows: OpenAPIDocRow[],
  labels: OpenApiDocsPdfLabels,
  filename: string = buildOpenApiDocsPdfFilename()
): Promise<void> => {
  if (!rows.length) {
    throw new Error('empty-catalog');
  }

  await waitForPaint();
  const root = createExportRoot(buildOpenApiDocsExportHtml(rows, labels));
  try {
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
      compress: true,
    });
    pdf.setProperties({ title: labels.title });
    const blocks = Array.from(root.querySelectorAll('[data-pdf-block]')) as HTMLElement[];
    let cursorY = PAGE_MARGIN;
    let imageIndex = 0;
    const nextAlias = () => `img-${imageIndex++}`;
    for (const block of blocks) {
      await yieldToMain();
      const canvas = await toCanvas(block, {
        pixelRatio: PIXEL_RATIO,
        backgroundColor: '#ffffff',
      });
      cursorY = await appendBlockCanvas(
        pdf,
        canvas,
        cursorY,
        nextAlias,
        collectBreakOffsets(block),
        block.offsetHeight
      );
    }
    pdf.save(`${filename}.pdf`);
  } finally {
    root.remove();
  }
};
