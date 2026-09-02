import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { createThemeCss, legacyVariableMap } from '../src/theme/css-adapter';
import { defaultDarkTokens, defaultLightTokens, defaultTheme } from '../src/theme/defaults';

const detailPage = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/detail/page.tsx', import.meta.url),
  'utf8',
);
const userSyncList = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncSourceList.tsx', import.meta.url),
  'utf8',
);
const userSyncListStyles = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncSourceList.module.scss', import.meta.url),
  'utf8',
);
const userSyncOperateModal = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncOperateModal.tsx', import.meta.url),
  'utf8',
);
const userSyncConfigFields = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx', import.meta.url),
  'utf8',
);

assert.match(
  detailPage,
  /<section className="grid overflow-hidden rounded-md bg-\[var\(--color-bg\)\] shadow-sm xl:grid-cols-\[minmax\(0,8\.4fr\)_minmax\(200px,1\.6fr\)\]">/,
  'integration detail main pane must use the container surface token so dark theme darkens with chrome',
);
assert.doesNotMatch(
  detailPage,
  /\bbg-white\b/,
  'integration detail must not hardcode a white pane that fights dark-theme labels and inputs',
);
assert.match(
  detailPage,
  /className="mb-4 text-\[16px\] font-semibold text-\[var\(--color-text\)\]"/,
  'section titles must keep semantic text tokens so they remain readable on the themed pane',
);
assert.match(
  detailPage,
  /className="rounded-md border border-\[var\(--color-border\)\] bg-\[var\(--color-bg\)\] px-3 py-2"/,
  'status cards must stay on the same surface token as the pane, distinguished by border',
);

assert.match(
  userSyncListStyles,
  /\.card \{[^}]*background:\s*var\(--color-bg\);/s,
  'user-sync outer cards must use the container surface token',
);
assert.match(
  userSyncListStyles,
  /\.metricCard \{[^}]*background:\s*var\(--color-fill-1\);/s,
  'user-sync nested metric blocks must use the secondary surface token, not a hardcoded light fill',
);
assert.match(
  userSyncListStyles,
  /\.metricCard \{[^}]*color:\s*var\(--color-text-1\);/s,
  'user-sync nested metric blocks must inherit themed text color',
);
assert.doesNotMatch(
  userSyncListStyles,
  /#f8fafc|#f3f6fa|#fff(?:fff)?\b/i,
  'user-sync source list nested surfaces must not hardcode light-theme fills',
);
assert.match(
  userSyncList,
  /styles\.metricCard[\s\S]*text-\[var\(--color-text-1\)\][\s\S]*syncCycleText/s,
  'sync cycle nested value must use primary text token',
);
assert.match(
  userSyncList,
  /system\.user\.userSyncPage\.syncCycle/,
  'sync cycle nested label must remain on the metric card',
);

assert.match(
  userSyncOperateModal,
  /bg-\[var\(--color-primary-bg-active\)\]/,
  'selected add-source step cards must use the themed selected surface token',
);
assert.match(
  userSyncOperateModal,
  /border-\[var\(--color-border\)\] bg-\[var\(--color-bg\)\]/,
  'idle add-source step cards must use the container surface token',
);
assert.match(
  userSyncOperateModal,
  /rounded-\[22px\] border border-\[var\(--color-border\)\] bg-\[var\(--color-bg\)\] px-5 py-5/,
  'add-source form pane must use the container surface token instead of a white card',
);
assert.match(
  userSyncOperateModal,
  /text-\[15px\] font-semibold text-\[var\(--color-text-1\)\]/,
  'add-source step titles must use the primary text token',
);
assert.doesNotMatch(
  userSyncOperateModal,
  /\bbg-white\b|\bbg-emerald-50\b|\bbg-blue-50\b|\bbg-slate-100\b/,
  'add-source modal must not hardcode light-theme fills that fight dark-theme labels',
);
assert.match(
  userSyncConfigFields,
  /rounded-sm border border-\[var\(--color-border\)\] bg-\[var\(--color-fill-1\)\] p-2/,
  'mapping row nested chips in the add-source modal must use the secondary surface token',
);
assert.doesNotMatch(
  userSyncConfigFields,
  /\bbg-white\b/,
  'user-sync config fields must not hardcode a white nested chip',
);

assert.equal(legacyVariableMap['--color-bg'], 'surfaceContainer');
assert.equal(legacyVariableMap['--color-fill-1'], 'fillSubtle');
assert.equal(legacyVariableMap['--color-text-1'], 'textPrimary');
assert.equal(legacyVariableMap['--color-text-3'], 'textTertiary');
assert.equal(legacyVariableMap['--color-primary-bg-active'], 'interactionPrimarySoft');
assert.equal(defaultLightTokens.surfaceContainer, '#FFFFFF');
assert.equal(defaultDarkTokens.surfaceContainer, '#141414');
assert.notEqual(defaultDarkTokens.surfaceContainer, '#FFFFFF');
assert.equal(defaultDarkTokens.textPrimary, 'rgba(255,255,255, 0.9)');
assert.equal(defaultDarkTokens.fillSubtle, 'rgba(255,255,255, 0.04)');
assert.equal(defaultDarkTokens.interactionPrimarySoft, '#172637');
assert.notEqual(defaultDarkTokens.fillSubtle, '#FFFFFF');
assert.notEqual(defaultDarkTokens.interactionPrimarySoft, '#FFFFFF');

const css = createThemeCss(defaultTheme);
assert.match(css, /html\.dark\{[^}]*--color-bg:var\(--theme-color-surface-container\)/);
assert.match(css, /html\.dark\{[^}]*--theme-color-surface-container:#141414/);
assert.match(css, /html\.dark\{[^}]*--color-fill-1:var\(--theme-color-fill-subtle\)/);
assert.match(css, /html\.dark\{[^}]*--theme-color-fill-subtle:rgba\(255,255,255, 0\.04\)/);
assert.match(css, /html\.dark\{[^}]*--theme-color-text-primary:rgba\(255,255,255, 0\.9\)/);
assert.match(css, /html\.dark\{[^}]*--color-primary-bg-active:var\(--theme-color-interaction-primary-soft\)/);
assert.match(css, /html\.dark\{[^}]*--theme-color-interaction-primary-soft:#172637/);

console.log('system-manager dark theme surface contract passed');
