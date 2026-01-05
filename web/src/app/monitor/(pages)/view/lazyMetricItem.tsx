'use client';

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from 'react';
import { Spin, Tooltip } from 'antd';
import { BellOutlined, SearchOutlined } from '@ant-design/icons';
import LineChart from '@/app/monitor/components/charts/lineChart';
import { TableDataItem, MetricItem, ChartData } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import { Dayjs } from 'dayjs';
import Icon from '@/components/icon';

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
      rootMargin: '50px',
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
      const displayUnit = item.displayUnit === 'short' ? '' : item.displayUnit;
      const unitName = findUnitNameById(displayUnit) || displayUnit;
      return unitName ? `（${unitName}）` : '\u00A0\u00A0';
    },
    [findUnitNameById]
  );

  return (
    <div
      ref={ref}
      className="w-[49%] border border-[var(--color-border-1)] p-[10px] mb-[10px]"
    >
      <div className="flex justify-between items-center">
        <div className="flex items-center w-[calc(100%-36px)] text-[14px] pr-[15px]">
          <div className="flex w-full box-border relative">
            <span
              className={`font-[600]  overflow-hidden text-ellipsis whitespace-nowrap`}
              title={item.display_name}
            >
              {item.display_name}
            </span>
            <div className="text-[var(--color-text-3)] text-[12px] relative">
              {getUnit(item)}
              <Tooltip placement="topLeft" title={item.display_description}>
                <div
                  className="absolute cursor-pointer inline-block"
                  style={{
                    top: '-4px',
                    right: '-6px',
                  }}
                >
                  <Icon type="a-shuoming2" className="text-[14px]" />
                </div>
              </Tooltip>
            </div>
          </div>
        </div>
        <div className="text-[var(--color-text-3)]">
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
            />
          </>
        )}
      </div>
    </div>
  );
};

export default React.memo(LazyMetricItem, (prevProps, nextProps) => {
  // 只有以下情况才重新渲染：
  return (
    prevProps.item.id === nextProps.item.id &&
    prevProps.item.viewData === nextProps.item.viewData &&
    prevProps.isLoading === nextProps.isLoading &&
    prevProps.resetKey === nextProps.resetKey &&
    prevProps.isLoaded === nextProps.isLoaded &&
    prevProps.isCancelled === nextProps.isCancelled &&
    prevProps.isInViewport === nextProps.isInViewport
  );
});
