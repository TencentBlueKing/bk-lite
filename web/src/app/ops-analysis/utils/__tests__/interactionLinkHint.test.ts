import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import { canOpenRoom3DRackLink } from '@/app/ops-analysis/components/widgets/room3D/room3DData';
import {
  appendDataLinkTooltipFooter,
  application3DHoverTitle,
  composeNativeHint,
  resolveDataLinkTooltipTheme,
  shouldShowContextLinkHint,
  shouldShowDataLinkHint,
  wrapDataLinkTooltipFormatter,
} from '@/app/ops-analysis/utils/interactionLinkHint';

const footer = '主机详情 ↗ 点击打开';
const base = (value = '<div>cpu: 12</div>') => value;

describe('shouldShowDataLinkHint', () => {
  it('is true only for an active data link in view mode', () => {
    expect(shouldShowDataLinkHint('view', { kind: 'data' })).toBe(true);
    expect(shouldShowDataLinkHint('edit', { kind: 'data' })).toBe(false);
    expect(shouldShowDataLinkHint('share', { kind: 'data' })).toBe(false);
    expect(shouldShowDataLinkHint('view', { kind: 'title' })).toBe(false);
    expect(shouldShowDataLinkHint('view', { kind: 'none' })).toBe(false);
    expect(shouldShowDataLinkHint('view', undefined)).toBe(false);
  });
});

describe('wrapDataLinkTooltipFormatter', () => {
  const options = {
    footerText: footer,
    theme: 'dark' as const,
  };

  it('appends an escaped footer only when a data link is active in view mode', () => {
    const formatter = () => base();
    const wrapped = wrapDataLinkTooltipFormatter(formatter, {
      ...options,
      surface: 'view',
      link: { kind: 'data' },
      footerText: '打开 <script>',
    });

    expect(wrapped).not.toBe(formatter);
    const html = String(wrapped?.({}));
    expect(html.startsWith('<div>cpu: 12')).toBe(true);
    expect(html).toContain('data-ops-link-hint="true"');
    expect(html).toContain('打开 &lt;script&gt;');
    expect(html).not.toContain('<script>');
    expect(html).toContain('rgba(232, 238, 247, 0.62)');
    expect(html.endsWith('</div>')).toBe(true);
  });

  it('returns the original formatter when the hint is off', () => {
    const formatter = () => base();
    expect(wrapDataLinkTooltipFormatter(formatter, {
      ...options,
      surface: 'edit',
      link: { kind: 'data' },
    })).toBe(formatter);
    expect(wrapDataLinkTooltipFormatter(formatter, {
      ...options,
      surface: 'share',
      link: { kind: 'data' },
    })).toBe(formatter);
    expect(wrapDataLinkTooltipFormatter(formatter, {
      ...options,
      surface: 'view',
      link: { kind: 'title' },
    })).toBe(formatter);
    expect(wrapDataLinkTooltipFormatter(undefined, {
      ...options,
      surface: 'view',
      link: { kind: 'title' },
      fallback: () => base(),
    })).toBeUndefined();
  });

  it('skips the footer when the shared can-open check rejects the column', () => {
    const formatter = () => base();
    const hidden = wrapDataLinkTooltipFormatter(formatter, {
      ...options,
      surface: 'view',
      link: { kind: 'data' },
      includeFooter: () => false,
    });
    expect(hidden?.({})).toBe(base());

    const shown = wrapDataLinkTooltipFormatter(formatter, {
      ...options,
      surface: 'view',
      link: { kind: 'data' },
      includeFooter: () => true,
    });
    expect(String(shown?.({}))).toContain(footer);
  });

  it('keeps an empty custom formatter empty', () => {
    const wrapped = wrapDataLinkTooltipFormatter(() => '', {
      ...options,
      surface: 'view',
      link: { kind: 'data' },
    });
    expect(wrapped?.({})).toBe('');
  });

  it('uses the fallback formatter when the chart has no custom one', () => {
    const wrapped = wrapDataLinkTooltipFormatter(undefined, {
      ...options,
      surface: 'view',
      link: { kind: 'data' },
      theme: 'light',
      fallback: () => '<div>延迟: 3</div>',
    });
    const html = String(wrapped?.({}));
    expect(html).toContain('延迟: 3');
    expect(html).toContain(footer);
    expect(html).toContain('rgba(30, 37, 46, 0.55)');
  });
});

