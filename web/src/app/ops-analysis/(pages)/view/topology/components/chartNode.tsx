import React, { useCallback, useState, useEffect } from 'react';
import { ConfigProvider, Spin } from 'antd';
import { IntlProvider } from 'react-intl';
import type { Node } from '@antv/x6';
import { useTranslation } from '@/utils/i18n';
import { NODE_DEFAULTS } from '../constants/nodeDefaults';
import { getLocaleData } from '../utils/localeStore';
import {
  getOpsChartThemeByMode,
} from '@/app/ops-analysis/utils/chartTheme';
import WidgetRenderer from '@/app/ops-analysis/components/widgetRenderer';
import WidgetErrorState from '@/app/ops-analysis/components/widgetErrorState';

interface ChartNodeProps {
  node: Node;
}

const ChartNodeContent: React.FC<ChartNodeProps> = ({ node }) => {
  const { t } = useTranslation();
  const [nodeData, setNodeData] = useState(() => node.getData() || {});

  useEffect(() => {
    const handleDataChange = () => {
      setNodeData({ ...node.getData() });
    };
    node.on('change:data', handleDataChange);
    return () => {
      node.off('change:data', handleDataChange);
    };
  }, [node]);
  const {
    valueConfig,
    styleConfig,
    isLoading,
    rawData,
    hasError,
    errorMessage,
    name: componentName,
    description,
    dataSource,
    onTableQueryChange,
    presentationRole,
  } = nodeData;

  const chartTheme = getOpsChartThemeByMode(valueConfig?.chartThemeMode);
  const width = styleConfig?.width || NODE_DEFAULTS.CHART_NODE.width;
  const height = styleConfig?.height || NODE_DEFAULTS.CHART_NODE.height;

  const handleQueryChange = useCallback((params: Record<string, any>) => {
    if (onTableQueryChange) {
      onTableQueryChange(node.id, params);
    }
  }, [node.id, onTableQueryChange]);

  const chartType = valueConfig?.chartType;
  const isTableLikeChart = chartType === 'table' || chartType === 'eventTable';

  const widgetProps = {
    rawData: rawData || null,
    loading: isLoading || false,
    config: valueConfig,
    dataSource,
    ...(isTableLikeChart ? { onQueryChange: handleQueryChange } : {}),
  };
  const shouldShowLoading =
    (isLoading || (!rawData && !hasError)) && !isTableLikeChart;
  const shouldShowError = hasError && !isLoading;
  const normalizedDescription = description?.trim();
  const usesScreenChartTheme =
    valueConfig?.chartThemeMode === 'screen-dark' ||
    valueConfig?.chartThemeMode === 'screen-light';
  const isPresentationPanel =
    usesScreenChartTheme &&
    (
      presentationRole === 'side-panel' ||
      presentationRole === 'kpi' ||
      presentationRole === 'metric-callout'
    );

  return (
    <div
      className={
        isPresentationPanel
          ? `ops-topology-screen-panel ${
              presentationRole === 'metric-callout' ? 'ops-topology-screen-callout' : ''
            }`
          : undefined
      }
      style={{
        '--ops-screen-panel-corner': chartTheme.panelCornerAccentColor,
        width: `${width}px`,
        height: `${height}px`,
        border: isPresentationPanel
          ? '1px solid var(--ops-screen-panel-border, rgba(45, 212, 255, 0.34))'
          : `1px solid ${chartTheme.panelBorderColor}`,
        borderRadius: isPresentationPanel ? '6px' : '18px',
        backgroundColor: isPresentationPanel
          ? 'var(--ops-screen-panel-bg, rgba(8, 22, 45, 0.76))'
          : chartTheme.panelBg,
        boxShadow: isPresentationPanel
          ? 'inset 0 1px 0 rgba(148, 230, 255, 0.18), 0 0 22px rgba(14, 165, 233, 0.16)'
          : 'none',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        position: 'relative',
      } as React.CSSProperties}
    >
      {componentName && (
        <div
          style={{
            padding: '14px 14px 10px',
            backgroundColor: isPresentationPanel
              ? 'var(--ops-screen-panel-header-bg, rgba(7, 18, 38, 0.7))'
              : chartTheme.panelBg,
            borderBottom: isPresentationPanel
              ? '1px solid var(--ops-screen-panel-divider, rgba(45, 212, 255, 0.18))'
              : `1px solid ${chartTheme.panelBorderColor}`,
          }}
        >
          <div
            style={{
              fontSize: '14px',
              fontWeight: '600',
              color: isPresentationPanel
                ? 'var(--ops-screen-text, #DDF8FF)'
                : chartTheme.panelTitleColor,
              marginBottom: normalizedDescription ? '4px' : 0,
              lineHeight: '20px',
            }}
          >
            {componentName}
          </div>
          {normalizedDescription && (
            <div
              style={{
                fontSize: '12px',
                color: isPresentationPanel
                  ? 'var(--ops-screen-muted-text, rgba(142, 219, 255, 0.72))'
                  : chartTheme.panelDescriptionColor,
                lineHeight: '16px',
                opacity: 0.8,
              }}
            >
              {normalizedDescription}
            </div>
          )}
        </div>
      )}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          position: 'relative',
          padding: '12px',
          backgroundColor: isPresentationPanel
            ? 'var(--ops-screen-panel-body-bg, rgba(7, 18, 38, 0.48))'
            : chartTheme.panelBg,
        }}
      >
        {shouldShowLoading ? (
          <div className="h-full flex flex-col items-center justify-center">
            <Spin size="small" />
            <div className="text-xs text-gray-500 mt-2">
              {t('common.loading')}
            </div>
          </div>
        ) : shouldShowError ? (
          <WidgetErrorState
            message={errorMessage || t('dashboard.dataFetchFailed')}
          />
        ) : (
          <div
            className="h-full min-h-0 w-full overflow-hidden"
            onClick={(e) => {
              e.stopPropagation();
            }}
            onMouseDown={(e) => {
              e.stopPropagation();
            }}
            onPointerDown={(e) => {
              e.stopPropagation();
            }}
            onKeyDown={(e) => {
              e.stopPropagation();
            }}
            onWheel={(e) => {
              e.stopPropagation();
            }}
          >
            <ConfigProvider getPopupContainer={() => document.body}>
              <WidgetRenderer
                chartType={chartType}
                {...widgetProps}
                fallback={
                  <div className="h-full flex flex-col items-center justify-center">
                    <div className="text-xs text-gray-500">
                      Unknown chart type: {chartType}
                    </div>
                  </div>
                }
              />
            </ConfigProvider>
          </div>
        )}
      </div>
    </div>
  );
};

const ChartNode: React.FC<ChartNodeProps> = ({ node }) => {
  const { locale, messages } = getLocaleData();
  return (
    // @ts-expect-error react-intl type incompatibility with React 19
    <IntlProvider locale={locale} messages={messages}>
      <ChartNodeContent node={node} />
    </IntlProvider>
  );
};

export default ChartNode;
