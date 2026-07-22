import React, { useEffect, useMemo } from 'react';
import { Empty, Spin, Tooltip } from 'antd';
import type { ScreenRenderContext, ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { useTranslation } from '@/utils/i18n';
import { validateMultiValueData } from '@/app/ops-analysis/utils/multiValueData';
import { getOpsChartThemeByMode } from '@/app/ops-analysis/utils/chartTheme';
import { scaleScreenMetric } from './shared/screenMetrics';

interface ComMultiValueProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready: boolean) => void;
}

const ComMultiValue: React.FC<ComMultiValueProps> = ({
  rawData,
  loading = false,
  config,
  screenRenderContext,
  onReady,
}) => {
  const { t } = useTranslation();
  const theme = getOpsChartThemeByMode(config?.chartThemeMode);
  const errorMessage = t('dashboard.dataFormatMismatch');
  const result = useMemo(() => validateMultiValueData(rawData, errorMessage), [errorMessage, rawData]);

  useEffect(() => {
    if (!loading) onReady?.(result.isValid && result.items.length > 0);
  }, [loading, onReady, result]);

  if (loading) {
    return <div className="flex h-full items-center justify-center"><Spin size="small" /></div>;
  }
  if (!result.isValid) {
    return <div className="flex h-full items-center justify-center text-xs text-red-500">{result.errorMessage}</div>;
  }
  if (result.items.length === 0) {
    return <div className="flex h-full items-center justify-center"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /></div>;
  }

  const padding = scaleScreenMetric(8, screenRenderContext);
  return (
    <div className="h-full w-full overflow-y-auto overflow-x-hidden" style={{ padding }}>
      <div className="flex flex-col gap-1">
        {result.items.map((item, index) => (
          <div
            key={`${index}-${item.label}`}
            className="flex min-w-0 items-center justify-between gap-3 rounded px-2 py-1"
            style={{ color: theme.singleValueColor }}
          >
            <Tooltip title={item.label}>
              <span className="min-w-0 flex-1 truncate text-left">{item.label}</span>
            </Tooltip>
            <Tooltip title={item.value}>
              <span className="shrink-0 truncate text-right font-semibold tabular-nums">{item.value}</span>
            </Tooltip>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ComMultiValue;
