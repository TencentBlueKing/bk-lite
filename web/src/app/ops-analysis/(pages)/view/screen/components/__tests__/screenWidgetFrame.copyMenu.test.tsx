import { describe, expect, it } from 'vitest';
import { buildScreenItemMenu } from '../screenItemMenu';
import { resolveWidgetCsvExportEntry } from '@/app/ops-analysis/utils/widgetCsvMenu';
import {
  getScreenWidgetFrameClassName,
} from '../screenWidgetFrame';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import { createScreenTextItem } from '../../utils/screenItems';

const dataWidget: ScreenWidgetItem = {
  id: 'w-line',
  type: 'widget',
  chartType: 'line',
  title: 'CPU',
  x: 0,
  y: 0,
  w: 200,
  h: 120,
  zIndex: 1,
  valueConfig: { chartType: 'line' },
};

const sceneWidget: ScreenWidgetItem = {
  ...dataWidget,
  id: 'w-topo',
  chartType: 'networkStatusTopology',
  valueConfig: {
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
  },
};

const keysOf = (
  item: ScreenWidgetItem,
  options?: { shareMode?: boolean; isBuiltIn?: boolean },
) => buildScreenItemMenu(item, [item], options).map((entry) => entry.key);

describe('screen item context menu', () => {
  it('uses topology frame chrome for related topology and network status topology', () => {
    expect(
      getScreenWidgetFrameClassName({ chartType: 'relatedTopology' }),
    ).toContain('screen-widget-frame--topology');
    expect(
      getScreenWidgetFrameClassName({ chartType: 'networkStatusTopology' }),
    ).toContain('screen-widget-frame--topology');
    expect(getScreenWidgetFrameClassName({ chartType: 'line' })).toContain(
      'screen-widget-frame--chart',
    );
  });

  it('includes copy, csv export, and layer actions for a data widget', () => {
    expect(keysOf(dataWidget)).toEqual([
      'edit',
      'copy',
      'exportCsv',
      'delete',
      'bringToFront',
      'bringToBack',
      'bringForward',
      'sendBackward',
    ]);
  });

  it('omits copy and csv export for a networkStatusTopology scene widget', () => {
    expect(keysOf(sceneWidget)).not.toContain('copy');
    expect(keysOf(sceneWidget)).not.toContain('exportCsv');
    expect(keysOf(sceneWidget)).toContain('edit');
    expect(keysOf(sceneWidget)).toContain('delete');
  });

  it('omits copy in share mode and on a builtin canvas', () => {
    expect(keysOf(dataWidget, { shareMode: true })).not.toContain('copy');
    expect(keysOf(dataWidget, { shareMode: true })).not.toContain('exportCsv');
    expect(keysOf(dataWidget, { isBuiltIn: true })).not.toContain('copy');
    expect(buildScreenItemMenu(dataWidget, [dataWidget], { fullscreen: true }).map((entry) => entry.key)).not.toContain('exportCsv');
  });

  it('includes copy for chrome, omits edit, and disables layer moves when it is the only item', () => {
    const text = createScreenTextItem([], { id: 'text-1', content: '说明' });
    const entries = buildScreenItemMenu(text, [text]);
    expect(entries.map((entry) => entry.key)).toEqual([
      'copy',
      'delete',
      'bringToFront',
      'bringToBack',
      'bringForward',
      'sendBackward',
    ]);
    expect(entries.filter((entry) => entry.key !== 'delete' && entry.key !== 'copy').every((entry) => entry.disabled)).toBe(true);
    expect(buildScreenItemMenu(text, [text], { shareMode: true }).map((entry) => entry.key)).not.toContain('copy');
    expect(buildScreenItemMenu(text, [text], { isBuiltIn: true }).map((entry) => entry.key)).not.toContain('copy');
    expect(buildScreenItemMenu(text, [text]).map((entry) => entry.key)).not.toContain('exportCsv');
  });

  it('keeps csv export out of the view-mode context menu and off the view canvas', () => {
    expect(buildScreenItemMenu(dataWidget, [dataWidget], { mode: 'view' })).toEqual([]);
    const radar = {
      ...dataWidget,
      id: 'w-radar',
      chartType: 'radar' as const,
      valueConfig: { chartType: 'radar' as const },
    };
    expect(buildScreenItemMenu(radar, [radar]).map((entry) => entry.key)).toContain('exportCsv');
    expect(buildScreenItemMenu(radar, [radar], {
      rawData: {
        hostA: [{ name: 'CPU', value: 1 }],
        hostB: [{ name: 'CPU', value: 2 }],
      },
    }).map((entry) => entry.key)).not.toContain('exportCsv');
    expect(resolveWidgetCsvExportEntry({
      surface: 'screen',
      chartType: 'line',
      editMode: false,
    })).toBe('none');
    expect(resolveWidgetCsvExportEntry({
      surface: 'screen',
      chartType: 'line',
      editMode: true,
    })).toBe('menu');
    (['single', 'gauge', 'topologyMap', 'nodeGraph'] as const).forEach((chartType) => {
      const item = { ...dataWidget, id: chartType, chartType, valueConfig: { chartType } };
      expect(buildScreenItemMenu(item, [item], { mode: 'view' })).toEqual([]);
      expect(buildScreenItemMenu(item, [item]).map((entry) => entry.key)).not.toContain('exportCsv');
      expect(resolveWidgetCsvExportEntry({
        surface: 'screen',
        chartType,
        editMode: false,
      })).toBe('none');
    });
  });
});
