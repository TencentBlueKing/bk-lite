import React, { useEffect, useMemo } from 'react';
import { Spin } from 'antd';
import ReactEcharts from 'echarts-for-react';
import { formatNumericValue } from '@/components/log-analysis-widgets/runtime';
import ChartSurface from '@/components/chart-surface';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import useChartColors from '@/hooks/useChartColors';

export interface LogAnalysisSankeyProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

interface SankeyNode {
  name: string;
}

interface SankeyLink {
  source: string;
  target: string;
  value: number;
  originalData?: any;
}

interface SankeyData {
  nodes: SankeyNode[];
  links: SankeyLink[];
}

const LogAnalysisSankey: React.FC<LogAnalysisSankeyProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const colors = useChartColors();
  const chartColors = colors.series;

  const chartData = useMemo((): SankeyData => {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return { nodes: [], links: [] };
    }

    const sourceField = config?.displayMaps?.sourceField || 'source.ip';
    const targetField = config?.displayMaps?.targetField || 'destination.ip';
    const valueField = config?.displayMaps?.valueField || 'flow_bytes';
    const middleField = config?.displayMaps?.middleField;

    const links: (SankeyLink & { originalData?: any })[] = [];
    const nodeSet = new Set<string>();

    if (middleField) {
      rawData.forEach((item: any) => {
        const source = item[sourceField];
        const middle = item[middleField];
        const target = item[targetField];
        const value = parseFloat(item[valueField]) || 0;

        if (source && middle && target && value > 0) {
          links.push({
            source: `源_${source}`,
            target: `协议_${middle}`,
            value,
            originalData: item,
          });
          links.push({
            source: `协议_${middle}`,
            target: `目标_${target}`,
            value,
            originalData: item,
          });
          nodeSet.add(`源_${source}`);
          nodeSet.add(`协议_${middle}`);
          nodeSet.add(`目标_${target}`);
        }
      });
    } else {
      rawData.forEach((item: any) => {
        const source = item[sourceField];
        const target = item[targetField];
        const value = parseFloat(item[valueField]) || 0;

        if (source && target && value > 0) {
          if (source === target) {
            return;
          }

          links.push({
            source: `源_${source}`,
            target: `目标_${target}`,
            value,
            originalData: item,
          });
          nodeSet.add(`源_${source}`);
          nodeSet.add(`目标_${target}`);
        }
      });
    }

    const linkMap = new Map<string, { value: number; originalData: any[] }>();
    links.forEach((link) => {
      const key = `${link.source}->${link.target}`;
      if (!linkMap.has(key)) {
        linkMap.set(key, { value: 0, originalData: [] });
      }
      const existing = linkMap.get(key)!;
      existing.value += link.value;
      if (link.originalData) {
        existing.originalData.push(link.originalData);
      }
    });

    const mergedLinks: (SankeyLink & { originalData?: any[] })[] = [];
    linkMap.forEach((data, key) => {
      const [source, target] = key.split('->');
      mergedLinks.push({
        source,
        target,
        value: data.value,
        originalData: data.originalData,
      });
    });

    const maxValue = Math.max(...mergedLinks.map((link) => link.value));
    const linksWithWidth = mergedLinks.map((link) => ({
      ...link,
      lineStyle: {
        width: Math.max(10, Math.min(30, (link.value / maxValue) * 20 + 10)),
        opacity: 0.7,
      },
    }));

    const nodes: SankeyNode[] = Array.from(nodeSet).map((name) => ({ name }));
    return { nodes, links: linksWithWidth };
  }, [config, rawData]);

  useEffect(() => {
    if (!loading) {
      const hasData = chartData.nodes.length > 0 && chartData.links.length > 0;
      onReady?.(hasData);
    }
  }, [chartData, loading, onReady]);

  const option: any = {
    color: chartColors,
    animation: false,
    title: { show: false },
    grid: {
      left: 10,
      right: 30,
      top: 10,
      bottom: 10,
    },
    tooltip: {
      trigger: 'item',
      triggerOn: 'mousemove',
      enterable: true,
      confine: true,
      textStyle: {
        fontSize: 12,
        color: colors.textPrimary,
      },
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      formatter: function (params: any) {
        if (params.dataType === 'edge') {
          const sourceName = params.data.source.replace(/^(源_|协议_|目标_)/, '');
          const targetName = params.data.target.replace(/^(源_|协议_|目标_)/, '');

          const tooltipFields = config?.displayMaps?.tooltipFields || {};
          const sourceField = config?.displayMaps?.sourceField || 'source.ip';
          const targetField = config?.displayMaps?.targetField || 'destination.ip';
          const valueField = config?.displayMaps?.valueField || 'flow_bytes';
          let rows: Array<{
            key: string;
            label: string;
            value: string | number;
          }> = [];

          if (params.data.originalData && params.data.originalData.length > 0) {
            const firstItem = params.data.originalData[0];

            Object.entries(tooltipFields).forEach(([fieldKey, fieldLabel]) => {
              let displayValue = firstItem[fieldKey];

              if (
                displayValue === undefined ||
                displayValue === null ||
                displayValue === ''
              ) {
                displayValue = '--';
              } else if (
                fieldKey === valueField &&
                typeof displayValue === 'number'
              ) {
                displayValue = (displayValue / (1024 * 1024 * 1024)).toFixed(2);
              }

              if (fieldKey === 'flow_bytes') {
                displayValue = formatNumericValue(displayValue);
              }

              rows.push({
                key: fieldKey,
                label: String(fieldLabel),
                value: String(displayValue),
              });
            });
          } else {
            const sourceLabel = tooltipFields[sourceField] || 'Source';
            const targetLabel = tooltipFields[targetField] || 'Target';
            const valueLabel = tooltipFields[valueField] || 'Value';

            rows = [
              {
                key: sourceField,
                label: String(sourceLabel),
                value: sourceName,
              },
              {
                key: targetField,
                label: String(targetLabel),
                value: targetName,
              },
              {
                key: valueField,
                label: String(valueLabel),
                value: String(params.data.value),
              },
            ];
          }

          return renderEChartsTooltipCard({
            title: `${sourceName} -> ${targetName}`,
            rows: rows.map((row) => ({
              ...row,
              markerShape: 'none' as const,
            })),
            minWidth: 180,
          });
        }

        if (params.dataType === 'node') {
          const nodeName = params.data.name.replace(/^(源_|协议_|目标_)/, '');
          return renderEChartsTooltipCard({
            title: nodeName,
            rows: [],
          });
        }

        return '';
      },
    },
    series: [
      {
        type: 'sankey',
        layout: 'none',
        layoutIterations: 32,
        nodeWidth: 20,
        nodeGap: 8,
        nodeAlign: 'left',
        draggable: false,
        focusNodeAdjacency: 'allEdges',
        data: chartData.nodes,
        links: chartData.links,
        lineStyle: {
          color: 'gradient',
          curveness: 0.5,
          opacity: 0.3,
        },
        label: {
          position: 'right',
          fontSize: 10,
          color: colors.textSecondary,
          formatter: function (params: any) {
            return params.name.replace(/^(源_|协议_|目标_)/, '');
          },
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 15,
            opacity: 0.9,
          },
        },
      },
    ],
  };

  return (
    <ChartSurface
      loading={loading}
      hasData={!!chartData.nodes.length}
      containerClassName="h-full w-full"
      loadingClassName="flex h-full w-full flex-col items-center justify-center"
      emptyClassName="h-full w-full"
      loadingContent={<Spin size="small" />}
    >
      <div className="h-full w-full">
        <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />
      </div>
    </ChartSurface>
  );
};

export default LogAnalysisSankey;
