import { describe, expect, it } from 'vitest';

import {
  isCanvasDataSourceLookupDecided,
  type DataSourceLookupStatus,
} from '@/app/ops-analysis/utils/widgetRequestVersion';

describe('isCanvasDataSourceLookupDecided', () => {
  it.each<[DataSourceLookupStatus, boolean]>([
    ['idle', false],
    ['loading', false],
    ['success', true],
    ['error', true],
  ])('treats %s as decided=%s', (status, decided) => {
    expect(isCanvasDataSourceLookupDecided(status)).toBe(decided);
  });
});
