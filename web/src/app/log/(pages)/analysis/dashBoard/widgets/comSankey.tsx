import React, { useEffect, useState, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/log/utils/randomColorForChart';
import { formatNumericValue } from '@/app/log/utils/common';

interface SankeyProps {
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

const Sankey: React.FC<SankeyProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const [chartInstance, setChartInstance] = useState<any>(null);
  const chartRef = useRef<any>(null);
  const chartColors = randomColorForLegend();

  const transformData = (rawData: any): SankeyData => {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return { nodes: [], links: [] };
    }

    // 获取配置参数，设置默认值
    const sourceField = config?.displayMaps?.sourceField || 'source.ip';
    const targetField = config?.displayMaps?.targetField || 'destination.ip';
    const valueField = config?.displayMaps?.valueField || 'flow_bytes';
    const middleField = config?.displayMaps?.middleField; // 可选的中间层字段，如 'network.transport'

    const links: (SankeyLink & { originalData?: any })[] = [];
    const nodeSet = new Set<string>();

    if (middleField) {
      // 三层桑基图：source -> middle -> target
      rawData.forEach((item: any) => {
        const source = item[sourceField];
        const middle = item[middleField];
        const target = item[targetField];
        const value = parseFloat(item[valueField]) || 0;

        if (source && middle && target && value > 0) {
          // 添加 source -> middle 的连接
          links.push({
            source: `源_${source}`,
            target: `协议_${middle}`,
            value: value,
            originalData: item,
          });

          // 添加 middle -> target 的连接
          links.push({
            source: `协议_${middle}`,
            target: `目标_${target}`,
            value: value,
            originalData: item,
          });

          nodeSet.add(`源_${source}`);
          nodeSet.add(`协议_${middle}`);
          nodeSet.add(`目标_${target}`);
        }
      });
    } else {
      // 两层桑基图：source -> target
      // 为了避免循环，我们给源和目标添加不同的前缀
      rawData.forEach((item: any) => {
        const source = item[sourceField];
        const target = item[targetField];
        const value = parseFloat(item[valueField]) || 0;

        if (source && target && value > 0) {
          // 避免自环：如果source和target相同，跳过
          if (source === target) {
            return;
          }

          links.push({
            source: `源_${source}`,
            target: `目标_${target}`,
            value: value,
            originalData: item,
          });

          nodeSet.add(`源_${source}`);
          nodeSet.add(`目标_${target}`);
        }
      });
    }

    // 合并相同source-target的连接
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

    // 计算最大值用于线宽缩放
    const maxValue = Math.max(...mergedLinks.map((link) => link.value));

    // 为每个连接添加线宽属性，确保最小宽度为10px
    const linksWithWidth = mergedLinks.map((link) => ({
      ...link,
      lineStyle: {
        width: Math.max(10, Math.min(30, (link.value / maxValue) * 20 + 10)), // 最小10px，最大30px
        opacity: 0.7,
      },
    }));

    const nodes: SankeyNode[] = Array.from(nodeSet).map((name) => ({ name }));

    return { nodes, links: linksWithWidth };
  };

  const chartData: SankeyData = transformData(rawData);

  useEffect(() => {
    if (!loading) {
      const hasData =
        chartData && chartData.nodes.length > 0 && chartData.links.length > 0;
      setIsDataReady(hasData);
      if (onReady) {
        onReady(hasData);
      }
    }
  }, [chartData, loading, onReady]);

  const option: any = {
    color: chartColors,
    animation: false,
    title: { show: false },
    grid: {
      left: 10,
      right: 30, // 减少右边距
      top: 10,
      bottom: 10,
    },
    tooltip: {
      trigger: 'item',
      triggerOn: 'mousemove',
      enterable: true,
      confine: true,
      extraCssText: 'box-shadow: 0 0 3px rgba(150,150,150, 0.7);',
      textStyle: {
        fontSize: 12,
      },
      formatter: function (params: any) {
        if (params.dataType === 'edge') {
          // 连接线的tooltip - 显示配置的字段信息
          const sourceName = params.data.source.replace(
            /^(源_|协议_|目标_)/,
            ''
          );
          const targetName = params.data.target.replace(
            /^(源_|协议_|目标_)/,
            ''
          );

          // 获取tooltip字段配置
          const tooltipFields = config?.displayMaps?.tooltipFields || {};
          const sourceField = config?.displayMaps?.sourceField || 'source.ip';
          const targetField =
            config?.displayMaps?.targetField || 'destination.ip';
          const valueField = config?.displayMaps?.valueField || 'flow_bytes';

          let tooltipContent = '';

          // 如果有原始数据，展示配置的字段
          if (params.data.originalData && params.data.originalData.length > 0) {
            const firstItem = params.data.originalData[0];

            // 动态生成tooltip内容
            Object.entries(tooltipFields).forEach(([fieldKey, fieldLabel]) => {
              let displayValue = firstItem[fieldKey];

              // 检查是否为空值
              if (
                displayValue === undefined ||
                displayValue === null ||
                displayValue === ''
              ) {
                displayValue = '--';
              } else {
                // 特殊处理值字段，如果是流量相关字段，格式化为GB
                if (
                  fieldKey === valueField &&
                  typeof displayValue === 'number'
                ) {
                  displayValue = (displayValue / (1024 * 1024 * 1024)).toFixed(
                    2
                  );
                }
              }
              if (fieldKey === 'flow_bytes') {
                displayValue = formatNumericValue(displayValue);
              }
              tooltipContent += `<div>${fieldLabel}：${displayValue}</div>`;
            });
          } else {
            // 降级处理：显示基本信息
            const sourceLabel = tooltipFields[sourceField] || 'Source';
            const targetLabel = tooltipFields[targetField] || 'Target';
            const valueLabel = tooltipFields[valueField] || 'Value';

            tooltipContent = `
              <div>${sourceLabel}：${sourceName}</div>
              <div>${targetLabel}：${targetName}</div>
              <div>${valueLabel}：${params.data.value}</div>
            `;
          }

          return `
            <div style="padding: 6px 10px; line-height: 1.5;">
              ${tooltipContent}
            </div>
          `;
        } else if (params.dataType === 'node') {
          // 节点的tooltip - 移除前缀显示原始名称
          const nodeName = params.data.name.replace(/^(源_|协议_|目标_)/, '');
          return `
            <div style="padding: 4px 8px;">
              <div style="margin-bottom: 4px; font-weight: bold;">${nodeName}</div>
            </div>
          `;
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
        nodeAlign: 'left', // 改为左对齐，减少右边空白
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
          color: '#333',
          formatter: function (params: any) {
            // 移除前缀显示原始名称
            return params.name.replace(/^(源_|协议_|目标_)/, '');
          },
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 15, // hover时线宽增加
            opacity: 0.9,
          },
        },
      },
    ],
  };

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady || !chartData || chartData.nodes.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <ReactEcharts
        ref={chartRef}
        option={option}
        style={{ height: '100%', width: '100%' }}
        onChartReady={(chart: any) => {
          setChartInstance(chart);
          console.log(chartInstance);
        }}
      />
    </div>
  );
};

export default Sankey;
