import type {
  AiContextSection,
  AiPageContext,
  PageContextMessage,
  PageContextToolkit,
} from '@/components/ai-page-context/types';
import { redactSensitiveText } from '@/components/ai-page-context/redact-sensitive-text';

const TITLE_PREFIX = 'apm-trace:';
const TRACE_VIEW_VALUES = ['waterfall', 'flame', 'list'] as const;
const ERROR_SPAN_LIMIT = 8;
const ATTRIBUTE_LIMIT = 20;

const cleanLabel = (value: string) => value.replace(/\s+/g, ' ').trim();

const activeTraceView = (): string => {
  const root = document.querySelector('[aria-label*="视图模式"], [aria-label*="view mode" i]');
  return selectedSegmentedValue(TRACE_VIEW_VALUES, root);
};

const selectedSegmentedValue = (values: readonly string[], root?: Element | Document | null): string => {
  const scope: ParentNode = root || document;
  const inputs = Array.from(scope.querySelectorAll<HTMLInputElement>('.ant-segmented-item-input'));
  const index = inputs.findIndex((input) => input.checked);
  if (index < 0) return '';
  return values[index] || '';
};

const normalizedPathname = (pathname = typeof window === 'undefined' ? '' : window.location.pathname) =>
  pathname.endsWith('/') ? pathname : `${pathname}/`;

