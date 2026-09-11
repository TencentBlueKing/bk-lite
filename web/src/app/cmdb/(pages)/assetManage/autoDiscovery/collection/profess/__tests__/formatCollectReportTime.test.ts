import { describe, expect, it } from 'vitest';
import dayjs from 'dayjs';

import { formatCollectReportTime } from '../formatCollectReportTime';

describe('formatCollectReportTime', () => {
  it('treats config-file version millis as unix time instead of year 1789', () => {
    const version = '1789033801432';
    expect(dayjs(version).format('YYYY-MM-DD')).toBe('1789-04-07');
    expect(formatCollectReportTime(version)).toBe(
      dayjs(1789033801432).format('YYYY-MM-DD HH:mm:ss')
    );
    expect(formatCollectReportTime(version).startsWith('1789')).toBe(false);
  });

  it('keeps ISO report times parseable', () => {
    expect(formatCollectReportTime('2026-09-10T09:50:01+00:00')).toBe(
      dayjs('2026-09-10T09:50:01+00:00').format('YYYY-MM-DD HH:mm:ss')
    );
  });
});
