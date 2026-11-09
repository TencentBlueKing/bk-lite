import { describe, expect, it } from 'vitest';

import { OPTIONS_QUERY_INVALID } from '@/app/ops-analysis/utils/optionsQueryParamRefs';
import {
  canonicalizeOptionsQueryRef,
  formatOptionsQueryCandidateLabel,
  listOptionsQueryCandidates,
  readComponentOptionsQueryUpstream,
  resolveOptionsQueryChoice,
  type OptionsQueryCandidateChoice,
  type OptionsQueryEditorContext,
} from '@/app/ops-analysis/utils/optionsQueryCandidates';

const translate = (key: string, _fallback?: string, values?: Record<string, string>) => {
  const text: Record<string, string> = {
    'paramInput.dynamic.originGlobalFilter': '全局筛选',
    'paramInput.dynamic.originComponentParam': '组件参数',
    'paramInput.dynamic.refChoice': '{origin} · {name}',
    'paramInput.dynamic.refChoiceWithKey': '{origin} · {name} ({key})',
    'paramInput.dynamic.refChoiceWithHint': '{origin} · {name} · {hint}',
  };
  return (text[key] || key).replace(/\{(\w+)\}/g, (_, name) => values?.[name] ?? '');
};

const labelOf = (choice: OptionsQueryCandidateChoice, choices: OptionsQueryCandidateChoice[]) => (
  formatOptionsQueryCandidateLabel(choice, choices, translate)
);

