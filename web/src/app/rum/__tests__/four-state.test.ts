import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { HandledRequestError } from '@/utils/request';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import { resolveRumPageState, softDegradation } from '@/app/rum/lib/page-state';

const RUM_ROOT = join(process.cwd(), 'src/app/rum');

function walkPages(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (
        name === '__tests__' ||
        name === 'ui' ||
        name === 'lib' ||
        name === 'api' ||
        name === 'components' ||
        name === 'locales' ||
        name === 'constants'
      ) {
        continue;
      }
      walkPages(full, out);
      continue;
    }
    if (name === 'page.tsx') out.push(full);
  }
  return out;
}

describe('rum DESIGN four-state helpers', () => {
  it('resolves exclusive loading / error / degraded / empty / ready', () => {
    expect(resolveRumPageState({ pending: true, itemCount: 0 })).toBe('loading');
    expect(resolveRumPageState({ pending: false, error: 'boom', itemCount: 0 })).toBe('error');
    expect(
      resolveRumPageState({
        pending: false,
        itemCount: 0,
        page: { controlUnavailable: true },
      }),
    ).toBe('degraded');
    expect(resolveRumPageState({ pending: false, itemCount: 0 })).toBe('empty');
    expect(
      resolveRumPageState({
        pending: false,
        itemCount: 3,
        page: { analyticsUnavailable: true },
      }),
    ).toBe('ready');
    expect(softDegradation({ analyticsUnavailable: true })).toBe('analytics');
    expect(softDegradation({ controlUnavailable: true, analyticsUnavailable: true })).toBe(
      'control',
    );
  });

  it('failed catalog/session first paint is error, not empty', () => {
    expect(
      resolveRumPageState({
        pending: false,
        error: '应用列表加载失败',
        itemCount: 0,
      }),
    ).toBe('error');
    expect(
      resolveRumPageState({
        pending: true,
        error: '应用列表加载失败',
        itemCount: 0,
      }),
    ).toBe('loading');
  });

  it('maps forbidden and unavailable errors to product copy', () => {
    const t = (id: string, fallback?: string) => fallback || id;
    expect(rumErrorMessage(new HandledRequestError('no', { code: 'forbidden' }), t)).toContain(
      '权限',
    );
    expect(rumErrorMessage(new HandledRequestError('down', { code: 'unavailable' }), t)).toContain(
      '控制面',
    );
    expect(rumErrorMessage(new HandledRequestError('x', { code: 'not_found' }), t)).toContain(
      '不存在',
    );
  });
  it('session detail attribute rows keep CJK labels on one line and truncate long ids', () => {
    const src = readFileSync(join(RUM_ROOT, 'sessions/[sessionId]/page.tsx'), 'utf8');
    expect(src).toContain('whitespace-nowrap');
    expect(src).toContain('max-w-[170px]');
    expect(src).toContain('copyText={session.userId');
  });
});

