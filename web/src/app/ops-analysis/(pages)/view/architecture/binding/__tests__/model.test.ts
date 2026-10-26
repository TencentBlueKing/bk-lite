import { describe, expect, it } from 'vitest';
import {
  BINDING_SEARCH_PAGE_SIZE,
  appendBindingHits,
  bindingDisplay,
  bindingModelLabel,
  bindingPageFromTotal,
  bindingSearchMode,
  findSelectionBinding,
  flattenModelOptions,
  normalizeBindingSearchHits,
  architectureSearchPage,
  sliceBindingPage,
} from '../model';

const views = [
  {
    id: 'view-1',
    items: [
      { id: 'node-1', tile: { x: 1, y: 1 }, bkBinding: { inst_uuid: 'uuid-host', model_id: 'host' } },
      { id: 'node-2', tile: { x: 2, y: 2 } },
    ],
    rectangles: [
      {
        id: 'rect-1',
        from: { x: 0, y: 0 },
        to: { x: 4, y: 4 },
        bkBinding: { inst_uuid: 'uuid-room', model_id: 'room' },
        bkFollowAlert: true,
      },
      { id: 'rect-2', from: { x: 5, y: 5 }, to: { x: 6, y: 6 } },
    ],
  },
];

describe('architecture binding model', () => {
  it('reads icon bindings and ignores a rectangle resource binding', () => {
    expect(findSelectionBinding(views, { type: 'ITEM', id: 'node-1' })).toEqual({
      binding: { inst_uuid: 'uuid-host', model_id: 'host' },
      followAlert: false,
    });
    expect(findSelectionBinding(views, { type: 'ITEM', id: 'node-2' })?.binding).toBeNull();
    expect(findSelectionBinding(views, { type: 'RECTANGLE', id: 'rect-1' })).toEqual({
      binding: null,
      followAlert: true,
    });
    expect(findSelectionBinding(views, { type: 'RECTANGLE', id: 'rect-2' })?.followAlert).toBe(false);
    expect(findSelectionBinding(views, { type: 'CONNECTOR', id: 'line-1' })).toBeNull();
  });

  it('normalizes search hits and keeps name and ip', () => {
    expect(normalizeBindingSearchHits([
      { inst_uuid: 'u1', model_id: 'host', inst_name: 'web-01', ip_addr: '10.0.0.1' },
      { inst_uuid: 'u2', model_id: 'switch', inst_name: 'sw-01', ip_addr: '10.0.0.2' },
      { inst_name: 'missing-id' },
    ])).toEqual([
      { inst_uuid: 'u1', model_id: 'host', inst_name: 'web-01', ip_addr: '10.0.0.1' },
      { inst_uuid: 'u2', model_id: 'switch', inst_name: 'sw-01', ip_addr: '10.0.0.2' },
    ]);
  });

  it('hides stale names for invalid and forbidden resources', () => {
    expect(bindingDisplay({
      inst_uuid: 'u1',
      status: 'invalid',
      alert_count: 0,
      max_level: null,
      monitor_id: '',
      model_id: 'host',
      inst_name: 'old-name',
    }, '主机').blocked).toBe('invalid');
    expect(bindingDisplay({
      inst_uuid: 'u1',
      status: 'forbidden',
      alert_count: 0,
      max_level: null,
      monitor_id: '',
      model_id: 'host',
      inst_name: 'old-name',
    }, '主机').name).toBe('');
    expect(bindingDisplay({
      inst_uuid: 'u1',
      status: 'normal',
      alert_count: 0,
      max_level: null,
      monitor_id: 'm1',
      model_id: 'host',
      inst_name: 'web-01',
    }, '主机')).toEqual({ name: 'web-01', typeName: '主机', blocked: null });
  });

  it('lists a selected type without a keyword and pages the results', () => {
    expect(BINDING_SEARCH_PAGE_SIZE).toBeLessThanOrEqual(100);
    expect(bindingSearchMode('', '')).toBe('idle');
    expect(bindingSearchMode('  ', 'host')).toBe('by-type');
    expect(bindingSearchMode('web', 'host')).toBe('by-model-text');
    expect(bindingSearchMode('web', '')).toBe('fulltext');

    const hits = [
      { inst_uuid: 'u1', model_id: 'host', inst_name: 'web-01', ip_addr: '10.0.0.1' },
    ];
    expect(bindingPageFromTotal(hits, 1, 30, 120)).toEqual({
      hits,
      hasMore: true,
      total: 120,
    });
    expect(bindingPageFromTotal(hits, 4, 30, 120).hasMore).toBe(false);
    expect(bindingPageFromTotal([], 1, 30, 120).hasMore).toBe(false);
  });

  it('pages ops-analysis resource search and slices cross-model hits locally', () => {
    const listed = architectureSearchPage({
      mode: 'by-type',
      hits: [{ inst_uuid: 'u1', model_id: 'host', inst_name: 'web-01', ip_addr: '10.0.0.1', password: 'nope' }],
      total: 80,
      page: 1,
      page_size: 30,
    }, 1, 30);
    expect(listed).toEqual({
      hits: [{ inst_uuid: 'u1', model_id: 'host', inst_name: 'web-01', ip_addr: '10.0.0.1' }],
      hasMore: true,
      total: 80,
    });

    const all = Array.from({ length: 5 }, (_, index) => ({
      inst_uuid: `u${index}`,
      inst_name: `n${index}`,
      ip_addr: '',
      model_id: 'host',
    }));
    expect(architectureSearchPage({ mode: 'fulltext', hits: all, total: all.length }, 2, 2)).toEqual({
      hits: all.slice(2, 4),
      hasMore: true,
      total: 5,
    });
  });

  it('slices a full keyword result into pages and skips repeated rows', () => {
    const all = Array.from({ length: 5 }, (_, index) => ({
      inst_uuid: `u${index}`,
      inst_name: `n${index}`,
      ip_addr: '',
      model_id: 'host',
    }));
    expect(sliceBindingPage(all, 1, 2)).toEqual({ hits: all.slice(0, 2), hasMore: true, total: 5 });
    expect(sliceBindingPage(all, 3, 2)).toEqual({ hits: all.slice(4), hasMore: false, total: 5 });
    expect(appendBindingHits(all.slice(0, 2), all.slice(1, 3)).map((hit) => hit.inst_uuid))
      .toEqual(['u0', 'u1', 'u2']);
  });

  it('uses the model list display name on search rows', () => {
    const models = flattenModelOptions([
      { model_id: 'host', model_name: '主机' },
      { model_id: 'switch', model_name: '  ' },
    ]);
    expect(bindingModelLabel(models, 'host')).toBe('主机');
    expect(bindingModelLabel(models, 'switch')).toBe('switch');
    expect(bindingModelLabel(models, 'missing')).toBe('missing');
  });

  it('flattens grouped model lists', () => {
    expect(flattenModelOptions([
      { model_id: 'host', model_name: '主机' },
      { list: [{ model_id: 'switch', model_name: '交换机' }] },
    ])).toEqual([
      { model_id: 'host', model_name: '主机' },
      { model_id: 'switch', model_name: '交换机' },
    ]);
  });

  it('keeps a configured model icon so inserted nodes can match the palette', () => {
    expect(flattenModelOptions([
      { model_id: 'mysql', model_name: 'MySQL', icn: ' cc-mysql_数据库 ' },
      { model_id: 'host', model_name: '主机', icn: '   ' },
    ])).toEqual([
      { model_id: 'mysql', model_name: 'MySQL', icn: 'cc-mysql_数据库' },
      { model_id: 'host', model_name: '主机' },
    ]);
  });
});
