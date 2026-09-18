import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const pageSource = readFileSync(
  new URL('../src/app/system-manager/(pages)/channel/im-notification/page.tsx', import.meta.url),
  'utf8',
);

assert.match(
  pageSource,
  /flex h-full min-h-0 min-w-0 w-full max-w-full flex-col overflow-hidden/,
  'table shell must shrink in the PageLayout overflow pane instead of growing with cell min-content',
);
assert.match(
  pageSource,
  /min-h-0 min-w-0 flex-1 overflow-hidden/,
  'CustomTable parent must clip sideways growth from column fill + scrollbar',
);
assert.doesNotMatch(
  pageSource,
  /<div className="flex h-full">/,
  'row flex without min-w-0 lets the table set the pane min-width and stretch infinitely',
);
assert.doesNotMatch(
  pageSource,
  /<div className="min-h-0 flex-1 bg-\[var\(--color-bg\)\] p-1">/,
  'unconstrained flex-1 table host is the previous infinite-width parent',
);
assert.match(
  pageSource,
  /className="flex min-w-0 items-center gap-2"/,
  'integration/latest-sync cells must allow truncation',
);
assert.match(pageSource, /EllipsisWithTooltip/);
assert.doesNotMatch(
  pageSource,
  /<div className="flex items-center gap-2">/,
  'nowrap flex cells without min-w-0 become the table min-content width',
);

console.log('im-notification table overflow contract passed');
