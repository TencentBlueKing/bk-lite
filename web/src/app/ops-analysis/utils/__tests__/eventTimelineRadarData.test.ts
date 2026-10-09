import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_EVENT_TIMELINE_MAX_ITEMS,
  parseEventTimelineItems,
  validateEventTimelinePayload,
} from '../eventTimeline';
import { normalizeRadarRange, resolveRadarSeriesData } from '../radarData';

test('event timeline applies desc sort and overflow truncation', () => {
  const parsed = parseEventTimelineItems(
    [
      { time: '2026-08-01 09:00:00', title: 'A' },
      { time: '2026-08-01 10:00:00', title: 'B' },
    ],
    {
      sortOrder: 'desc',
      maxItems: 1,
    },
  );

  assert.equal(parsed.total, 2);
  assert.equal(parsed.truncated, true);
  assert.equal(parsed.items.length, 1);
  assert.equal(parsed.items[0]?.title, 'B');
});

test('event timeline keeps latest N when sort order is asc', () => {
  const parsed = parseEventTimelineItems(
    [
      { time: '2026-08-01 09:00:00', title: 'A' },
      { time: '2026-08-01 10:00:00', title: 'B' },
    ],
    {
      sortOrder: 'asc',
      maxItems: 1,
    },
  );
  assert.equal(parsed.items.length, 1);
  assert.equal(parsed.items[0]?.title, 'B');
});

test('event timeline skips rows missing required fields without failing others', () => {
  const parsed = parseEventTimelineItems([
    { time: '2026-08-01 09:00:00' },
    { title: '缺少时间' },
    { time: '2026-08-01 10:00:00', title: '有效事件' },
  ]);
  assert.equal(parsed.total, 1);
  assert.equal(parsed.items[0]?.title, '有效事件');
});

test('event timeline renders optional fields when present', () => {
  const parsed = parseEventTimelineItems([
    {
      time: '2026-08-01 09:00:00',
      title: 'A',
      description: 'detail',
      category: '网络',
      status: 'warning',
      link: 'https://example.com',
    },
  ]);
  assert.deepEqual(parsed.items[0], {
    time: '2026-08-01 09:00:00',
    title: 'A',
    description: 'detail',
    category: '网络',
    status: 'warning',
    link: 'https://example.com',
  });
});

test('event timeline default maxItems is safety cap', () => {
  const rows = Array.from({ length: DEFAULT_EVENT_TIMELINE_MAX_ITEMS + 2 }).map(
    (_, index) => ({
      time: `2026-08-01 10:${String(index).padStart(2, '0')}:00`,
      title: `E${index}`,
    }),
  );
  const parsed = parseEventTimelineItems(rows);
  assert.equal(parsed.items.length, DEFAULT_EVENT_TIMELINE_MAX_ITEMS);
  assert.equal(parsed.truncated, true);
});

test('event timeline normalizes unknown and neutral status explicitly', () => {
  const parsed = parseEventTimelineItems(
    [
      { time: '2026-08-01 09:00:00', title: 'A', status: 'neutral' },
      { time: '2026-08-01 10:00:00', title: 'B', status: 'custom-state' },
      { time: '2026-08-01 11:00:00', title: 'C', status: 1 },
    ],
    { sortOrder: 'asc' },
  );
  assert.equal(parsed.items[0]?.status, 'neutral');
  assert.equal(parsed.items[1]?.status, 'unknown');
  assert.equal(parsed.items[2]?.status, 'unknown');
});

test('empty items envelope is valid empty payload', () => {
  assert.equal(validateEventTimelinePayload({ items: [] }).isValid, true);
  assert.equal(validateEventTimelinePayload([]).isValid, true);
  assert.equal(validateEventTimelinePayload(null).isValid, true);
});

test('all unparseable events fail structure validation', () => {
  const result = validateEventTimelinePayload({
    items: [
      { time: '2026-08-01 09:00:00' },
      { title: '缺少时间' },
      { foo: 1 },
    ],
  });
  assert.equal(result.isValid, false);
  assert.equal(result.message, 'dashboard.eventTimelineStructureMismatch');
});