describe('options query candidates', () => {
  const componentContext = (): OptionsQueryEditorContext => ({
    scope: 'component',
    self: { key: 'device_id' },
    componentParams: [
      { name: 'device_id', label: '设备', type: 'string', filterType: 'params' },
      { name: 'zone_id', label: '区域', type: 'string', filterType: 'params' },
      { name: 'site_id', label: '机房', type: 'string', filterType: 'filter', value: 'local-room' },
      { name: 'limit', label: '条数', type: 'number', filterType: 'fixed' },
    ],
    globalFilters: [
      { id: 'org__string', key: 'org', label: '组织', type: 'string', enabled: true },
      { id: 'site_id__string', key: 'site_id', label: '监控对象', type: 'string', enabled: true },
      { id: 'closed__string', key: 'closed', label: '停用', type: 'string', enabled: false },
      { id: 'window__timeRange', key: 'window', label: '时间', type: 'timeRange', enabled: true },
    ],
  });

  it('lets a component param reference this card and canvas filters, not itself or the wrong type', () => {
    const choices = listOptionsQueryCandidates({
      context: componentContext(),
      expectedType: 'string',
    });
    expect(choices.map((item) => item.ref)).toEqual([
      'site_id',
      'zone_id',
      'org__string',
      'site_id__string',
    ]);
    expect(choices.map((item) => item.origin)).toEqual([
      'componentParam',
      'componentParam',
      'globalFilter',
      'globalFilter',
    ]);
    expect(choices.find((item) => item.ref === 'site_id__string')?.displayName).toBe('监控对象');
    expect(labelOf(choices.find((item) => item.ref === 'site_id__string')!, choices)).toBe('全局筛选 · 监控对象');
    expect(labelOf(choices.find((item) => item.ref === 'zone_id')!, choices)).toBe('组件参数 · 区域');
  });

  it('does not follow the order the filters were passed in', () => {
    const context = componentContext();
    context.globalFilters = [...(context.globalFilters ?? [])].reverse();
    context.componentParams = [...(context.componentParams ?? [])].reverse();
    const choices = listOptionsQueryCandidates({ context, expectedType: 'string' });
    expect(choices.map((item) => item.key)).toEqual(['site_id', 'zone_id', 'org', 'site_id']);
  });

  it('keeps global filters inside the canvas and ignores component params', () => {
    const choices = listOptionsQueryCandidates({
      context: {
        scope: 'globalFilter',
        self: { id: 'device_id__string', key: 'device_id' },
        componentParams: [
          { name: 'secret', label: '别的组件', type: 'string', filterType: 'params' },
        ],
        globalFilters: [
          { id: 'device_id__string', key: 'device_id', label: '设备', type: 'string' },
          { id: 'site_id__string__bbbbbbbb', key: 'site_id', label: '机房', type: 'string', sourceHint: 'monitor/rooms' },
          { id: 'site_id__string__aaaaaaaa', key: 'site_id', label: '机房', type: 'string', sourceHint: 'cmdb/rooms' },
          { id: 'count__number', key: 'count', label: '数量', type: 'number' },
        ],
      },
      expectedType: 'string',
    });
    expect(choices.map((item) => ({ ref: item.ref, key: item.key }))).toEqual([
      { ref: 'site_id__string__aaaaaaaa', key: 'site_id' },
      { ref: 'site_id__string__bbbbbbbb', key: 'site_id' },
    ]);
    expect(labelOf(choices[0], choices)).toBe('全局筛选 · 机房 · cmdb/rooms');
    expect(choices.some((item) => item.ref === 'secret' || item.key === 'device_id')).toBe(false);
  });

  it('still lists a candidate that would cycle or exceed three parameters', () => {
    const choices = listOptionsQueryCandidates({
      context: {
        scope: 'globalFilter',
        self: { id: 'b', key: 'b' },
        globalFilters: [
          { id: 'a', key: 'a', label: '甲', type: 'string', queryParams: { x: { ref: 'b' } } },
          { id: 'c', key: 'c', label: '丙', type: 'string' },
          { id: 'd', key: 'd', label: '丁', type: 'string', queryParams: { x: { ref: 'e' } } },
          { id: 'e', key: 'e', label: '戊', type: 'string', queryParams: { x: { ref: 'f' } } },
          { id: 'f', key: 'f', label: '己', type: 'string' },
        ],
      },
      expectedType: 'string',
    });
    expect(choices.map((item) => item.ref)).toEqual(['a', 'c', 'd', 'e', 'f']);
  });

  it('lists the instance a detail param can reference after object, metric, and instance', () => {
    const choices = listOptionsQueryCandidates({
      context: {
        scope: 'component',
        self: { key: 'detail_id' },
        componentParams: [
          { name: 'object_id', label: '对象', type: 'string' },
          {
            name: 'metric_id',
            label: '指标',
            type: 'string',
            queryParams: { object_id: { ref: 'object_id' } },
          },
          {
            name: 'instance_id',
            label: '实例',
            type: 'string',
            queryParams: { metric_id: { ref: 'metric_id' } },
          },
          { name: 'detail_id', label: '明细', type: 'string' },
        ],
      },
      expectedType: 'string',
    });
    expect(choices.map((item) => item.ref)).toEqual(['instance_id', 'metric_id', 'object_id']);
    expect(choices.some((item) => item.ref === 'detail_id')).toBe(false);
  });

  it('keeps a component param ref when a global filter uses the same key', () => {
    const context: OptionsQueryEditorContext = {
      scope: 'component',
      self: { key: 'metric_id' },
      componentParams: [
        { name: 'object_id', label: '监控对象', type: 'string', filterType: 'params' },
        { name: 'metric_id', label: '指标', type: 'string', filterType: 'params' },
      ],
      globalFilters: [
        { id: 'object_id__string', key: 'object_id', label: '监控对象', type: 'string', enabled: true },
      ],
    };
    expect(canonicalizeOptionsQueryRef('object_id', context)).toBe('object_id');
    expect(canonicalizeOptionsQueryRef('object_id__string', context)).toBe('object_id__string');
    expect(canonicalizeOptionsQueryRef('site_id', {
      scope: 'globalFilter',
      self: { id: 'device_id__string', key: 'device_id' },
      globalFilters: [
        { id: 'site_id__string', key: 'site_id', label: '监控对象', type: 'string' },
      ],
    })).toBe('site_id__string');

    const choices = listOptionsQueryCandidates({ context, expectedType: 'string' });
    expect(resolveOptionsQueryChoice('object_id', choices, context)?.origin).toBe('componentParam');
    expect(resolveOptionsQueryChoice('object_id__string', choices, context)?.origin).toBe('globalFilter');
    expect(labelOf(resolveOptionsQueryChoice('object_id', choices, context)!, choices)).toBe('组件参数 · 监控对象');
    expect(labelOf(resolveOptionsQueryChoice('object_id__string', choices, context)!, choices)).toBe('全局筛选 · 监控对象');
  });

  it('reads a component param ref from the card and a filter id from the canvas', () => {
    const definitions = [
      { id: 'object_id__string', key: 'object_id', type: 'string', enabled: true },
    ];
    const componentParams = [
      { name: 'object_id', type: 'string', filterType: 'params' as const, value: 'local-object' },
    ];
    const readFilterValue = (id: string) => (id === 'object_id__string' ? 'canvas-object' : undefined);
    expect(readComponentOptionsQueryUpstream({
      ref: 'object_id',
      componentParams,
      definitions,
      filterBindings: { object_id__string: true },
      readFilterValue,
    })).toBe('local-object');
    expect(readComponentOptionsQueryUpstream({
      ref: 'object_id__string',
      componentParams,
      definitions,
      filterBindings: { object_id__string: false },
      readFilterValue,
    })).toBe('canvas-object');
  });

  it('reads the bound global filter value when a component param is referenced', () => {
    const definitions = [
      { id: 'site_id__string', key: 'site_id', type: 'string', enabled: true },
      { id: 'org__string', key: 'org', type: 'string', enabled: true },
    ];
    const componentParams = [
      { name: 'site_id', type: 'string', filterType: 'filter', value: 'local-room' },
      { name: 'zone_id', type: 'string', filterType: 'params', value: 'zone-a' },
    ];
    const readFilterValue = (id: string) => (id === 'site_id__string' ? 'canvas-room' : 'org-1');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id',
      componentParams,
      definitions,
      filterBindings: { site_id__string: true },
      readFilterValue,
    })).toBe('canvas-room');
    expect(readComponentOptionsQueryUpstream({
      ref: 'zone_id',
      componentParams,
      definitions,
      filterBindings: { site_id__string: true },
      readFilterValue,
    })).toBe('zone-a');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id__string',
      componentParams,
      definitions,
      filterBindings: { site_id__string: true },
      readFilterValue,
    })).toBe('canvas-room');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id',
      componentParams,
      definitions,
      filterBindings: { site_id__string: false },
      readFilterValue,
    })).toBe('local-room');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id',
      componentParams,
      definitions,
      filterBindings: {},
      readFilterValue,
    })).toBe('canvas-room');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id',
      componentParams,
      definitions,
      filterBindings: undefined,
      readFilterValue,
    })).toBe('canvas-room');
    expect(readComponentOptionsQueryUpstream({
      ref: 'org',
      componentParams,
      definitions,
      filterBindings: {},
      readFilterValue,
    })).toBe('org-1');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id',
      componentParams: [],
      definitions: [
        { id: 'site_id__string__aaaaaaaa', key: 'site_id', type: 'string' },
        { id: 'site_id__string__bbbbbbbb', key: 'site_id', type: 'string' },
      ],
      filterBindings: {},
      readFilterValue,
    })).toBe(OPTIONS_QUERY_INVALID);
  });

  it('resolves a bare name to the followed filter whose options identity matches', () => {
    const cmdb = {
      control: 'select' as const,
      optionsSource: {
        type: 'dynamic' as const,
        sourceRef: { type: 'rest_api' as const, value: 'cmdb/rooms' },
        valueField: 'id',
        labelField: 'name',
      },
    };
    const monitor = {
      control: 'select' as const,
      optionsSource: {
        type: 'dynamic' as const,
        sourceRef: { type: 'rest_api' as const, value: 'monitor/rooms' },
        valueField: 'id',
        labelField: 'name',
      },
    };
    const drifted = {
      ...cmdb,
      optionsSource: {
        ...cmdb.optionsSource,
        queryParams: { zone_id: { ref: 'zone_id' } },
      },
    };
    const definitions = [
      { id: 'site_id__string', key: 'site_id', type: 'string', inputConfig: drifted },
      { id: 'site_id__string__bbbbbbbb', key: 'site_id', type: 'string', inputConfig: monitor },
    ];
    const readFilterValue = (id: string) => (id === 'site_id__string' ? 'room-a' : 'room-b');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id',
      componentParams: [{
        name: 'site_id',
        type: 'string',
        filterType: 'filter',
        inputConfig: cmdb,
        value: 'local-room',
      }],
      definitions,
      filterBindings: {
        site_id__string: true,
        'site_id__string__bbbbbbbb': true,
      },
      readFilterValue,
    })).toBe('room-a');
    expect(readComponentOptionsQueryUpstream({
      ref: 'site_id',
      componentParams: [{
        name: 'site_id',
        type: 'string',
        filterType: 'filter',
        inputConfig: cmdb,
        value: 'local-room',
      }],
      definitions,
      filterBindings: {
        site_id__string: false,
        'site_id__string__bbbbbbbb': true,
      },
      readFilterValue,
    })).toBe('room-b');
  });
});
