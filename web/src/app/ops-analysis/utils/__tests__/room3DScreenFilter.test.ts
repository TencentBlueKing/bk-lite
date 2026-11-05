import { describe, expect, it } from 'vitest';
import type { ScreenViewSets, ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  buildFiltersFromScreenItems,
  syncScreenFilterBindings,
} from '@/app/ops-analysis/(pages)/view/screen/utils/layoutUtils';
import { normalizeScreenViewSets } from '@/app/ops-analysis/(pages)/view/screen/utils/viewport';
import {
  ROOM3D_FILTER_ID,
  ROOM3D_FILTER_INPUT_CONFIG,
  ROOM3D_FILTER_NAME,
  includeRoom3DCanvasFilter,
  relabelBuiltinRoom3DFilter,
  resolveRoom3DCanvasSelection,
  resolveRoomFilterAppliedValue,
  ROOM_FILTER_PASSTHROUGH,
} from '../room3DScreenFilter';

const ROOM_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const ROOM_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const emptyViewSets = (): ScreenViewSets => ({
  viewport: { width: 1920, height: 1080, adapter: 'fill' },
  items: [],
  decorations: {},
  filters: [],
});

const roomWidget = (
  id: string,
  valueConfig: ScreenWidgetItem['valueConfig'] = {
    chartType: 'room3D',
    sceneWidgetType: 'room3D',
  },
): ScreenWidgetItem => ({
  id,
  type: 'widget',
  chartType: 'room3D',
  title: '3D机房',
  x: 0,
  y: 0,
  w: 400,
  h: 300,
  zIndex: 1,
  valueConfig,
});

const hostFilter: UnifiedFilterDefinition = {
  id: 'instance_ids__string',
  key: 'instance_ids',
  name: '主机',
  type: 'string',
  defaultValue: 'host-1',
  order: 0,
  enabled: true,
};