describe('rum page four-state presence (static)', () => {
  const pages = walkPages(RUM_ROOT);
  const rel = (file: string) => file.slice(RUM_ROOT.length + 1).replace(/\\/g, '/');

  it('finds the route pages under web/src/app/rum', () => {
    expect(pages.map(rel).sort()).toEqual(
      [
        'alert-events/page.tsx',
        'applications/[name]/overview/page.tsx',
        'applications/[name]/page.tsx',
        'applications/page.tsx',
        'compliance/page.tsx',
        'errors/detail/page.tsx',
        'errors/page.tsx',
        'funnels/[id]/page.tsx',
        'funnels/page.tsx',
        'monitors/page.tsx',
        'page.tsx',
        'releases/page.tsx',
        'sessions/[sessionId]/page.tsx',
        'sessions/[sessionId]/replay/page.tsx',
        'sessions/page.tsx',
        'setup/[name]/page.tsx',
        'setup/page.tsx',
        'views/page.tsx',
      ].sort(),
    );
  });

  it('list/detail pages expose loading + empty; request errors use framework toast', () => {
    for (const file of pages) {
      const src = readFileSync(file, 'utf8');
      if (src.includes('redirect(')) continue;
      if (src.includes('FunnelsWorkspace') && !src.includes('pending')) continue;
      if (src.includes('RumPortPlaceholder')) {
        throw new Error(`placeholder still present: ${file}`);
      }
      const hasLoading =
        src.includes('pending') ||
        src.includes('loading=') ||
        src.includes('Skeleton') ||
        src.includes('Spin');
      const hasEmpty = src.includes('<Empty') || src.includes('Empty ');
      const hasErrorHandling = src.includes('catch');
      expect(hasLoading, `${file} missing loading`).toBe(true);
      expect(hasEmpty, `${file} missing empty`).toBe(true);
      expect(hasErrorHandling, `${file} missing catch`).toBe(true);
    }

    const noPageRequestError = [
      'sessions/[sessionId]/page.tsx',
      'sessions/[sessionId]/replay/page.tsx',
      'views/page.tsx',
      'errors/page.tsx',
      'funnels/funnels-workspace.tsx',
      'monitors/page.tsx',
      'setup/page.tsx',
      'setup/[name]/page.tsx',
      'applications/[name]/overview/page.tsx',
      'alert-events/page.tsx',
      'releases/page.tsx',
      'compliance/page.tsx',
    ];
    for (const rel of noPageRequestError) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('RumPageError'), `${rel} should not render RumPageError`).toBe(false);
      expect(
        /type=["']error["']/.test(src) && src.includes('setError'),
        `${rel} should not render page request error Alert`,
      ).toBe(false);
    }

    const workspace = readFileSync(join(RUM_ROOT, 'funnels/funnels-workspace.tsx'), 'utf8');
    expect(workspace.includes('pending')).toBe(true);
    expect(workspace.includes('<Empty')).toBe(true);
    expect(workspace.includes('catch')).toBe(true);
  });

  it('application catalog and session list wait for auth and keep failed loads off the empty copy', () => {
    for (const rel of ['applications/page.tsx', 'sessions/page.tsx'] as const) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('authReady'), `${rel} missing authReady gate`).toBe(true);
      expect(src.includes('useRumAuthedEffect'), `${rel} missing cancelled authed load`).toBe(true);
      expect(src.includes('RumPageError'), `${rel} missing failed-load chrome`).toBe(true);
      // Refetch (e.g. time-window change) must enter loading even when prior page is cached.
      expect(
        /pending:\s*pending\s*&&\s*page\s*===\s*null/.test(src),
        `${rel} still gates loading chrome on page === null`,
      ).toBe(false);
    }
    const catalog = readFileSync(join(RUM_ROOT, 'applications/page.tsx'), 'utf8');
    expect(catalog.includes("chrome === 'error'")).toBe(true);
    expect(catalog.includes("chrome === 'loading'")).toBe(true);
  });

  it('list empty states are vertically centered and saved-views chrome is gone', () => {
    const listPages = [
      'sessions/page.tsx',
      'views/page.tsx',
      'errors/page.tsx',
      'releases/page.tsx',
      'monitors/page.tsx',
      'alert-events/page.tsx',
      'compliance/page.tsx',
    ] as const;
    for (const rel of listPages) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('SavedViewsBar'), `${rel} still mounts SavedViewsBar`).toBe(false);
      expect(
        /flex min-h-0 flex-1 items-center justify-center[\s\S]{0,200}<Empty/.test(src),
        `${rel} empty state is not vertically centered`,
      ).toBe(true);
    }
    expect(existsSync(join(RUM_ROOT, 'components/saved-views-bar.tsx'))).toBe(false);
  });

  it('page loading uses isomorphic rum skeletons instead of Spin or paragraph Skeleton', () => {
    const skeletonPages = [
      'applications/page.tsx',
      'setup/page.tsx',
      'setup/[name]/page.tsx',
      'applications/[name]/overview/page.tsx',
      'sessions/page.tsx',
      'sessions/[sessionId]/page.tsx',
      'sessions/[sessionId]/replay/page.tsx',
      'views/page.tsx',
      'errors/page.tsx',
      'errors/detail/page.tsx',
      'releases/page.tsx',
      'monitors/page.tsx',
      'compliance/page.tsx',
      'alert-events/page.tsx',
      'funnels/funnels-workspace.tsx',
    ];
    for (const rel of skeletonPages) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('rum-skeleton'), `${rel} missing rum-skeleton`).toBe(true);
      expect(src.includes('<Skeleton '), `${rel} still uses paragraph Skeleton`).toBe(false);
      expect(
        /<(?:Custom)?Table[\s\S]{0,800}loading=\{pending\}/.test(src),
        `${rel} table still uses Spin overlay`,
      ).toBe(false);
    }
  });

  it('product tables use CustomTable instead of raw AntD Table + Pagination', () => {
    const tableSurfaces = [
      'applications/page.tsx',
      'setup/page.tsx',
      'applications/[name]/overview/page.tsx',
      'sessions/page.tsx',
      'views/page.tsx',
      'errors/page.tsx',
      'errors/detail/page.tsx',
      'releases/page.tsx',
      'releases/ui/sourcemap-manager.tsx',
      'monitors/page.tsx',
      'compliance/page.tsx',
      'alert-events/page.tsx',
      'funnels/funnels-workspace.tsx',
    ];
    for (const rel of tableSurfaces) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes("from '@/components/custom-table'"), `${rel} missing CustomTable import`).toBe(
        true,
      );
      expect(src.includes('<CustomTable'), `${rel} missing CustomTable`).toBe(true);
      expect(/<Pagination[\s>]/.test(src), `${rel} still has standalone Pagination`).toBe(false);
      // DESIGN One Header Alignment Rule: column.align moves the header too.
      expect(
        /align:\s*['"](?:center|right)['"]/.test(src),
        `${rel} still uses column.align center/right`,
      ).toBe(false);
    }
  });

  it('list table primary cells inherit body 14px instead of text-xs', () => {
    const banned = [
      ['sessions/page.tsx', ['truncate text-sm', 'text-xs tabular-nums text-[var(--color-text-3)]">{formatWhen']],
      [
        'errors/page.tsx',
        ['truncate text-xs font-medium', 'text-xs tabular-nums', 'text-xs font-semibold tabular-nums'],
      ],
      [
        'alert-events/page.tsx',
        ['font-mono text-xs font-semibold', 'truncate text-xs text-[var(--color-text-3)]'],
      ],
      ['releases/page.tsx', ['font-mono text-xs font-medium', 'font-mono text-xs tabular-nums']],
      ['compliance/page.tsx', ['font-mono text-xs font-medium', 'font-mono text-xs font-semibold']],
    ] as const;
    for (const [rel, needles] of banned) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      for (const needle of needles) {
        expect(src.includes(needle), `${rel} still shrinks table cells with ${needle}`).toBe(false);
      }
    }
  });

  it('list table cells stay regular weight and body color except links and fail emphasis', () => {
    const banned = [
      [
        'sessions/page.tsx',
        [
          'font-medium text-[var(--color-text-1)]',
          'font-semibold text-[var(--color-fail)]',
          'tabular-nums text-[var(--color-text-3)]">{formatWhen',
          'gap-1.5 text-[var(--color-text-3)]',
        ],
      ],
      [
        'errors/page.tsx',
        [
          'truncate font-medium',
          'font-semibold tabular-nums',
          'truncate text-[var(--color-text-3)]">{issue.application',
          'tabular-nums text-[var(--color-text-3)]">{formatWhen',
        ],
      ],
      [
        'alert-events/page.tsx',
        ['className="font-medium"', 'font-mono font-semibold', 'truncate text-[var(--color-text-3)]'],
      ],
      ['monitors/page.tsx', ['truncate font-medium', 'font-mono text-[var(--color-text-3)]']],
      ['releases/page.tsx', ['font-mono font-medium', 'font-semibold text-[var(--color-fail)]']],
      ['compliance/page.tsx', ['font-mono font-medium', 'font-mono font-semibold']],
    ] as const;
    for (const [rel, needles] of banned) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      for (const needle of needles) {
        expect(src.includes(needle), `${rel} still styles table cells with ${needle}`).toBe(false);
      }
    }
  });

  it('entity list tables paginate; nested preview tables do not', () => {
    const listPages = [
      'applications/page.tsx',
      'setup/page.tsx',
      'sessions/page.tsx',
      'views/page.tsx',
      'errors/page.tsx',
      'releases/page.tsx',
      'monitors/page.tsx',
      'compliance/page.tsx',
      'alert-events/page.tsx',
    ];
    for (const rel of listPages) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('pagination={{'), `${rel} missing list pager`).toBe(true);
    }
    const nested = [
      'applications/[name]/overview/page.tsx',
      'errors/detail/page.tsx',
      'releases/ui/sourcemap-manager.tsx',
      'funnels/funnels-workspace.tsx',
    ];
    for (const rel of nested) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('pagination={false}'), `${rel} should keep nested table unpaged`).toBe(
        true,
      );
      expect(src.includes('pagination={{'), `${rel} nested table should not paginate`).toBe(false);
    }
  });

  it('applications catalog uses pixel columns so the action column is not squeezed', () => {
    const src = readFileSync(join(RUM_ROOT, 'applications/page.tsx'), 'utf8');
    expect(src).not.toMatch(/width: '\d+%'/);
    expect(src).toMatch(/key: 'actions',\s*width: 80,/);
    expect(src).not.toContain("rum.applications.openSetup");
    expect(src).toContain('autoScrollX={false}');
  });

  it('setup list configures existing apps and does not create them', () => {
    const src = readFileSync(join(RUM_ROOT, 'setup/page.tsx'), 'utf8');
    expect(src).not.toContain('CreateApplicationDrawer');
    expect(src).not.toContain('PlusOutlined');
    expect(src).toContain("router.push('/rum/applications')");
    expect(src).toContain('rumIngestStatus');
    expect(src).toContain('rumSetupPath');
  });

  it('creating an application continues into setup for that app', () => {
    const src = readFileSync(join(RUM_ROOT, 'applications/ui/create-application-drawer.tsx'), 'utf8');
    expect(src).toContain('rumSetupPath(view.application)');
  });

  it('legacy /rum/applications/:name redirects to setup', () => {
    const src = readFileSync(join(RUM_ROOT, 'applications/[name]/page.tsx'), 'utf8');
    expect(src).toContain('redirect(`/rum/setup/${encodeURIComponent(name)}`)');
  });

  it('setup detail returns to the setup list', () => {
    const src = readFileSync(join(RUM_ROOT, 'setup/[name]/page.tsx'), 'utf8');
    expect(src).toContain("router.push('/rum/setup')");
  });

  it('action columns are pinned to the right', () => {
    const actionTables = [
      'applications/page.tsx',
      'setup/page.tsx',
      'sessions/page.tsx',
      'errors/page.tsx',
      'errors/detail/page.tsx',
      'releases/page.tsx',
      'monitors/page.tsx',
    ];
    for (const rel of actionTables) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes("key: 'actions'"), `${rel} missing actions column`).toBe(true);
      expect(
        /key: 'actions',\s*width: \d+,\s*fixed: 'right'/.test(src),
        `${rel} actions column is not fixed right`,
      ).toBe(true);
    }
  });

  it('analytics list pages wire PipelineDegradedBanner', () => {
    const analyticsPages = [
      'applications/page.tsx',
      'setup/page.tsx',
      'applications/[name]/overview/page.tsx',
      'sessions/page.tsx',
      'sessions/[sessionId]/page.tsx',
      'sessions/[sessionId]/replay/page.tsx',
      'views/page.tsx',
      'errors/page.tsx',
      'errors/detail/page.tsx',
      'releases/page.tsx',
      'funnels/funnels-workspace.tsx',
    ];
    for (const rel of analyticsPages) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('PipelineDegradedBanner'), `${rel} missing degrade banner`).toBe(true);
    }
  });

  it('long detail pages scroll inside the clipped rum canvas', () => {
    const detailPages = [
      'setup/[name]/page.tsx',
      'applications/[name]/overview/page.tsx',
      'sessions/[sessionId]/page.tsx',
      'errors/detail/page.tsx',
    ];
    for (const rel of detailPages) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(
        src.includes('flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto'),
        `${rel} is clipped by rum layout overflow-hidden`,
      ).toBe(true);
    }
  });

  it('operate surfaces wrap mutations with RumPermission', () => {
    const operatePages = [
      'applications/page.tsx',
      'setup/[name]/page.tsx',
      'errors/page.tsx',
      'errors/detail/page.tsx',
      'funnels/funnels-workspace.tsx',
      'releases/page.tsx',
      'monitors/page.tsx',
      'compliance/page.tsx',
    ];
    for (const rel of operatePages) {
      const src = readFileSync(join(RUM_ROOT, rel), 'utf8');
      expect(src.includes('RumPermission'), `${rel} missing RumPermission`).toBe(true);
    }
  });
});
