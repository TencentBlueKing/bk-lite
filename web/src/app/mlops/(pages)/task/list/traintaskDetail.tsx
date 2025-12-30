import SimpleLineChart from "@/app/mlops/components/charts/simpleLineChart";
import HorizontalBarChart from "@/app/mlops/components/charts/horizontalBarChart";
import useMlopsTaskApi from "@/app/mlops/api/task";
import { Spin } from "antd";
// import { LeftOutlined } from "@ant-design/icons";
import { useEffect, useState, useRef, useCallback } from "react";
import { useTranslation } from "@/utils/i18n";
import styles from './index.module.scss';

interface TrainTaskDetailProps {
  metricData: any,
  backToList: () => void,
  activeKey: string
}

// 懒加载图表组件
interface LazyChartProps {
  metricName: string;
  runId: string;
  status: string;
  getMetricsDetail: (runId: string, metricsName: string) => Promise<any>;
}

const LazyChart: React.FC<LazyChartProps> = ({ metricName, runId, status, getMetricsDetail }) => {
  const { t } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const enterTimeRef = useRef<number | null>(null);
  const isInViewportRef = useRef(false);
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Intersection Observer 实现懒加载
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            // 标记进入视口
            isInViewportRef.current = true;
            
            // 记录进入视口的时间
            enterTimeRef.current = Date.now();

            // 如果正在加载中，不重复发起请求
            if (loadingRef.current) {
              return;
            }

            // 清除之前的延时器
            if (timeoutRef.current) {
              clearTimeout(timeoutRef.current);
            }

            // 延迟执行，给用户滑过去的时间
            timeoutRef.current = setTimeout(() => {
              // 检查是否仍在视口内，且停留时间足够
              const now = Date.now();
              const stayTime = enterTimeRef.current ? now - enterTimeRef.current : 0;

              // 只有停留时间超过600ms才加载数据
              if (stayTime >= 600) {
                loadChartData();
              }
            }, 600);
          } else {
            // 标记离开视口
            isInViewportRef.current = false;
            
            // 离开视口时清除定时器
            if (timeoutRef.current) {
              clearTimeout(timeoutRef.current);
              timeoutRef.current = null;
            }
            enterTimeRef.current = null;
          }
        });
      },
      {
        threshold: 0.1,
        rootMargin: '50px'
      }
    );

    if (chartRef.current) {
      observer.observe(chartRef.current);
    }

    return () => {
      if (chartRef.current) {
        observer.unobserve(chartRef.current);
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [metricName]);

  const loadChartData = async () => {
    if (loadingRef.current) return;

    setLoading(true);
    loadingRef.current = true;
    try {
      const detailInfo = await getMetricsDetail(runId, metricName);
      const { metric_history } = detailInfo;
      setData(metric_history);
    } catch (error) {
      console.error(`加载指标 ${metricName} 数据失败:`, error);
      setData([]);
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  };

  // 轮询更新数据
  const updateChartData = async () => {
    try {
      const detailInfo = await getMetricsDetail(runId, metricName);
      const newData = detailInfo?.metric_history || [];
      
      // 使用函数式更新，确保获取最新的 state
      setData(prevData => {
        const merged = mergeData(prevData, newData);
        
        if (merged.length !== prevData.length) {
          console.log(`[Data] ${metricName}: ${prevData.length} → ${merged.length} (+${merged.length - prevData.length})`);
          return merged;
        }
        
        return prevData;  // 无变化则返回原数据，避免重新渲染
      });
    } catch (error) {
      console.error(`[Error] ${metricName} 更新失败:`, error);
    }
  };

  // 数据去重合并
  const mergeData = (oldData: any[], newData: any[]): any[] => {
    if (!oldData.length) return newData;
    if (!newData.length) return oldData;
    
    const maxStep = oldData[oldData.length - 1].step;
    const incremental = newData.filter(d => d.step > maxStep);
    
    return incremental.length > 0 ? [...oldData, ...incremental] : oldData;
  };

  // 轮询定时器
  useEffect(() => {
    if (status !== 'RUNNING') {
      return;
    }
    
    pollingTimerRef.current = setInterval(() => {
      if (isInViewportRef.current) {
        updateChartData();
      }
    }, 10000);
    
    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
      }
    };
  }, [status, metricName, updateChartData]);

  // 判断是否为单一数值指标（step为0表示没有step数据）
  const isSingleValueMetric = (data: any[]) => {
    return data.length === 1 && data[0]?.step === 0;
  };

  // 转换数据格式为横向柱状图所需格式
  const transformToBarData = (data: any[]) => {
    if (data.length > 0) {
      return [{ name: metricName, value: data[0].value }];
    }
    return [];
  };

  return (
    <div ref={chartRef} className={styles.metricCard} style={{ width: '49%' }}>
      <div className={styles.metricCardHeader}>
        <h3 className={styles.metricCardTitle}>
          {metricName}
        </h3>
      </div>
      <div className={styles.metricCardContent}>
        {loading ? (
          <div className={styles.metricCardLoading}>
            <Spin size="small" />
          </div>
        ) : data.length > 0 ? (
          isSingleValueMetric(data) ? (
            <HorizontalBarChart 
              data={transformToBarData(data)} 
              minValue={data[0].value >= 0 ? 0 : data[0].value * 1.2}
              maxValue={data[0].value >= 0 ? data[0].value * 1.2 : 0}
            />
          ) : (
            <SimpleLineChart data={data} />
          )
        ) : (
          <div className={styles.metricCardEmpty}>
            <span className={styles.metricCardEmptyText}>
              {t(`common.noData`)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

const TrainTaskDetail = ({
  metricData,
  activeKey
  // backToList
}: TrainTaskDetailProps) => {
  const { t } = useTranslation();
  const [metrics, setMetricsList] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const { getTrainTaskMetrics, getTrainTaskMetricsDetail } = useMlopsTaskApi();

  // 进入页面时获取指标列表
  useEffect(() => {
    if (metricData?.run_id) {
      getMetricsList();
    }
  }, [metricData?.run_id]);

  const getMetricsList = async () => {
    if (!metricData?.run_id) return;

    setLoading(true);
    try {
      const response = await getTrainTaskMetrics(metricData.run_id, activeKey);
      if (response?.metrics) {
        setMetricsList(response.metrics);
      }
    } catch (error) {
      console.error('获取指标列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const getMetricsDetail = useCallback(async (runId: string, metricsName: string) => {
    const data = await getTrainTaskMetricsDetail(runId, metricsName, activeKey);
    return data;
  }, [getTrainTaskMetricsDetail]);

  return (
    <div className={styles.trainTaskDetail}>
      <div className={styles.taskDetailContainer}>
        {/* Content Section */}
        <div className={styles.taskContent}>
          {/* Loading State */}
          {loading && (
            <div className={styles.taskLoading}>
              <Spin size="large" />
              <span className={styles.taskLoadingText}>{t(`mlops-common.loadingData`)}</span>
            </div>
          )}

          {/* Metrics Grid */}
          {!loading && metrics.length > 0 && (
            <div className={styles.metricsSection}>
              {/* <div className={styles.metricsHeader}>
                <h2 className={styles.metricsTitle}>训练指标</h2>
                <div className={styles.metricsCount}>{metrics.length} 个指标</div>
              </div> */}
              <div className={styles.metricsGrid}>
                {metrics.map((metricName) => (
                  <LazyChart
                    key={metricName}
                    metricName={metricName}
                    runId={metricData?.run_id}
                    status={metricData?.status}
                    getMetricsDetail={getMetricsDetail}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {!loading && metrics.length === 0 && (
            <div className={styles.taskEmpty}>
              <div className={styles.taskEmptyIcon}>📊</div>
              <div className={styles.taskEmptyTitle}>{t(`common.noData`)}</div>
              <div className={styles.taskEmptyDescription}>{t(`common.noData`)}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TrainTaskDetail;