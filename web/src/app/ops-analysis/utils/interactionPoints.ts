import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { extractComparableValue } from '@/app/ops-analysis/utils/compareQuery';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import { extractMultiValueItems, validateMultiValueData } from '@/app/ops-analysis/utils/multiValueData';
import { parseCardListItems } from '@/app/ops-analysis/utils/cardList';
import { resolveRadarSeriesData } from '@/app/ops-analysis/utils/radarData';
import {
  buildNodeGraph,
  nodeGraphEdgeFields,
  toNodeGraphMapping,
  withNodeGraphParallelIndex,
} from '@/app/ops-analysis/utils/nodeGraphData';
import { buildTopNItems, type TopNItem } from '@/app/ops-analysis/utils/topNData';
import { parseEventTimelineItems } from '@/app/ops-analysis/utils/eventTimeline';
import {
  chartLinkFields,
  eventTimelineLinkPoint,
  rowsFromUnknown,
  type ChartLinkPoint,
} from '@/app/ops-analysis/utils/interactionLink';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const numericPoint = (
  raw: unknown,
  extra: Partial<ChartLinkPoint> = {},
): ChartLinkPoint => {
  const numeric = typeof raw === 'number'
    ? raw
    : typeof raw === 'string' && raw.trim() && Number.isFinite(Number(raw))
      ? Number(raw)
      : null;
  return {
    ...extra,
    ...(typeof numeric === 'number' && Number.isFinite(numeric) ? { numeric } : {}),
    ...(extra.text ? {} : numeric != null ? { text: String(numeric) } : {}),
    ...(raw !== undefined ? { raw } : {}),
  };
};

export const topNLinkPoints = (
  items: Array<Pick<TopNItem, 'name' | 'source' | 'field'>>,
  valueField?: string,
): ChartLinkPoint[] => items.map((item) => {
  const raw = item.source ? getValueByPath(item.source, item.field || valueField) : undefined;
  const fields = item.source ? chartLinkFields(item.source) : undefined;
  return numericPoint(raw, {
    seriesName: item.name,
    text: item.name,
    ...(fields ? { fields } : {}),
  });
});

export const cardListLinkPoints = (
  items: Array<{ primary?: string; source?: Record<string, unknown> }>,
): ChartLinkPoint[] => items.map((item) => ({
  ...(item.primary ? { seriesName: item.primary, text: item.primary } : {}),
  ...(item.source ? { raw: item.source, fields: chartLinkFields(item.source) } : {}),
}));

export const buildInteractionPoints = (
  chartType: string | undefined,
  rawData: unknown,
  config?: Pick<
    ValueConfig,
    | 'dimensionField'
    | 'valueField'
    | 'pieScalarFields'
    | 'selectedFields'
    | 'topNLabelField'
    | 'topNValueField'
    | 'topNScalarFields'
    | 'multiValueLabelField'
    | 'multiValueValueField'
    | 'cardList'
    | 'radar'
    | 'nodeGraphIdentityMode'
    | 'nodeGraphSourceField'
    | 'nodeGraphTargetField'
    | 'nodeGraphValueField'
    | 'nodeGraphTargetPortField'
    | 'eventTimeline'
  > | null,
): ChartLinkPoint[] => {
  if (chartType === 'line' || chartType === 'bar') {
    const chart = ChartDataTransformer.transformToLineBarData(rawData, {
      dimensionField: config?.dimensionField,
      valueField: config?.valueField,
    });
    if (chart.series?.length) {
      return chart.series.flatMap((series) => series.points || []);
    }
    return chart.points || [];
  }

  if (chartType === 'pie') {
    return ChartDataTransformer.transformToPieData(rawData, {
      dimensionField: config?.dimensionField,
      valueField: config?.valueField,
      pieScalarFields: config?.pieScalarFields,
    }).flatMap((item) => (item.__link ? [item.__link] : []));
  }

  if (chartType === 'table' || chartType === 'eventTable') {
    return rowsFromUnknown(rawData).map((row) => ({
      fields: chartLinkFields(row),
      raw: row,
    }));
  }

  if (chartType === 'eventTimeline') {
    const mapping = config?.eventTimeline;
    return parseEventTimelineItems(rawData, {
      sortOrder: mapping?.sortOrder,
      timeField: mapping?.timeField,
      titleField: mapping?.titleField,
      descriptionField: mapping?.descriptionField,
      categoryField: mapping?.categoryField,
      statusField: mapping?.statusField,
      linkField: mapping?.linkField,
    }).items.map((item) => eventTimelineLinkPoint(item));
  }

  if (chartType === 'single' || chartType === 'gauge') {
    const selectedField = config?.selectedFields?.[0];
    const raw = extractComparableValue(rawData, selectedField);
    const fields = chartLinkFields(rawData);
    if (raw == null && !fields) return [];
    return [numericPoint(raw, {
      ...(selectedField ? { seriesName: selectedField } : {}),
      ...(fields ? { fields } : {}),
    })];
  }

  if (chartType === 'topN') {
    return topNLinkPoints(
      buildTopNItems(rawData, config?.topNLabelField, config?.topNValueField, {
        scalarFields: config?.topNScalarFields,
      }),
      config?.topNValueField,
    );
  }

  if (chartType === 'multiValue') {
    const result = validateMultiValueData(rawData, '', {
      labelField: config?.multiValueLabelField,
      valueField: config?.multiValueValueField,
    });
    const extracted = extractMultiValueItems(rawData);
    const rows = Array.isArray(extracted) ? extracted.filter(isRecord) : [];
    return result.items.map((item, index) => numericPoint(item.value, {
      seriesName: item.label,
      text: item.label,
      fields: chartLinkFields(rows[index]) ?? { label: item.label, value: item.value },
    }));
  }

  if (chartType === 'radar') {
    const series = resolveRadarSeriesData(
      rawData,
      config?.radar,
      config?.selectedFields || [],
    );
    return series.indicatorLabels.map((label, index) => numericPoint(
      series.indicatorValues[index],
      {
        seriesName: label,
        text: label,
        fields: { [label]: series.indicatorValues[index] },
      },
    ));
  }

  if (chartType === 'cardList') {
    return cardListLinkPoints(parseCardListItems(rawData, {
      ...config?.cardList,
      titleField: config?.cardList?.titleField || '',
    }).items);
  }

  if (chartType === 'nodeGraph') {
    const model = buildNodeGraph(rawData, toNodeGraphMapping(config ?? undefined));
    const nodes = model.nodes.map((node) => numericPoint(node.inbound + node.outbound, {
      seriesName: node.id,
      text: node.id,
      fields: {
        id: node.id,
        inbound: node.inbound,
        outbound: node.outbound,
      },
    }));
    const edges = withNodeGraphParallelIndex(model.edges).map((edge) => numericPoint(edge.value, {
      seriesName: `${edge.source} → ${edge.target}`,
      fields: nodeGraphEdgeFields(edge, config?.nodeGraphIdentityMode),
    }));
    return [...nodes, ...edges];
  }

  return [];
};