describe('room3D canvas filter discovery', () => {
  it('adds a single-select room filter and binds the widget when a screen has room3D', () => {
    const viewSets: ScreenViewSets = {
      ...emptyViewSets(),
      items: [roomWidget('room')],
      filters: [hostFilter],
    };

    const normalized = normalizeScreenViewSets(viewSets);
    const roomFilter = normalized.filters?.find((item) => item.id === ROOM3D_FILTER_ID);

    expect(normalized.filters?.map((item) => item.id)).toEqual([
      'instance_ids__string',
      ROOM3D_FILTER_ID,
    ]);
    expect(roomFilter).toMatchObject({
      key: 'server_room_id',
      name: ROOM3D_FILTER_NAME,
      type: 'string',
      defaultValue: null,
      enabled: true,
      inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
    });
    expect(roomFilter?.inputConfig).not.toMatchObject({ multiple: true });
    expect(normalized.items[0]).toMatchObject({
      valueConfig: { filterBindings: { [ROOM3D_FILTER_ID]: true } },
    });
  });

  it('keeps an existing room filter and other filters unchanged', () => {
    const customRoom: UnifiedFilterDefinition = {
      id: ROOM3D_FILTER_ID,
      key: 'server_room_id',
      name: '园区机房',
      type: 'string',
      defaultValue: ROOM_B,
      order: 4,
      enabled: false,
      inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
    };
    const viewSets: ScreenViewSets = {
      ...emptyViewSets(),
      items: [
        roomWidget('room', {
          chartType: 'room3D',
          room3D: { serverRoomId: ROOM_A },
          filterBindings: { [ROOM3D_FILTER_ID]: false },
        }),
      ],
      filters: [hostFilter, customRoom],
    };

    const normalized = normalizeScreenViewSets(viewSets);

    expect(normalized.filters).toEqual([hostFilter, customRoom]);
    expect(normalized.items[0]).toMatchObject({
      valueConfig: { filterBindings: { [ROOM3D_FILTER_ID]: true } },
    });
  });

  it('migrates the first room3D default without rewriting other widgets', () => {
    const viewSets: ScreenViewSets = {
      ...emptyViewSets(),
      items: [
        roomWidget('first', {
          chartType: 'room3D',
          room3D: { serverRoomId: ROOM_A },
        }),
        roomWidget('second', {
          chartType: 'room3D',
          dataSourceParams: [{ name: 'server_room_id', value: ROOM_B, alias_name: '机房' }],
        }),
      ],
    };

    const normalized = normalizeScreenViewSets(viewSets);
    expect(
      normalized.filters?.find((item) => item.id === ROOM3D_FILTER_ID)?.defaultValue,
    ).toBe(ROOM_A);
    expect(normalized.items).toHaveLength(2);
    expect(normalized.items[1]).toMatchObject({
      valueConfig: { filterBindings: { [ROOM3D_FILTER_ID]: true } },
    });
  });

  it('reads a legacy dataSourceParams room when scene config has none', () => {
    const normalized = normalizeScreenViewSets({
      ...emptyViewSets(),
      items: [
        roomWidget('legacy', {
          chartType: 'room3D',
          dataSourceParams: [{ name: 'server_room_id', value: ROOM_B, alias_name: '机房' }],
        }),
      ],
    });

    expect(
      normalized.filters?.find((item) => item.id === ROOM3D_FILTER_ID)?.defaultValue,
    ).toBe(ROOM_B);
  });

  it('rediscover keeps the saved room filter when editing widgets', () => {
    const saved: UnifiedFilterDefinition = {
      id: ROOM3D_FILTER_ID,
      key: 'server_room_id',
      name: '园区机房',
      type: 'string',
      defaultValue: ROOM_B,
      order: 2,
      enabled: true,
      inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
    };
    const hostParam = {
      name: 'instance_ids',
      alias_name: '主机',
      type: 'string',
      filterType: 'filter' as const,
      value: null,
    };
    const viewSets: ScreenViewSets = {
      ...emptyViewSets(),
      items: [
        roomWidget('room', {
          chartType: 'room3D',
          room3D: { serverRoomId: ROOM_A },
        }),
        {
          id: 'kpi',
          type: 'widget',
          chartType: 'single',
          title: 'CPU',
          x: 0,
          y: 0,
          w: 200,
          h: 120,
          zIndex: 2,
          valueConfig: {
            chartType: 'single',
            dataSource: 7,
            dataSourceParams: [hostParam],
          },
        },
      ],
      filters: [hostFilter, saved],
    };

    const discovered = buildFiltersFromScreenItems({
      viewSets,
      previousDefinitions: viewSets.filters || [],
      dataSources: [
        {
          id: 7,
          name: 'hosts',
          desc: '',
          params: [hostParam],
          chart_type: ['single'],
          namespaces: [],
        },
      ] as never,
    });
    const synced = syncScreenFilterBindings(
      { ...viewSets, filters: discovered },
      discovered,
      [],
    );

    expect(discovered.find((item) => item.id === ROOM3D_FILTER_ID)).toEqual(saved);
    expect(discovered.find((item) => item.id === hostFilter.id)).toMatchObject({
      name: '主机',
      defaultValue: 'host-1',
    });
    expect(synced.items[0]).toMatchObject({
      valueConfig: { filterBindings: { [ROOM3D_FILTER_ID]: true } },
    });
  });
});

describe('relabelBuiltinRoom3DFilter', () => {
  it('replaces only the seeded room filter name', () => {
    const labeled = relabelBuiltinRoom3DFilter(
      {
        filters: [
          {
            id: ROOM3D_FILTER_ID,
            key: 'server_room_id',
            name: ROOM3D_FILTER_NAME,
            type: 'string',
            order: 0,
            enabled: true,
          },
          {
            id: 'instance_ids__string',
            key: 'instance_ids',
            name: '主机',
            type: 'string',
            order: 1,
            enabled: true,
          },
        ],
      },
      '机房',
    );
    expect(labeled.filters?.map((item) => item.name)).toEqual(['机房', '主机']);

    const custom = relabelBuiltinRoom3DFilter(
      {
        filters: [
          {
            id: ROOM3D_FILTER_ID,
            key: 'server_room_id',
            name: '园区机房',
            type: 'string',
            order: 0,
            enabled: true,
          },
        ],
      },
      '机房',
    );
    expect(custom.filters?.[0]?.name).toBe('园区机房');
  });
});

describe('includeRoom3DCanvasFilter', () => {
  it('adds the room filter when datasource scanning finds nothing', () => {
    const filters = includeRoom3DCanvasFilter([], true, [], '机房');

    expect(filters).toHaveLength(1);
    expect(filters[0]).toMatchObject({
      id: ROOM3D_FILTER_ID,
      name: '机房',
      enabled: true,
      defaultValue: null,
      inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
    });
  });

  it('keeps a saved default and enabled flag from the screen definitions', () => {
    const filters = includeRoom3DCanvasFilter(
      [],
      true,
      [
        {
          id: ROOM3D_FILTER_ID,
          key: 'server_room_id',
          name: '机房',
          type: 'string',
          defaultValue: ROOM_A,
          order: 2,
          enabled: false,
          inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
        },
      ],
      '机房',
    );

    expect(filters[0]).toMatchObject({
      name: '机房',
      defaultValue: ROOM_A,
      enabled: false,
    });
  });

  it('leaves a canvas without room3D unchanged', () => {
    expect(includeRoom3DCanvasFilter([], false, [], '机房')).toEqual([]);
  });
});