test('radar resolves [{name,value}] mode', () => {
  const series = resolveRadarSeriesData([
    { name: 'CPU', value: 80 },
    { name: 'Memory', value: 60 },
    { name: 'Disk', value: 40 },
  ]);
  assert.deepEqual(series.indicatorLabels, ['CPU', 'Memory', 'Disk']);
  assert.deepEqual(series.indicatorValues, [80, 60, 40]);
});

test('radar resolves object mode with indicators', () => {
  const series = resolveRadarSeriesData(
    { cpu: 70, memory: 55, disk: 45 },
    {
      indicators: [
        { key: 'cpu', label: 'CPU' },
        { key: 'memory', label: '内存' },
        { key: 'disk' },
      ],
    },
  );
  assert.deepEqual(series.indicatorLabels, ['CPU', '内存', 'disk']);
  assert.deepEqual(series.indicatorValues, [70, 55, 45]);
});

test('radar marks multi-series object input as unsupported', () => {
  const series = resolveRadarSeriesData({
    hostA: [
      { name: 'CPU', value: 70 },
      { name: 'Memory', value: 55 },
    ],
    hostB: [
      { name: 'CPU', value: 60 },
      { name: 'Memory', value: 48 },
    ],
  });
  assert.equal(series.unsupported, 'multi_series');
  assert.deepEqual(series.indicatorLabels, []);
});

test('event timeline reads saved columns and skips rows missing time or title', () => {
  const parsed = parseEventTimelineItems(
    [
      { occurred_at: 'not-a-date', headline: 'A', note: 'detail', state: 'custom' },
      { occurred_at: '', headline: 'B' },
      { headline: 'C' },
    ],
    {
      sortOrder: 'asc',
      timeField: 'occurred_at',
      titleField: 'headline',
      descriptionField: 'note',
      statusField: 'state',
    },
  );

  assert.equal(parsed.total, 1);
  assert.equal(parsed.items[0]?.time, 'not-a-date');
  assert.equal(parsed.items[0]?.title, 'A');
  assert.equal(parsed.items[0]?.description, 'detail');
  assert.equal(parsed.items[0]?.status, 'unknown');
  assert.equal(parsed.items[0]?.category, undefined);
});

test('radar array mapping reads selected columns and skips incomplete numbers', () => {
  const series = resolveRadarSeriesData(
    [
      { metric: 'CPU', reading: '80' },
      { metric: 'Memory', reading: '1abc' },
      { metric: 'Disk', reading: 40 },
    ],
    { arrayNameField: 'metric', arrayValueField: 'reading' },
  );

  assert.deepEqual(series.indicatorLabels, ['CPU', 'Disk']);
  assert.deepEqual(series.indicatorValues, [80, 40]);
});

test('radar object mode ignores array field mapping', () => {
  const series = resolveRadarSeriesData(
    { cpu: 70, memory: 55, disk: 45 },
    {
      arrayNameField: 'name',
      arrayValueField: 'value',
      indicators: [
        { key: 'cpu', label: 'CPU' },
        { key: 'memory', label: '内存' },
        { key: 'disk' },
      ],
    },
  );

  assert.deepEqual(series.indicatorLabels, ['CPU', '内存', 'disk']);
});

test('radar min/max uses defaults and supports override', () => {
  assert.deepEqual(normalizeRadarRange(undefined), { min: 0, max: 100 });
  assert.deepEqual(normalizeRadarRange({ min: 10, max: 50 }), {
    min: 10,
    max: 50,
  });
  assert.deepEqual(
    normalizeRadarRange({}, { gaugeMin: 5, gaugeMax: 90 }),
    { min: 5, max: 90 },
  );
  assert.deepEqual(
    normalizeRadarRange({ min: 20, max: 80 }, { gaugeMin: 5, gaugeMax: 90 }),
    { min: 20, max: 80 },
  );
});