const traceIdFromPath = (pathname = typeof window === 'undefined' ? '' : window.location.pathname) => {
  const match = normalizedPathname(pathname).match(/\/apm\/explore\/traces\/([^/]+)\//);
  return match?.[1] || '';
};

const labeledStat = (labelPattern: RegExp): string => {
  const labels = Array.from(document.querySelectorAll('.text-xs.font-medium'));
  const label = labels.find((node) => labelPattern.test(cleanLabel(node.textContent || '')));
  return cleanLabel(label?.nextElementSibling?.textContent || '');
};

const headingRoot = (
  pattern: RegExp,
  hasContent: (node: HTMLElement) => boolean,
): HTMLElement | null => {
  const heading = Array.from(document.querySelectorAll('strong, h3, h4, .ant-typography')).find((node) =>
    pattern.test(cleanLabel(node.textContent || '')),
  );
  if (!(heading instanceof HTMLElement)) return null;
  let node: HTMLElement | null = heading;
  for (let depth = 0; depth < 8 && node; depth += 1) {
    if (hasContent(node)) return node;
    node = node.parentElement;
  }
  return heading.parentElement;
};

const readServiceBreakdown = (): string[] => {
  const root = headingRoot(
    /服务耗时分解|duration breakdown/i,
    (node) => Array.from(node.querySelectorAll('.flex.items-center.gap-2')).some((row) => row.querySelector('.font-mono')),
  );
  if (!root) return [];
  return Array.from(root.querySelectorAll('.flex.items-center.gap-2'))
    .map((row) => {
      const service = cleanLabel(row.querySelector('.font-mono')?.textContent || '');
      const numbers = Array.from(row.querySelectorAll('.tabular-nums'))
        .map((node) => cleanLabel(node.textContent || ''))
        .filter(Boolean);
      if (!service || !numbers.length) return '';
      return [service, ...numbers].join(' ');
    })
    .filter(Boolean);
};

const readWaterfallErrors = (): string[] =>
  Array.from(document.querySelectorAll('button')).filter((button) => button.querySelector('.ant-tag-error'))
    .map((button) => {
      const name = cleanLabel(button.querySelector('.font-mono')?.textContent || '');
      const service = cleanLabel(
        Array.from(button.querySelectorAll('span')).find((node) =>
          node.className.includes('text-[var(--color-text-3)]'),
        )?.textContent || '',
      );
      const duration = cleanLabel(
        Array.from(button.querySelectorAll('.tabular-nums'))[0]?.textContent || '',
      );
      return [service, name, duration].filter(Boolean).join(' · ');
    })
    .filter(Boolean);

const readListErrors = (): string[] =>
  Array.from(document.querySelectorAll('button')).map((button) => {
    const duration = Array.from(button.querySelectorAll('span'))
      .map((node) => node.textContent || '')
      .find((text) => text.includes('⚠'));
    if (!duration) return '';
    const name = cleanLabel(button.querySelector('.font-mono')?.textContent || '');
    const service = cleanLabel(
      Array.from(button.querySelectorAll('span')).find((node) =>
        node.className.includes('text-[var(--color-text-3)]'),
      )?.textContent || '',
    );
    return [service, name, cleanLabel(duration)].filter(Boolean).join(' · ');
  }).filter(Boolean);

const isFlameErrorBackground = (style: string): boolean =>
  /(?:^|;)\s*background:\s*var\(--color-fail\)\s*(;|$)/i.test(style);

const readFlameErrors = (): string[] =>
  Array.from(document.querySelectorAll('button')).filter((button) =>
    isFlameErrorBackground(button.getAttribute('style') || ''),
  ).map((button) => cleanLabel(button.getAttribute('aria-label') || button.textContent || '')).filter(Boolean);

export const readErrorSpanLines = (view = activeTraceView()): string[] => {
  if (view === 'list') return readListErrors();
  if (view === 'flame') return readFlameErrors();
  return readWaterfallErrors();
};

const spanQueryValue = (): string => {
  const input = document.querySelector<HTMLInputElement>('input[aria-label*="搜索跨度"], input[aria-label*="span" i]');
  return cleanLabel(input?.value || '');
};

const readSelectedSpanDetail = (): string => {
  const root = headingRoot(
    /Span 详情|Span detail/i,
    (node) => Boolean(node.querySelector('.ant-descriptions, tbody')),
  );
  if (!root) return '';
  const lines: string[] = [];
  const name = cleanLabel(root.querySelector('.font-mono')?.textContent || '');
  if (name) lines.push(`名称: ${name}`);
  Array.from(root.querySelectorAll('.ant-descriptions-item, .ant-descriptions-item-container')).forEach((item) => {
    const label = cleanLabel(
      item.querySelector('.ant-descriptions-item-label')?.textContent || '',
    );
    const value = cleanLabel(
      item.querySelector('.ant-descriptions-item-content')?.textContent || '',
    );
    if (label && value) lines.push(`${label}: ${redactSensitiveText(value)}`);
  });
  const rows = Array.from(root.querySelectorAll('tbody tr')).slice(0, ATTRIBUTE_LIMIT).map((row) => {
    const cells = Array.from(row.querySelectorAll('td')).map((cell) => cleanLabel(cell.textContent || ''));
    if (cells.length < 2) return '';
    return `${cells[0]}: ${redactSensitiveText(cells[1])}`;
  }).filter(Boolean);
  if (rows.length) {
    const total = root.querySelectorAll('tbody tr').length;
    lines.push(total > ATTRIBUTE_LIMIT ? `属性共 ${total} 项，已附 ${rows.length} 项` : '属性:');
    lines.push(...rows);
  }
  return lines.join('\n');
};

interface TraceDetailStamp {
  traceId: string;
  view: string;
  errorCount: string;
  duration: string;
  serviceCount: string;
  spanCount: string;
  spanQuery: string;
  truncated: boolean;
  breakdownFingerprint: string;
  errorFingerprint: string;
  selectedFingerprint: string;
}

const readTraceDetailStamp = (): TraceDetailStamp => {
  const traceId = traceIdFromPath();
  return {
    traceId,
    view: activeTraceView(),
    errorCount: labeledStat(/错误 Span|Error Spans/i),
    duration: labeledStat(/总耗时|Total duration/i),
    serviceCount: labeledStat(/服务数|Services/i),
    spanCount: labeledStat(/Span 数|Span count/i),
    spanQuery: spanQueryValue(),
    truncated: Boolean(
      Array.from(document.querySelectorAll('.ant-alert-message, .ant-alert')).find((node) =>
        /安全上限|safety limit/i.test(node.textContent || ''),
      ),
    ),
    breakdownFingerprint: readServiceBreakdown().join('|'),
    errorFingerprint: readErrorSpanLines().join('|'),
    selectedFingerprint: readSelectedSpanDetail(),
  };
};

const buildTraceCurrentTime = (stamp: TraceDetailStamp): string =>
  [
    stamp.view,
    stamp.errorCount,
    stamp.duration,
    stamp.spanQuery,
    stamp.breakdownFingerprint,
    stamp.errorFingerprint,
    stamp.selectedFingerprint,
    stamp.truncated ? 'truncated' : '',
  ].filter(Boolean).join('::');

const textSections = (stamp: TraceDetailStamp): AiContextSection[] => {
  const view = stamp.view || 'waterfall';
  const errors = readErrorSpanLines(view);
  const visible = errors.slice(0, ERROR_SPAN_LIMIT);
  const headerCount = Number.parseInt(stamp.errorCount, 10);
  const totalErrors = Number.isFinite(headerCount) ? headerCount : errors.length;
  const listFiltered = view === 'list' && Boolean(stamp.spanQuery);
  const errorNotes = [
    `页头错误 Span: ${stamp.errorCount || '0'}`,
    listFiltered ? '列表已过滤，仅展示可见错误 Span' : '',
    visible.length < totalErrors
      ? `共 ${totalErrors} 个，以下可见 ${visible.length} 条`
      : '',
  ].filter(Boolean);
  const breakdown = readServiceBreakdown();
  const selected = readSelectedSpanDetail();
  return [
    {
      id: 'apm-trace-identity',
      label: '当前调用链',
      content: [
        '正在查看 APM 调用链详情',
        stamp.traceId ? `Trace ID: ${stamp.traceId}` : '',
        stamp.spanCount ? `Span 数: ${stamp.spanCount}` : '',
        stamp.errorCount ? `错误 Span: ${stamp.errorCount}` : '',
        stamp.serviceCount ? `服务数: ${stamp.serviceCount}` : '',
        stamp.duration ? `总耗时: ${stamp.duration}` : '',
        view ? `视图: ${view}` : '',
        stamp.truncated ? '展示部分 Span' : '',
      ].filter(Boolean).join('\n'),
      priority: 10,
    },
    ...(breakdown.length
      ? [{
        id: 'apm-trace-breakdown',
        label: '服务耗时分解',
        content: breakdown.join('\n'),
        priority: 9,
      }]
      : []),
    {
      id: 'apm-trace-errors',
      label: '错误 Span',
      content: [...errorNotes, ...visible].join('\n'),
      priority: 8,
    },
    ...(selected
      ? [{
        id: 'apm-trace-selected',
        label: '当前选中 Span',
        content: selected,
        priority: 4,
      }]
      : []),
  ];
};

export function getMessage(): PageContextMessage {
  const stamp = readTraceDetailStamp();
  if (!stamp.traceId) return { title: '' };
  const title = `${TITLE_PREFIX}${stamp.traceId}`;
  const currentTime = buildTraceCurrentTime(stamp);
  return currentTime ? { title, currentTime } : { title };
}

export function getTextContext(): Partial<AiPageContext> {
  const stamp = readTraceDetailStamp();
  if (!stamp.traceId) return { sections: [], images: [] };
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'apm',
    title: document.title || 'Trace 详情',
    sections: textSections(stamp),
    images: [],
  };
}

export async function getContext(toolkit: PageContextToolkit): Promise<Partial<AiPageContext>> {
  void toolkit;
  const stamp = readTraceDetailStamp();
  const base = getTextContext();
  if (!stamp.traceId) return base;
  console.info('[ai-page-context] page data updated at', buildTraceCurrentTime(stamp), {
    view: stamp.view,
    errorCount: stamp.errorCount,
    duration: stamp.duration,
  });
  return base;
}
