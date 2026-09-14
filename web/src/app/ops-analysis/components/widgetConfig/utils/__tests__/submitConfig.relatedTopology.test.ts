import { describe, expect, it } from 'vitest';
import {
  buildWidgetSubmitConfig,
  mergeSanitizedWidgetValueConfig,
  persistRelatedTopologyConfig,
} from '../submitConfig';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const baseInput = {
  chartType: 'relatedTopology',
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [] as string[],
  thresholdColors: [] as never[],
  filterBindings: {},
  displayColumns: [] as never[],
  filterFields: [] as never[],
  actions: [] as never[],
};

describe('relatedTopology submit config', () => {
  it('requires modelId and instUuid on save and allows empty preview', () => {
    const missingModel = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '关联拓扑',
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: { instUuid: INST_UUID },
      },
    });
    expect(missingModel.error).toBe('relatedTopologyModelIdRequired');

    const missingInstance = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '关联拓扑',
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: { modelId: 'host' },
      },
    });
    expect(missingInstance.error).toBe('relatedTopologyInstUuidRequired');

    const empty = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '关联拓扑',
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: { instUuid: '' },
      },
    });
    expect(empty.error).toBe('relatedTopologyModelIdRequired');

    const preview = buildWidgetSubmitConfig({
      ...baseInput,
      forPreview: true,
      values: {
        name: '关联拓扑',
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
      },
    });
    expect(preview.config).toEqual({
      name: '关联拓扑',
      description: undefined,
      chartType: 'relatedTopology',
      sceneWidgetType: 'relatedTopology',
      relatedTopology: {},
      appearance: undefined,
    });
  });

  it('persists modelId and instUuid without a data source', () => {
    const result = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '关联拓扑',
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: {
          modelId: 'host',
          instUuid: INST_UUID,
        },
      },
    });
    expect(result.config).toEqual({
      name: '关联拓扑',
      description: undefined,
      chartType: 'relatedTopology',
      sceneWidgetType: 'relatedTopology',
      relatedTopology: { modelId: 'host', instUuid: INST_UUID },
      appearance: undefined,
    });
    expect(result.config).not.toHaveProperty('dataSource');
    expect(result.config).not.toHaveProperty('networkStatusTopology');
  });

  it('reads the same modelId and instUuid after persist and merge', () => {
    const saved = buildWidgetSubmitConfig({
      ...baseInput,
      values: {
        name: '关联拓扑',
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: {
          modelId: 'host',
          instUuid: INST_UUID,
        },
      },
    }).config;
    expect(saved?.relatedTopology).toEqual({
      modelId: 'host',
      instUuid: INST_UUID,
    });

    const reopened = persistRelatedTopologyConfig(saved?.relatedTopology);
    expect(reopened).toEqual({
      modelId: 'host',
      instUuid: INST_UUID,
    });

    const merged = mergeSanitizedWidgetValueConfig(
      { chartType: 'relatedTopology', sceneWidgetType: 'relatedTopology' },
      {
        chartType: 'relatedTopology',
        sceneWidgetType: 'relatedTopology',
        relatedTopology: saved?.relatedTopology,
      },
      'relatedTopology',
    );
    expect(merged.relatedTopology).toEqual({
      modelId: 'host',
      instUuid: INST_UUID,
    });
  });
});
