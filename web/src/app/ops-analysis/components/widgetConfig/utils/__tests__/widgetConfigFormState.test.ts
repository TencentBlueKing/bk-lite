import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import type { LayoutItem, ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import {
  applyOpenedValueConfigToFormValues,
  buildDataFetchSignature,
  buildDatasourceSwitchResetValues,
  buildOpenedSceneWidgetTopology,
  buildOpenedWidgetFormValues,
  buildSceneWidgetSelectorResetValues,
  computePreviewDefinitions,
  getSceneWidgetSelectionType,
  getWidgetChartTypeFlags,
  isSceneWidgetSelection,
  mergeNetworkStatusTopologyDraft,
  resolveOpenedSceneWidgetType,
} from '../widgetConfigFormState';

describe('getWidgetChartTypeFlags', () => {
  it('marks table-like from chartType only', () => {
    assert.equal(getWidgetChartTypeFlags('table').isTableLike, true);
    assert.equal(getWidgetChartTypeFlags('eventTable').isTableLike, true);
    assert.equal(getWidgetChartTypeFlags('line').isTableLike, false);
  });

  it('marks scene widgets from either chartType or sceneWidgetType', () => {
    assert.equal(
      getWidgetChartTypeFlags('networkStatusTopology').isNetworkStatusTopology,
      true,
    );
    assert.equal(
      getWidgetChartTypeFlags('line', 'networkStatusTopology').isNetworkStatusTopology,
      true,
    );
    assert.equal(
      getWidgetChartTypeFlags('relatedTopology').isRelatedTopology,
      true,
    );
    assert.equal(
      getWidgetChartTypeFlags('', 'application3D').isSceneWidget,
      true,
    );
    assert.equal(getWidgetChartTypeFlags('room3D').isRoom3D, true);
    assert.equal(getWidgetChartTypeFlags('room3D').isSceneWidget, true);
    assert.equal(getWidgetChartTypeFlags('line').isSceneWidget, false);
  });

  it('keeps value-format types on the chart type, not the scene type', () => {
    assert.equal(getWidgetChartTypeFlags('line').showValueFormat, true);
    assert.equal(getWidgetChartTypeFlags('multiValue').showValueFormat, true);
    assert.equal(
      getWidgetChartTypeFlags('networkStatusTopology').showValueFormat,
      false,
    );
  });
});

describe('getSceneWidgetSelectionType', () => {
  it('reads sceneWidgetType, then chartType, then scene: id prefix', () => {
    assert.equal(
      getSceneWidgetSelectionType({ sceneWidgetType: 'relatedTopology' }),
      'relatedTopology',
    );
    assert.equal(
      getSceneWidgetSelectionType({ chartType: 'application3D' }),
      'application3D',
    );
    assert.equal(
      getSceneWidgetSelectionType({ id: 'scene:networkStatusTopology' }),
      'networkStatusTopology',
    );
    assert.equal(isSceneWidgetSelection({ id: '12' }), false);
  });
});

describe('selector reset values stay on two paths', () => {
  it('scene reset writes topology defaults and clears tableConfig/actions', () => {
    const values = buildSceneWidgetSelectorResetValues('networkStatusTopology');
    assert.deepEqual(values.networkStatusTopology, {
      instUuids: [],
      nodeLimit: 100,
      linkTrafficDisplays: ['inbound', 'outbound'],
    });
    assert.equal(values.tableConfig, undefined);
    assert.deepEqual(values.actions, []);
    assert.equal(values.dataSource, undefined);
    assert.ok(!('name' in values));
  });

  it('datasource reset does not touch tableConfig or actions', () => {
    const values = buildDatasourceSwitchResetValues({
      dataSourceId: 9,
      chartType: 'line',
      params: { q: 'up' },
    });
    assert.equal(values.dataSource, 9);
    assert.equal(values.sceneWidgetType, undefined);
    assert.equal(values.networkStatusTopology, undefined);
    assert.deepEqual(values.params, { q: 'up' });
    assert.ok(!('tableConfig' in values));
    assert.ok(!('actions' in values));
    assert.ok(!('dataSourceParams' in values));
    assert.ok(!('name' in values));
  });
});

describe('opened widget hydrate', () => {
  const item: LayoutItem = {
    i: 'w1',
    x: 0,
    y: 0,
    w: 4,
    h: 4,
    name: 'CPU',
    description: 'desc',
    valueConfig: {
      chartType: 'nodeGraph',
      dataSource: 3,
      dataSourceParams: [],
    },
  };

  it('copies name and leaves params empty for the coordinator to fill', () => {
    const values = buildOpenedWidgetFormValues(item, {
      showChartThemeMode: false,
    });
    assert.equal(values.name, 'CPU');
    assert.equal(values.description, 'desc');
    assert.equal(values.chartType, 'nodeGraph');
    assert.deepEqual(values.params, {});
    assert.equal(values.chartThemeMode, undefined);
  });

  it('fills theme only when the surface asks for it', () => {
    const values = buildOpenedWidgetFormValues(item, {
      showChartThemeMode: true,
    });
    assert.equal(values.chartThemeMode, 'default');
  });

  it('defaults nodeGraph identity to ip and cardList layout when missing', () => {
    const formValues = buildOpenedWidgetFormValues(item, {
      showChartThemeMode: false,
    });
    applyOpenedValueConfigToFormValues(formValues, item.valueConfig, undefined);
    assert.equal(formValues.nodeGraphIdentityMode, 'ip');
    assert.deepEqual(formValues.cardList, {
      leading: { type: 'none' },
      layout: 'list',
    });
    assert.equal(formValues.compareMode, 'percent');
  });

  it('keeps compare false when the data source cannot compare', () => {
    const formValues = buildOpenedWidgetFormValues(item, {
      showChartThemeMode: false,
    });
    const valueConfig: ValueConfig = {
      ...item.valueConfig,
      compare: true,
      compareMode: 'value',
    };
    applyOpenedValueConfigToFormValues(formValues, valueConfig, {
      params: [{ name: 'q', value: 'up' }],
    } as DatasourceItem);
    assert.equal(formValues.compare, false);
    assert.equal(formValues.compareMode, 'value');
  });

  it('hydrates room3D default from legacy dataSourceParams', () => {
    const values = buildOpenedWidgetFormValues(
      {
        i: 'room',
        x: 0,
        y: 0,
        w: 4,
        h: 4,
        name: '3D机房',
        valueConfig: {
          chartType: 'room3D',
          dataSource: 12,
          dataSourceParams: [
            {
              name: 'server_room_id',
              value: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            },
          ],
        },
      },
      { showChartThemeMode: false },
    );
    assert.deepEqual(values.room3D, {
      serverRoomId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      rackTopLine1: 'location',
      rackTopLine2: 'type',
    });
    assert.equal(values.sceneWidgetType, undefined);
  });

  it('hydrates saved rack-top lines into the room3D form', () => {
    const values = buildOpenedWidgetFormValues(
      {
        i: 'room',
        x: 0,
        y: 0,
        w: 4,
        h: 4,
        name: '3D机房',
        valueConfig: {
          chartType: 'room3D',
          sceneWidgetType: 'room3D',
          room3D: {
            rackTopLine1: 'name',
            rackTopLine2: '',
          },
        },
      },
      { showChartThemeMode: false },
    );
    assert.deepEqual(values.room3D, {
      rackTopLine1: 'name',
    });
  });
});

describe('scene open vs selector topology defaults', () => {
  it('open path keeps existing linkTrafficDisplays', () => {
    assert.deepEqual(
      buildOpenedSceneWidgetTopology({
        chartType: 'networkStatusTopology',
        networkStatusTopology: {
          instUuids: ['a'],
          nodeLimit: 20,
          linkTrafficDisplays: ['inbound'],
        },
      }),
      {
        instUuids: ['a'],
        nodeLimit: 20,
        linkTrafficDisplays: ['inbound'],
      },
    );
  });

  it('open path fills inbound/outbound only when the stored list is missing', () => {
    assert.deepEqual(
      buildOpenedSceneWidgetTopology({
        chartType: 'networkStatusTopology',
        networkStatusTopology: { instUuids: ['a'] },
      }).linkTrafficDisplays,
      ['inbound', 'outbound'],
    );
  });

  it('resolves scene type from chartType when sceneWidgetType is absent', () => {
    assert.equal(
      resolveOpenedSceneWidgetType({ chartType: 'relatedTopology' }),
      'relatedTopology',
    );
    assert.equal(
      resolveOpenedSceneWidgetType({ chartType: 'room3D' }),
      'room3D',
    );
  });
});

describe('computePreviewDefinitions', () => {
  it('keeps existing definitions and appends bindable filter params', () => {
    const existing = [
      {
        id: 'env__string',
        key: 'env',
        name: '环境',
        type: 'string' as const,
        order: 0,
        enabled: true,
      },
    ];
    const next = computePreviewDefinitions(existing, {
      params: [
        { name: 'env', type: 'string', filterType: 'filter', alias_name: 'Env' },
        { name: 'q', type: 'string', filterType: 'fixed' },
        { name: 'ns', type: 'string', filterType: 'filter', value: 'prod' },
      ],
    } as DatasourceItem);
    assert.equal(next[0].name, '环境');
    const added = next.find((item) => item.id === 'ns__string');
    assert.equal(added?.defaultValue, 'prod');
    assert.equal(added?.order, 2);
    assert.equal(next.some((item) => item.key === 'q'), false);
  });
});

describe('buildDataFetchSignature', () => {
  it('returns empty string for missing config', () => {
    assert.equal(buildDataFetchSignature(undefined), '');
  });

  it('only hashes fetch-relevant fields', () => {
    const signature = buildDataFetchSignature({
      name: 'ignored',
      chartType: 'topN',
      dataSource: 4,
      topNLabelField: 'host',
      topNValueField: 'cpu',
      dataSourceParams: [{ name: 'q', value: 'up' }],
    });
    assert.equal(
      signature,
      JSON.stringify({
        dataSource: 4,
        chartType: 'topN',
        sceneWidgetType: undefined,
        compare: false,
        compareMode: undefined,
        filterBindings: undefined,
        dataSourceParams: [{ name: 'q', value: 'up' }],
        topNLabelField: 'host',
        topNValueField: 'cpu',
        cardListTitleField: undefined,
        networkStatusTopology: undefined,
        room3D: undefined,
      }),
    );
  });
});

describe('mergeNetworkStatusTopologyDraft', () => {
  it('prefers form values and falls back to the opened topology', () => {
    assert.deepEqual(
      mergeNetworkStatusTopologyDraft(
        { instUuids: ['b'], nodeLimit: 8 },
        {
          instUuids: ['a'],
          nodeLimit: 100,
          linkTrafficDisplays: ['outbound'],
          layoutMode: 'force',
        },
      ),
      {
        instUuids: ['b'],
        nodeLimit: 8,
        linkTrafficDisplays: ['outbound'],
        inboundTrafficThresholds: undefined,
        outboundTrafficThresholds: undefined,
        layoutMode: 'force',
        layoutByMode: undefined,
        nodePositions: undefined,
        linkVertices: undefined,
      },
    );
  });
});

describe('application3D wall form values', () => {
  it('hydrates a saved wall config and fills defaults when the field is missing', () => {
    const saved = buildOpenedWidgetFormValues(
      {
        i: 'wall',
        x: 0,
        y: 0,
        w: 4,
        h: 4,
        name: '3D应用',
        valueConfig: {
          chartType: 'application3D',
          sceneWidgetType: 'application3D',
          application3DWall: {
            pageSize: 36,
            alarmPagesEnabled: false,
            alarmPageSize: 12,
            autoPageEnabled: true,
            dwellSeconds: 8,
            pageEffect: 'fade',
          },
        },
      },
      { showChartThemeMode: false },
    );
    assert.equal(saved.application3DWall?.pageSize, 36);
    assert.equal(saved.application3DWall?.alarmPageSize, 12);
    assert.equal(saved.application3DWall?.pageEffect, 'fade');

    const missing = buildOpenedWidgetFormValues(
      {
        i: 'wall',
        x: 0,
        y: 0,
        w: 4,
        h: 4,
        name: '3D应用',
        valueConfig: {
          chartType: 'application3D',
          sceneWidgetType: 'application3D',
        },
      },
      { showChartThemeMode: false },
    );
    assert.deepEqual(missing.application3DWall, {
      pageSize: 24,
      alarmPagesEnabled: false,
      alarmPageSize: 24,
      autoPageEnabled: false,
      dwellSeconds: 10,
      pageEffect: 'slide',
    });
  });
});