describe('appendDataLinkTooltipFooter', () => {
  it('leaves non-string tooltip results untouched', () => {
    const node = { tag: 'div' };
    expect(appendDataLinkTooltipFooter(node, footer, 'light')).toBe(node);
  });
});

describe('data link hint gating for 3D', () => {
  it('skips placeholder racks and non-view surfaces', () => {
    expect(shouldShowContextLinkHint(
      'view',
      { kind: 'data' },
      canOpenRoom3DRackLink({ is_conflict: false }),
    )).toBe(true);
    expect(shouldShowContextLinkHint(
      'view',
      { kind: 'data' },
      canOpenRoom3DRackLink({}),
    )).toBe(true);
    expect(shouldShowContextLinkHint(
      'view',
      { kind: 'data' },
      canOpenRoom3DRackLink({ is_conflict: true }),
    )).toBe(false);
    expect(shouldShowContextLinkHint(
      'edit',
      { kind: 'data' },
      canOpenRoom3DRackLink({ is_conflict: false }),
    )).toBe(false);
    expect(shouldShowContextLinkHint(
      'share',
      { kind: 'data' },
      canOpenRoom3DRackLink({ is_conflict: false }),
    )).toBe(false);
    expect(shouldShowContextLinkHint('view', { kind: 'title' }, true)).toBe(false);
  });

  it('adds the right-click line only on objects that open the menu', () => {
    expect(application3DHoverTitle('门户', 'wall', '右键打开链接')).toBe('门户\n右键打开链接');
    expect(application3DHoverTitle('web-1', 'host', '右键打开链接')).toBe('web-1\n右键打开链接');
    expect(application3DHoverTitle('订单', 'application', '右键打开链接')).toBe('订单\n右键打开链接');
    expect(application3DHoverTitle('系统', 'system', '右键打开链接')).toBe('系统\n右键打开链接');
    expect(application3DHoverTitle('机柜', 'cabinet', '右键打开链接')).toBe('机柜');
    expect(application3DHoverTitle('门户', 'wall', '')).toBe('门户');
    expect(application3DHoverTitle('门户', 'wall', undefined)).toBe('门户');
    expect(composeNativeHint('名称', '点击打开：详情')).toBe('名称\n点击打开：详情');
    expect(composeNativeHint(undefined, undefined)).toBeUndefined();
  });
});

describe('screen table action button', () => {
  it('inherits the screen table font and uses the chrome accent', () => {
    const source = readFileSync(
      path.join(process.cwd(), 'src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx'),
      'utf8',
    );
    expect(source).toContain('.screen-tech-canvas .ant-table-tbody > tr > td .ant-btn-link {');
    expect(source).toContain('height: auto !important;');
    expect(source).toContain('padding: 0 !important;');
    expect(source).toContain('font-size: inherit !important;');
    expect(source).toContain('line-height: inherit !important;');
    expect(source).toContain('color: var(--screen-chrome-accent) !important;');
    expect(source).toContain('color: color-mix(in srgb, var(--screen-chrome-accent) 72%, white) !important;');
  });
});

describe('resolveDataLinkTooltipTheme', () => {
  it('follows the screen theme, then the app theme', () => {
    expect(resolveDataLinkTooltipTheme('screen-dark', 'light')).toBe('dark');
    expect(resolveDataLinkTooltipTheme('screen-light', 'dark')).toBe('light');
    expect(resolveDataLinkTooltipTheme(undefined, 'dark')).toBe('dark');
    expect(resolveDataLinkTooltipTheme('default', 'light')).toBe('light');
  });
});
