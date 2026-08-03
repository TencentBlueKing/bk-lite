'use client';

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo
} from 'react';
import { Spin, Tooltip } from 'antd';
import { BellOutlined, SearchOutlined } from '@ant-design/icons';
import LineChart from '@/app/monitor/components/charts/lineChart';
import { TableDataItem, MetricItem, ChartData } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { Dayjs } from 'dayjs';
import Icon from '@/components/icon';
import { areLazyMetricItemPropsEqual } from './lazyMetricItemMemo';

interface LazyMetricItemProps {
  item: MetricItem;
  isLoading: boolean;
  onVisible: (metric: MetricItem) => void;
  onSearchClick: (item: MetricItem) => void;
  onPolicyClick: (item: MetricItem) => void;
  onXRangeChange: (arr: [Dayjs, Dayjs]) => void;
  resetKey?: number;
  isLoaded: boolean;
  isCancelled: boolean;
  onVisibilityChange: (metricId: number, isVisible: boolean) => void;
  isInViewport: boolean;
  xAxisDomain?: [number, number];
}

const LazyMetricItem: React.FC<LazyMetricItemProps> = ({
  item,
  isLoading,
  onVisible,
  onSearchClick,
  onPolicyClick,
  onXRangeChange,
  resetKey = 0,
  isLoaded,
  isCancelled,
  onVisibilityChange,
  isInViewport,
  xAxisDomain
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const [hasBeenVisible, setHasBeenVisible] = useState(false);
  const { t } = useTranslation();
  const { findUnitNameById } = useUnitTransform();

  // 缓存 observer 配置
  const observerOptions = useMemo(
    () => ({
      threshold: 0.1,
      // 两列卡片高度约 220px；预取下一行，避免滚动到卡片后才开始等待请求。
      rootMargin: '240px 0px'
    }),
    []
  );

  // 重置可见状态
  useEffect(() => {
    setHasBeenVisible(false);
  }, [resetKey]);

  // IntersectionObserver 懒加载逻辑
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    // 创建 observer
    const observer = new IntersectionObserver(([entry]) => {
      const isCurrentlyVisible = entry.isIntersecting;
      onVisibilityChange(item.id, isCurrentlyVisible);

      if (
        isCurrentlyVisible &&
        (!hasBeenVisible || (isCancelled && !isLoading))
      ) {
        setHasBeenVisible(true);
        onVisible(item);
      }
    }, observerOptions);

    observerRef.current = observer;
    observer.observe(element);

    // Cleanup
    return () => {
      if (observerRef.current && element) {
        observerRef.current.unobserve(element);
        observerRef.current.disconnect();
        observerRef.current = null;
      }
    };
  }, [item.id, hasBeenVisible, isCancelled, isLoading, observerOptions]);

  const getUnit = useCallback(
    (item: TableDataItem) => {
      const unitName = findUnitNameById(item.displayUnit);
      return unitName ? `（${unitName}）` : '\u00A0\u00A0';
    },
    [findUnitNameById]
  );

  return (
    <div
      ref={ref}
      className="w-[49%] border border-[var(--color-border-1)] p-[10px] mb-[10px]"
    >
      <div className="flex justify-between items-start gap-[8px]">
        <div className="min-w-0 flex-1 text-[14px]">
          <div className="flex items-center min-w-0">
            <span
              className="font-[600] overflow-hidden text-ellipsis whitespace-nowrap"
              title={`${item.display_name || ''}${item.name ? ` (${item.name})` : ''}`}
            >
              {item.display_name}
            </span>
            <span className="text-[var(--color-text-3)] text-[12px] shrink-0 ml-[2px]">
              {getUnit(item)}
            </span>
            <Tooltip placement="topLeft" title={item.display_description}>
              <span className="inline-flex items-center shrink-0 ml-[2px] cursor-pointer text-[var(--color-text-3)] leading-none">
                <Icon type="a-shuoming2" className="text-[14px]" />
              </span>
            </Tooltip>
            {item.seriesBudget?.truncated ? (
              <Tooltip
                placement="top"
                title={t('monitor.views.seriesTruncated', '', {
                  limit: item.seriesBudget.limit
                })}
              >
                <span className="ml-[8px] shrink-0 text-[12px] text-[var(--color-warning)] cursor-default whitespace-nowrap">
                  {t('monitor.views.seriesTruncatedShort', '', {
                    limit: item.seriesBudget.limit
                  })}
                </span>
              </Tooltip>
            ) : null}
          </div>
          {item.name ? (
            <div
              className="mt-[2px] text-[12px] leading-[18px] text-[var(--color-text-3)] overflow-hidden text-ellipsis whitespace-nowrap"
              title={item.name}
            >
              {item.name}
            </div>
          ) : null}
        </div>
        <div className="shrink-0 text-[var(--color-text-3)] leading-none pt-[2px]">
          <Tooltip placement="topRight" title={t('monitor.views.quickSearch')}>
            <SearchOutlined
              className="cursor-pointer"
              onClick={() => onSearchClick(item)}
            />
          </Tooltip>
          <Tooltip
            placement="topRight"
            title={t('monitor.events.createPolicy')}
          >
            <BellOutlined
              className="ml-[6px] cursor-pointer"
              onClick={() => onPolicyClick(item)}
            />
          </Tooltip>
        </div>
      </div>
      <div className="h-[200px] mt-[10px] relative">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Spin />
          </div>
        ) : (
          <>
            <LineChart
              metric={item}
              data={
                isInViewport && isLoaded
                  ? (item.viewData as ChartData[]) || []
                  : []
              }
              unit={item.displayUnit}
              onXRangeChange={onXRangeChange}
              xAxisDomain={xAxisDomain}
            />
          </>
        )}
      </div>
    </div>
  );
};

export default React.memo(LazyMetricItem, areLazyMetricItemPropsEqual);
