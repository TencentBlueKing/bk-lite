import SimpleLineChart from "@/app/mlops/components/charts/simpleLineChart";
import useMlopsTaskApi from "@/app/mlops/api/task";
import { Spin } from "antd";
// import { LeftOutlined } from "@ant-design/icons";
import { useEffect, useState, useRef, useCallback } from "react";
import { useTranslation } from "@/utils/i18n";
import styles from './index.module.scss';

interface TrainTaskDetailProps {
  metricData: any,
  backToList: () => void
}

// 懒加载图表组件
interface LazyChartProps {
  metricName: string;
  runId: string;
  getMetricsDetail: (runId: string, metricsName: string) => Promise<any>;
}

const LazyChart: React.FC<LazyChartProps> = ({ metricName, runId, getMetricsDetail }) => {
  const { t } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const loadingRef = useRef(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const enterTimeRef = useRef<number | null>(null);
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Intersection Observer 实现懒加载
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
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
      // 清理定时器
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

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

  return (
    <div ref={chartRef} className={styles.metricCard}>
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
          <SimpleLineChart data={data} />
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
  // backToList
}: TrainTaskDetailProps) => {
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
      const response = await getTrainTaskMetrics(metricData.run_id);
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
    const data = await getTrainTaskMetricsDetail(runId, metricsName);
    return data;
  }, [getTrainTaskMetricsDetail]);

  return (
    <div className={styles.trainTaskDetail}>
      <div className={styles.taskDetailContainer}>
        {/* Header Section */}
        <div className={styles.taskHeader}>
          <div className={styles.taskHeaderContent}>
            <div className={styles.taskInfo}>
              {metricData?.run_name && (
                <div className={styles.taskInfoItem}>
                  <span className={styles.taskInfoLabel}>任务名称</span>
                  <span className={styles.taskInfoValue}>{metricData.run_name}</span>
                </div>
              )}
              {metricData?.run_id && (
                <div className={styles.taskInfoItem}>
                  <span className={styles.taskInfoLabel}>任务ID</span>
                  <span className={styles.taskInfoValue}>{metricData.run_id}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Content Section */}
        <div className={styles.taskContent}>
          {/* Loading State */}
          {loading && (
            <div className={styles.taskLoading}>
              <Spin size="large" />
              <span className={styles.taskLoadingText}>正在加载训练指标...</span>
            </div>
          )}

          {/* Metrics Grid */}
          {!loading && metrics.length > 0 && (
            <div className={styles.metricsSection}>
              <div className={styles.metricsHeader}>
                <h2 className={styles.metricsTitle}>训练指标</h2>
                <div className={styles.metricsCount}>{metrics.length} 个指标</div>
              </div>
              <div className={styles.metricsGrid}>
                {metrics.map((metricName) => (
                  <LazyChart
                    key={metricName}
                    metricName={metricName}
                    runId={metricData?.run_id}
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
              <div className={styles.taskEmptyTitle}>暂无训练指标</div>
              <div className={styles.taskEmptyDescription}>该任务还没有生成训练指标数据</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TrainTaskDetail;