import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

const HALF_HOUR_MS = 30 * 60 * 1000;
const ONE_MINUTE_MS = 60 * 1000;

/**
 * 告警 API 无时区墙钟：`YYYY-MM-DD HH:mm:ss`（可带小数秒、`T` 分隔）。
 * DRF 在 activate(user_tz) 后按**用户墙钟**吐出，须用同一时区解析；未传时区时回落 UTC
 * （与后端 TIME_ZONE=UTC / 未 activate 的 API Key 路径一致）。
 */
const ALARM_NAIVE_WALL_TIME =
  /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?$/;

export interface AlarmApmReplayWindow {
  startedAt: string;
  endedAt: string;
}

export interface AlarmApmReplayTimeSource {
  first_event_time?: unknown;
  last_event_time?: unknown;
  created_at?: unknown;
  /** 容错：若运行时被转成 camelCase 仍能锚到发生时段 */
  firstEventTime?: unknown;
  lastEventTime?: unknown;
  createdAt?: unknown;
}

/** 将 now 按 UTC 分钟向下取整，避免 clamp 后 endedAt 随每次渲染微变。 */
export function floorNowToUtcMinute(now: Date): Date {
  const ms = now.getTime();
  if (!Number.isFinite(ms)) return now;
  return new Date(Math.floor(ms / ONE_MINUTE_MS) * ONE_MINUTE_MS);
}

export function parseAlarmApmTime(
  value: unknown,
  timeZone: string = 'UTC',
): Date | null {
  if (value instanceof Date) {
    return Number.isFinite(value.getTime()) ? value : null;
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? new Date(value) : null;
  }
  if (typeof value !== 'string') return null;
  const raw = value.trim();
  if (!raw) return null;

  const wall = raw.match(ALARM_NAIVE_WALL_TIME);
  if (wall) {
    const zone = timeZone || 'UTC';
    const local = dayjs.tz(
      `${wall[1]}-${wall[2]}-${wall[3]} ${wall[4]}:${wall[5]}:${wall[6]}`,
      'YYYY-MM-DD HH:mm:ss',
      zone,
    );
    if (!local.isValid()) return null;
    return local.toDate();
  }

  // 已带 Z / 数值 offset 的 ISO：标准解析。
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? new Date(ms) : null;
}

function readTimeField(
  alert: AlarmApmReplayTimeSource,
  snake: keyof AlarmApmReplayTimeSource,
  camel: keyof AlarmApmReplayTimeSource,
): unknown {
  const snakeVal = alert[snake];
  if (snakeVal !== undefined && snakeVal !== null && snakeVal !== '') {
    return snakeVal;
  }
  return alert[camel];
}

/**
 * 告警 APM 嵌入默认查询窗：有发生时段锚点时，先将未来锚点夹到 now，再取 ±30m
 *（endedAt 封顶 now）；无有效锚点时返回 null，由 widget 回落 now−1h。
 * 夹窗后仍无效时给 [now−30m, now]，避免静默回落 now−1h。
 */
export function buildAlarmApmReplayWindow(
  alert: AlarmApmReplayTimeSource | null | undefined,
  now: Date = new Date(),
  timeZone: string = 'UTC',
): AlarmApmReplayWindow | null {
  if (!alert) return null;

  const zone = timeZone || 'UTC';
  const anchor =
    parseAlarmApmTime(
      readTimeField(alert, 'first_event_time', 'firstEventTime'),
      zone,
    ) ||
    parseAlarmApmTime(
      readTimeField(alert, 'last_event_time', 'lastEventTime'),
      zone,
    ) ||
    parseAlarmApmTime(readTimeField(alert, 'created_at', 'createdAt'), zone);
  if (!anchor) return null;

  const nowFloorMs = floorNowToUtcMinute(now).getTime();
  // 锚点落在未来时先夹到 now 再开窗，避免略微未来的锚点少切一段时间。
  const anchorMs = Math.min(anchor.getTime(), nowFloorMs);
  let started = new Date(anchorMs - HALF_HOUR_MS);
  let ended = new Date(anchorMs + HALF_HOUR_MS);

  if (ended.getTime() > nowFloorMs) {
    ended = new Date(nowFloorMs);
  }
  // 夹窗后仍无效（例如 now 本身不可用）：给 [now−30m, now]，避免 widget 静默 now−1h。
  if (started.getTime() >= ended.getTime()) {
    ended = new Date(nowFloorMs);
    started = new Date(nowFloorMs - HALF_HOUR_MS);
  }
  if (started.getTime() >= ended.getTime()) {
    return null;
  }

  return {
    startedAt: started.toISOString(),
    endedAt: ended.toISOString(),
  };
}
