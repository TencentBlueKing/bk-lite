import { describe, expect, it } from 'vitest';

import { buildOpsAnalysisViewHref } from '../viewHref';

describe('ops-analysis view href', () => {
  it('keeps screen when replacing type and id', () => {
    expect(buildOpsAnalysisViewHref('dashboard', '7', '?screen=true')).toBe(
      '/ops-analysis/view?screen=true&type=dashboard&id=7',
    );
    expect(
      buildOpsAnalysisViewHref('screen', 's1', '?type=topology&id=t1&screen=true'),
    ).toBe('/ops-analysis/view?type=screen&id=s1&screen=true');
    expect(buildOpsAnalysisViewHref('dashboard', '7', '?screen=1')).toBe(
      '/ops-analysis/view?screen=1&type=dashboard&id=7',
    );
  });

  it('does not add screen when the current query is not screen mode', () => {
    expect(buildOpsAnalysisViewHref('dashboard', '7', '')).toBe(
      '/ops-analysis/view?type=dashboard&id=7',
    );
    expect(buildOpsAnalysisViewHref('dashboard', '7', '?type=topology&id=t1')).toBe(
      '/ops-analysis/view?type=dashboard&id=7',
    );
  });
});