describe('resolveRoom3DCanvasSelection', () => {
  const definitions: UnifiedFilterDefinition[] = [
    {
      id: ROOM3D_FILTER_ID,
      key: 'server_room_id',
      name: ROOM3D_FILTER_NAME,
      type: 'string',
      defaultValue: ROOM_A,
      order: 0,
      enabled: true,
    },
  ];

  it('uses the filter default until a value is applied', () => {
    expect(
      resolveRoom3DCanvasSelection({
        filterDefinitions: definitions,
        unifiedFilterValues: { [ROOM3D_FILTER_ID]: null },
      }),
    ).toEqual({ savedRoomId: ROOM_A, runtimeRoomId: '' });
  });

  it('uses the applied snapshot value ahead of the default', () => {
    expect(
      resolveRoom3DCanvasSelection({
        filterDefinitions: definitions,
        unifiedFilterValues: { [ROOM3D_FILTER_ID]: ROOM_B },
      }),
    ).toEqual({ savedRoomId: ROOM_A, runtimeRoomId: ROOM_B });
  });

  it('ignores default and applied values when the canvas filter is disabled', () => {
    expect(
      resolveRoom3DCanvasSelection({
        filterDefinitions: [{ ...definitions[0], enabled: false }],
        unifiedFilterValues: { [ROOM3D_FILTER_ID]: ROOM_B },
      }),
    ).toEqual({ savedRoomId: '', runtimeRoomId: '' });
  });

  it('keeps using the canvas filter when stored binding is false', () => {
    expect(
      resolveRoom3DCanvasSelection({
        filterBindings: { [ROOM3D_FILTER_ID]: false },
        filterDefinitions: definitions,
        unifiedFilterValues: { [ROOM3D_FILTER_ID]: ROOM_B },
      }),
    ).toEqual({ savedRoomId: ROOM_A, runtimeRoomId: ROOM_B });
  });
});

describe('resolveRoomFilterAppliedValue', () => {
  const definition = {
    id: ROOM3D_FILTER_ID,
    key: 'server_room_id',
    type: 'string' as const,
    defaultValue: null,
    enabled: true,
  };
  const options = [
    { label: '二号机房', value: ROOM_B },
    { label: '一号机房', value: ROOM_A },
  ];

  it('selects the first room when no default is set', () => {
    expect(resolveRoomFilterAppliedValue(definition, null, options)).toBe(ROOM_B);
  });

  it('keeps an invisible default instead of the first room', () => {
    const missing = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
    expect(
      resolveRoomFilterAppliedValue(
        { ...definition, defaultValue: missing },
        null,
        options,
      ),
    ).toBe(missing);
  });

  it('keeps a visible default ahead of the first option', () => {
    expect(
      resolveRoomFilterAppliedValue(
        { ...definition, defaultValue: ROOM_A },
        null,
        options,
      ),
    ).toBe(ROOM_A);
  });

  it('keeps an applied room that is no longer in the options', () => {
    const missing = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
    expect(resolveRoomFilterAppliedValue(definition, missing, options)).toBeUndefined();
  });

  it('does not replace a selected room when the default is invisible', () => {
    const missing = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
    expect(
      resolveRoomFilterAppliedValue(
        { ...definition, defaultValue: missing },
        ROOM_A,
        options,
      ),
    ).toBeUndefined();
  });

  it('does not choose a first option for other filters', () => {
    expect(
      resolveRoomFilterAppliedValue(
        { ...definition, id: 'region__string', key: 'region' },
        null,
        options,
      ),
    ).not.toBe(ROOM_B);
  });

  it('does not treat a split server_room_id digest id as the builtin room filter', () => {
    expect(
      resolveRoomFilterAppliedValue(
        { ...definition, id: 'server_room_id__string__abcd1234' },
        null,
        options,
      ),
    ).toBe(ROOM_FILTER_PASSTHROUGH);
  });
});
