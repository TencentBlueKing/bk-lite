import { describe, expect, it } from 'vitest';

import {
  buildAlarmApmReplayWindow,
  floorNowToUtcMinute,
  parseAlarmApmTime,
} from '../alarmApmReplayWindow';

describe('parseAlarmApmTime', () => {
  it('treats naive alarm wall-clock as the given zone, defaulting to UTC', () => {
    expect(parseAlarmApmTime('2026-09-16 10:00:00')?.toISOString()).toBe(
      '2026-09-16T10:00:00.000Z',
    );
    expect(parseAlarmApmTime('2026-09-16T10:00:00')?.toISOString()).toBe(
      '2026-09-16T10:00:00.000Z',
    );
    // 鉴权 activate(Asia/Shanghai) 后 API 吐出的用户墙钟
    expect(
      parseAlarmApmTime('2026-09-17 10:49:34', 'Asia/Shanghai')?.toISOString(),
    ).toBe('2026-09-17T02:49:34.000Z');
  });

  it('parses ISO with Z or numeric offset via standard rules', () => {
    expect(parseAlarmApmTime('2026-09-16T02:00:00.000Z')?.toISOString()).toBe(
      '2026-09-16T02:00:00.000Z',
    );
    expect(parseAlarmApmTime('2026-09-16T10:00:00+08:00')?.toISOString()).toBe(
      '2026-09-16T02:00:00.000Z',
    );
  });

  it('rejects empty or illegal values', () => {
    expect(parseAlarmApmTime('')).toBeNull();
    expect(parseAlarmApmTime('not-a-time')).toBeNull();
    expect(parseAlarmApmTime(null)).toBeNull();
  });
});

describe('buildAlarmApmReplayWindow', () => {
  const now = new Date('2026-09-17T12:00:00.000Z');

  it('prefers first_event_time then last_event_time then created_at with UTC ±30m', () => {
    expect(
      buildAlarmApmReplayWindow(
        {
          first_event_time: '2026-09-16 10:00:00',
          last_event_time: '2026-09-16 11:00:00',
          created_at: '2026-09-16 12:00:00',
        },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-16T09:30:00.000Z',
      endedAt: '2026-09-16T10:30:00.000Z',
    });

    expect(
      buildAlarmApmReplayWindow(
        {
          first_event_time: null,
          last_event_time: '2026-09-16T11:00:00.000Z',
          created_at: '2026-09-16T12:00:00.000Z',
        },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-16T10:30:00.000Z',
      endedAt: '2026-09-16T11:30:00.000Z',
    });

    expect(
      buildAlarmApmReplayWindow(
        {
          first_event_time: '',
          last_event_time: 'bad',
          created_at: '2026-09-16T12:00:00.000Z',
        },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-16T11:30:00.000Z',
      endedAt: '2026-09-16T12:30:00.000Z',
    });
  });

  it('interprets API naive wall-clock in the user timezone before ±30m', () => {
    // DB 02:49:34Z；activate(Asia/Shanghai) 后列表/详情为 10:49:34
    expect(
      buildAlarmApmReplayWindow(
        { first_event_time: '2026-09-17 10:49:34' },
        new Date('2026-09-17T06:57:00.000Z'),
        'Asia/Shanghai',
      ),
    ).toEqual({
      startedAt: '2026-09-17T02:19:34.000Z',
      endedAt: '2026-09-17T03:19:34.000Z',
    });
  });

  it('caps endedAt at floored now; clamps future anchors to now instead of null', () => {
    expect(
      buildAlarmApmReplayWindow(
        { first_event_time: '2026-09-17T11:50:00.000Z' },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-17T11:20:00.000Z',
      endedAt: '2026-09-17T12:00:00.000Z',
    });

    // 略微未来：先夹锚点到 now 再 ±30m，而不是只截 endedAt。
    expect(
      buildAlarmApmReplayWindow(
        { first_event_time: '2026-09-17T12:10:00.000Z' },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-17T11:30:00.000Z',
      endedAt: '2026-09-17T12:00:00.000Z',
    });

    expect(buildAlarmApmReplayWindow({}, now)).toBeNull();
    expect(buildAlarmApmReplayWindow(null, now)).toBeNull();
    // 整段 ±30m 在未来：夹到 now → [now−30m, now]，避免 widget 静默 now−1h
    expect(
      buildAlarmApmReplayWindow(
        { first_event_time: '2026-09-17T13:00:00.000Z' },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-17T11:30:00.000Z',
      endedAt: '2026-09-17T12:00:00.000Z',
    });
  });

  it('keeps endedAt stable within the same UTC minute when clamping', () => {
    const alert = { first_event_time: '2026-09-17 11:50:00' };
    const first = buildAlarmApmReplayWindow(
      alert,
      new Date('2026-09-17T12:00:12.345Z'),
    );
    const second = buildAlarmApmReplayWindow(
      alert,
      new Date('2026-09-17T12:00:59.999Z'),
    );
    expect(first).toEqual({
      startedAt: '2026-09-17T11:20:00.000Z',
      endedAt: '2026-09-17T12:00:00.000Z',
    });
    expect(second).toEqual(first);
  });

  it('accepts camelCase aliases and Date instances', () => {
    expect(
      buildAlarmApmReplayWindow(
        { firstEventTime: '2026-09-16 10:00:00' },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-16T09:30:00.000Z',
      endedAt: '2026-09-16T10:30:00.000Z',
    });
    expect(
      buildAlarmApmReplayWindow(
        { first_event_time: new Date('2026-09-16T10:00:00.000Z') },
        now,
      ),
    ).toEqual({
      startedAt: '2026-09-16T09:30:00.000Z',
      endedAt: '2026-09-16T10:30:00.000Z',
    });
  });
});

describe('floorNowToUtcMinute', () => {
  it('drops seconds and milliseconds in UTC', () => {
    expect(
      floorNowToUtcMinute(new Date('2026-09-17T12:00:45.123Z')).toISOString(),
    ).toBe('2026-09-17T12:00:00.000Z');
  });
});
