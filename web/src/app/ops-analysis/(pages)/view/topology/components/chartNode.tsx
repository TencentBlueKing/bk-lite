import React from 'react';
import { Spin } from 'antd';
import type { Node } from '@antv/x6';
import { NODE_DEFAULTS } from '../constants/nodeDefaults';
import ComLine from '../../dashBoard/widgets/comLine';
import ComPie from '../../dashBoard/widgets/comPie';
import ComBar from '../../dashBoard/widgets/comBar';

const componentMap: Record<string, React.ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
};

interface ChartNodeProps {
  node: Node;
}

const ChartNode: React.FC<ChartNodeProps> = ({ node }) => {
  const nodeData = node.getData();
  const {
    valueConfig,
    styleConfig,
    isLoading,
    rawData,
    hasError,
    name: componentName,
    description,
  } = nodeData;

  const width = styleConfig?.width || NODE_DEFAULTS.CHART_NODE.width;
  const height = styleConfig?.height || NODE_DEFAULTS.CHART_NODE.height;

  const widgetProps = {
    rawData: rawData || null,
    loading: isLoading || false,
  };

  const shouldShowLoading = isLoading || (!rawData && !hasError);

  const Component = valueConfig.chartType
    ? componentMap[valueConfig.chartType]
    : null;

  return (
    <div
      style={{
        width: `${width}px`,
        height: `${height}px`,
        border: '1px solid var(--color-border-2)',
        borderRadius: '6px',
        backgroundColor: 'var(--color-bg-1)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {componentName && (
        <div
          style={{
            padding: '12px 12px 8px',
            backgroundColor: 'var(--color-bg-2)',
          }}
        >
          <div
            style={{
              fontSize: '14px',
              fontWeight: '500',
              color: 'var(--color-text-1)',
              marginBottom: '4px',
              lineHeight: '20px',
            }}
          >
            {componentName}
          </div>
          <div
            style={{
              fontSize: '12px',
              color: 'var(--color-text-3)',
              lineHeight: '16px',
              opacity: 0.8,
            }}
          >
            {description || '--'}
          </div>
        </div>
      )}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          position: 'relative',
          padding: '8px',
        }}
      >
        {shouldShowLoading ? (
          <div className="h-full flex flex-col items-center justify-center">
            <Spin size="small" />
            <div className="text-xs text-gray-500 mt-2">
              {hasError ? 'Load Failed' : 'Loading...'}
            </div>
          </div>
        ) : Component ? (
          <div
            className="h-full w-full"
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
            }}
            onMouseDown={(e) => {
              e.stopPropagation();
            }}
          >
            <Component {...widgetProps} />
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center">
            <div className="text-xs text-gray-500">
              Unknown chart type: {valueConfig.chartType}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChartNode;
