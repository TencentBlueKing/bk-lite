import { describe, expect, it } from 'vitest';
import {
  normalizeInputConfig,
  normalizeInputConfigResult,
} from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  collectOptionsQueryParamIssues,
  MAX_OPTIONS_QUERY_CHAIN_NODES,
  normalizeQueryParamsForStorage,
  OPTIONS_QUERY_INVALID,
  readOptionsQueryUpstream,
  redirectRetiredSummaryRef,
  resolveOptionsQueryParams,
  validateOptionsQueryParams,
  validateUnifiedFilterQueryGraph,
} from '@/app/ops-analysis/utils/optionsQueryParamRefs';

const names = ['room', 'device', 'rack', 'port'];

describe('options query param refs', () => {
  it('normalizes a whole $name$ or $name:type$ token into { ref }', () => {
    expect(normalizeQueryParamsForStorage({
      room_id: '$server_room_id$',
      typed: '$server_room_id:string$',
      fixed: 'literal',
    })).toEqual({
      ok: true,
      queryParams: {
        room_id: { ref: 'server_room_id' },
        typed: { ref: 'server_room_id' },
        fixed: 'literal',
      },
    });
  });

  it('rejects concatenated tokens', () => {
    expect(normalizeQueryParamsForStorage({ x: 'pre-$id$' })).toEqual({
      ok: false,
      issue: { code: 'concat', param: 'x' },
    });
  });

  it('keeps a chain of three parameters and rejects the fourth', () => {
    expect(MAX_OPTIONS_QUERY_CHAIN_NODES).toBe(3);
    expect(validateOptionsQueryParams([
      { name: 'device', queryParams: { room_id: { ref: 'room' } } },
      { name: 'rack', queryParams: { device_id: { ref: 'device' } } },
    ], names)).toBeNull();
    expect(validateOptionsQueryParams([
      { name: 'device', queryParams: { room_id: { ref: 'room' } } },
      { name: 'rack', queryParams: { device_id: { ref: 'device' } } },
      { name: 'port', queryParams: { rack_id: { ref: 'rack' }, site: { ref: 'room' } } },
    ], names)?.code).toBe('depth');
    const issues = collectOptionsQueryParamIssues([
      { name: 'device', queryParams: { room_id: { ref: 'room' } } },
      { name: 'rack', queryParams: { device_id: { ref: 'device' } } },
      { name: 'port', queryParams: { rack_id: { ref: 'rack' }, site: { ref: 'room' } } },
    ], names);
    expect(issues).toEqual([
      expect.objectContaining({ code: 'depth', name: 'port', param: 'rack_id' }),
    ]);
    const longer = collectOptionsQueryParamIssues([
      { name: 'site', queryParams: { parent: { ref: 'root' } } },
      { name: 'room', queryParams: { site_id: { ref: 'site' } } },
      { name: 'device', queryParams: { room_id: { ref: 'room' } } },
      { name: 'rack', queryParams: { device_id: { ref: 'device' } } },
      { name: 'port', queryParams: { rack_id: { ref: 'rack' } } },
    ], ['root', 'site', 'room', 'device', 'rack', 'port']);
    expect(longer.map((issue) => issue.param).sort()).toEqual(['device_id', 'rack_id', 'room_id']);
  });

  it('reports a cycle, an over-long edge, and a bad type in one pass', () => {
    const issues = collectOptionsQueryParamIssues([
      { name: 'left', queryParams: { peer: { ref: 'right' } } },
      { name: 'right', queryParams: { peer: { ref: 'left' } } },
      { name: 'device', queryParams: { room_id: { ref: 'room' } } },
      { name: 'rack', queryParams: { device_id: { ref: 'device' } } },
      { name: 'port', queryParams: { rack_id: { ref: 'rack' } } },
      { name: 'typed', queryParams: { raw: { ref: 'payload' } } },
    ], [
      ...names,
      'left',
      'right',
      'typed',
      { name: 'payload', type: 'object' },
    ]);
    expect(issues.map((issue) => issue.code).sort()).toEqual(['cycle', 'cycle', 'depth', 'type']);
    expect(issues.filter((issue) => issue.code === 'depth').map((issue) => (
      'param' in issue ? issue.param : ''
    ))).toEqual(['rack_id']);
    expect(issues.some((issue) => issue.code === 'type' && 'param' in issue && issue.param === 'raw')).toBe(true);
  });

  it('rejects a reference to a parameter that cannot be passed as a filter', () => {
    expect(validateOptionsQueryParams([
      { name: 'device', queryParams: { raw: { ref: 'payload' } } },
    ], [
      { name: 'device', type: 'string' },
      { name: 'payload', type: 'object' },
    ])?.code).toBe('type');
  });

  it('rejects a cycle and a self reference', () => {
    expect(validateOptionsQueryParams([
      { name: 'room', queryParams: { device_id: { ref: 'device' } } },
      { name: 'device', queryParams: { room_id: { ref: 'room' } } },
    ], names)?.code).toBe('cycle');
    expect(validateOptionsQueryParams([
      { name: 'room', queryParams: { room_id: { ref: 'room' } } },
    ], names)?.code).toBe('self');
  });

  it('does not request downstream options when an upstream value is empty', () => {
    const query = { room_id: { ref: 'room' }, site: 'fixed' };
    expect(resolveOptionsQueryParams(query, () => null)).toEqual({
      blocked: true,
      blockReason: 'empty',
      params: {},
      missingRefs: ['room'],
    });
    expect(resolveOptionsQueryParams(query, () => [])).toMatchObject({
      blocked: true,
      blockReason: 'empty',
    });
    expect(resolveOptionsQueryParams(query, () => 'room-1')).toEqual({
      blocked: false,
      params: { room_id: 'room-1', site: 'fixed' },
      missingRefs: [],
    });
  });

  it('normalizes YAML whole-token query params when reading inputConfig', () => {
    const config = normalizeInputConfig({
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'cmdb/devices' },
          valueField: 'id',
          labelField: 'name',
          queryParams: { room_id: '$server_room_id:string$' },
        },
      },
    });
    expect(config && config.control === 'select' && config.optionsSource.type === 'dynamic'
      ? config.optionsSource.queryParams
      : undefined).toEqual({ room_id: { ref: 'server_room_id' } });
  });

  it('refuses a concatenated value at runtime instead of sending it', () => {
    expect(resolveOptionsQueryParams({ x: 'pre-$id$' }, () => 'id-1')).toMatchObject({
      blocked: true,
      blockReason: 'invalid',
    });
  });

  it('drops illegal query params when normalizing stored input config', () => {
    const entity = {
      inputConfig: {
        control: 'select' as const,
        optionsSource: {
          type: 'dynamic' as const,
          sourceId: 9,
          valueField: 'id',
          labelField: 'name',
          queryParams: { room_id: 'pre-$site$' },
        },
      },
    };
    const result = normalizeInputConfigResult(entity);
    expect(result.queryParamIssue).toEqual({ code: 'concat', param: 'room_id' });
    const config = result.config;
    expect(config && config.control === 'select' && config.optionsSource.type === 'dynamic'
      ? config.optionsSource.queryParams
      : 'kept').toBeUndefined();
    expect(normalizeInputConfig(entity)).toEqual(result.config);
  });

  it('rejects a bare parameter name when several filters share it, and accepts a filter id', () => {
    const nodes = [
      {
        name: 'device_id__string__aaaa1111',
        aliases: ['device_id'],
        queryParams: { room_id: { ref: 'site_id' } },
      },
      { name: 'site_id__string__11111111', aliases: ['site_id'] },
      { name: 'site_id__string__22222222', aliases: ['site_id'] },
    ];
    expect(validateOptionsQueryParams(nodes, ['device_id', 'site_id'])?.code).toBe('ambiguous');
    expect(validateOptionsQueryParams([
      {
        ...nodes[0],
        queryParams: { room_id: { ref: 'site_id__string__22222222' } },
      },
      nodes[1],
      nodes[2],
    ], ['device_id', 'site_id', 'site_id__string__22222222'])).toBeNull();
  });

  it('reads the draft of the filter id and treats a shared bare name as invalid', () => {
    const definitions = [
      { id: 'site_id__string__11111111', key: 'site_id', enabled: true },
      { id: 'site_id__string__22222222', key: 'site_id', enabled: true },
    ];
    const values: Record<string, string> = {
      site_id__string__11111111: 'room-a',
      site_id__string__22222222: 'room-b',
    };
    expect(readOptionsQueryUpstream('site_id__string__22222222', definitions, (id) => values[id]))
      .toEqual({ found: true, invalid: false, value: 'room-b' });
    expect(readOptionsQueryUpstream('site_id', definitions, (id) => values[id]))
      .toEqual({ found: true, invalid: true });
    expect(resolveOptionsQueryParams(
      { room_id: { ref: 'site_id' } },
      () => OPTIONS_QUERY_INVALID,
    )).toMatchObject({ blocked: true, blockReason: 'invalid' });
  });

  it('rejects a bare name when the filter table is confirmed with split rows', () => {
    const dynamic = (ref: string) => ({
      control: 'select' as const,
      optionsSource: {
        type: 'dynamic' as const,
        sourceId: 9,
        valueField: 'id',
        labelField: 'name',
        queryParams: { room_id: { ref } },
      },
    });
    expect(validateUnifiedFilterQueryGraph([
      { id: 'site_id__string__11111111', key: 'site_id', type: 'string' },
      { id: 'site_id__string__22222222', key: 'site_id', type: 'string' },
      {
        id: 'device_id__string',
        key: 'device_id',
        type: 'string',
        inputConfig: dynamic('site_id'),
      },
    ])?.code).toBe('ambiguous');
    expect(validateUnifiedFilterQueryGraph([
      { id: 'site_id__string__11111111', key: 'site_id', type: 'string' },
      { id: 'site_id__string__22222222', key: 'site_id', type: 'string' },
      {
        id: 'device_id__string',
        key: 'device_id',
        type: 'string',
        inputConfig: dynamic('site_id__string__22222222'),
      },
    ])).toBeNull();
  });

  it('redirects a retired summary id only after that row is gone', () => {
    const live = new Set(['object_id__string', 'metric_id__string']);
    expect(redirectRetiredSummaryRef('object_id__string__abcd1234', live)).toBe('object_id__string');
    expect(redirectRetiredSummaryRef('object_id__string', live)).toBe('object_id__string');
    expect(redirectRetiredSummaryRef('object_id', live)).toBe('object_id');
    const stillSplit = new Set(['object_id__string__abcd1234', 'object_id__string__bbbbbbbb']);
    expect(redirectRetiredSummaryRef('object_id__string__abcd1234', stillSplit))
      .toBe('object_id__string__abcd1234');
  });
});
