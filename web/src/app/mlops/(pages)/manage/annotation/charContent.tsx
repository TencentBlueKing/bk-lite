"use client";
import {
  useEffect,
  useState,
  useMemo,
  useCallback,
  useRef,
  Dispatch,
  SetStateAction
} from "react";
import { useSearchParams } from 'next/navigation';
import { cloneDeep } from "lodash";
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import { useTranslation } from "@/utils/i18n";
import useMlopsManageApi from "@/app/mlops/api/manage";
import {
  Button,
  message,
  Spin,
} from "antd";
import LineChart from "@/app/mlops/components/charts/lineChart";
import CustomTable from "@/components/custom-table";
import PermissionWrapper from '@/components/permission';
import { ColumnItem, TableDataItem, } from '@/app/mlops/types';
import { AnnotationData } from '@/app/mlops/types/manage';

const ChartContent = ({
  flag,
  isChange,
  setFlag,
  setIsChange
}: {
  flag: boolean,
  setFlag: Dispatch<SetStateAction<boolean>>,
  isChange: boolean,
  setIsChange: Dispatch<SetStateAction<boolean>>
}) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { getAnomalyTrainDataInfo, getTimeSeriesPredictTrainDataInfo, labelingData } = useMlopsManageApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [currentFileData, setCurrentFileData] = useState<AnnotationData[]>([]);
  const [loadingState, setLoadingState] = useState({
    loading: false,
    chartLoading: false,
    saveLoading: false,
  });
  // const [selectedTags, setSelectedTags] = useState<string[]>([]);
  // const [isChange, setIsChange] = useState<boolean>(false);
  // const [flag, setFlag] = useState<boolean>(true);
  const [timeline, setTimeline] = useState<any>({
    startIndex: 0,
    endIndex: 0,
  });
  const [tableScrollHeight, setTableScrollHeight] = useState<number>(400);
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const [chartData, setChartData] = useState<AnnotationData[]>([]);
  const [isAnimating, setIsAnimating] = useState<boolean>(false);
  const animationTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // const tagsData = ['is_train_data', 'is_val_data', 'is_test_data'];
  const getTrainDataInfoMap: Record<string, any> = {
    'anomaly': getAnomalyTrainDataInfo,
    'timeseries_predict': getTimeSeriesPredictTrainDataInfo
  };

  // useEffect(() => {
  //   setFlag(true);
  // }, [searchParams]);

  const {
    id,
    key
  } = useMemo(() => ({
    id: searchParams.get('id') || '',
    key: searchParams.get('activeTap')
  }), [searchParams]);

  const colmuns: ColumnItem[] = useMemo(() => {
    return [
      {
        title: t('mlops-common.time'),
        key: 'timestamp',
        dataIndex: 'timestamp',
        width: 80,
        align: 'center',
        render: (_, record) => {
          const time = new Date(record.timestamp * 1000).toISOString();
          return <p className="h-full place-content-center">{convertToLocalizedTime(time.toString(), 'YYYY-MM-DD HH:mm:ss')}</p>;
        },
      },
      {
        title: t('datasets.value'),
        key: 'value',
        dataIndex: 'value',
        align: 'center',
        width: 30,
        render: (_, record) => {
          const value = Number(record.value).toFixed(2);
          return <p className="h-full place-content-center">{value}</p>
        },
      },
      {
        title: t('datasets.labelResult'),
        key: 'label',
        dataIndex: 'label',
        width: 100,
        align: 'center',
        hidden: true
      },
      {
        title: t('mlops-common.action'),
        key: 'action',
        dataIndex: 'action',
        align: 'center',
        width: 30,
        render: (_, record) => {
          return (
            <PermissionWrapper requiredPermissions={['File Edit']}>
              <Button color="danger" variant="link" onClick={() => handleDelete(record)}>
                {t('common.delete')}
              </Button>
            </PermissionWrapper>
          )
        }
      }
    ];
  }, [t, convertToLocalizedTime]);

  // 动态计算表格滚动高度
  const calculateTableHeight = useCallback(() => {
    if (tableContainerRef.current) {
      const containerElement = tableContainerRef.current;
      const containerHeight = containerElement.clientHeight;

      // 计算需要减去的各个部分高度
      const buttonHeight = 60;
      const tableHeaderHeight = 40;
      const padding = 16;

      // 计算最终的表格内容滚动高度
      const calculatedHeight = containerHeight - buttonHeight - tableHeaderHeight - padding;
      const tableHeight = Math.max(150, calculatedHeight);

      setTableScrollHeight(tableHeight);
    } else {
      const viewportHeight = window.innerHeight;
      const fallbackHeight = Math.max(200, viewportHeight - 300);
      setTableScrollHeight(fallbackHeight);
    }
  }, []);

  const pagedData = useMemo(() => {
    if (!tableData.length) return [];
    return tableData;
  }, [tableData]);

  useEffect(() => {
    getCurrentFileData();
  }, [searchParams]);

  useEffect(() => {
    if (currentFileData.length && flag) {
      setTimeline({
        startIndex: 0,
        endIndex: currentFileData.length > 10 ? Math.floor(currentFileData.length / 10) : (currentFileData.length > 1 ? currentFileData.length - 1 : 0)
      });
      setFlag(false);
    }
  }, [currentFileData]);

  // 监听容器高度变化
  useEffect(() => {
    // 延迟初始计算，确保DOM渲染完成
    const timeoutId = setTimeout(calculateTableHeight, 300);

    const handleResize = () => {
      setTimeout(calculateTableHeight, 100);
    };

    window.addEventListener('resize', handleResize);

    // 使用 ResizeObserver 监听容器大小变化
    let resizeObserver: ResizeObserver | null = null;

    if (tableContainerRef.current && window.ResizeObserver) {
      resizeObserver = new ResizeObserver(() => {
        // 防抖处理，避免频繁计算
        setTimeout(calculateTableHeight, 50);
      });
      resizeObserver.observe(tableContainerRef.current);
    }

    return () => {
      clearTimeout(timeoutId);
      window.removeEventListener('resize', handleResize);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
    };
  }, [calculateTableHeight]);

  // 当数据加载完成后重新计算高度
  useEffect(() => {
    if (!loadingState.loading && tableData.length > 0) {
      setTimeout(calculateTableHeight, 100);
    }
  }, [loadingState.loading, tableData.length, calculateTableHeight]);

  // 监听侧边栏宽度变化，管理图表动画状态
  useEffect(() => {
    let observer: MutationObserver | null = null;

    const handleAnimationStart = () => {
      if (!isAnimating) {
        setIsAnimating(true);
        setChartData([]);
        setLoadingState(prev => ({ ...prev, chartLoading: true }));

        // 清除之前的定时器
        if (animationTimeoutRef.current) {
          clearTimeout(animationTimeoutRef.current);
        }
      }
    };

    const handleAnimationEnd = () => {
      animationTimeoutRef.current = setTimeout(() => {
        setIsAnimating(false);
        setChartData(currentFileData);
        setLoadingState(prev => ({ ...prev, chartLoading: false }));
        calculateTableHeight();
      }, 100);
    };

    if (window.MutationObserver) {
      observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
            const target = mutation.target as HTMLElement;
            // 检查是否是侧边栏的宽度变化
            if (target.tagName === 'ASIDE' && target.style.transition && target.style.transition.includes('width')) {
              handleAnimationStart();

              // 监听过渡结束事件
              const onTransitionEnd = (e: TransitionEvent) => {
                if (e.propertyName === 'width') {
                  handleAnimationEnd();
                  target.removeEventListener('transitionend', onTransitionEnd);
                }
              };

              target.addEventListener('transitionend', onTransitionEnd);
            }
          }
        });
      });

      // 观察侧边栏容器
      const asideElement = document.querySelector('aside');
      if (asideElement) {
        observer.observe(asideElement, {
          attributes: true,
          attributeFilter: ['style'],
          subtree: false
        });
      }
    }

    return () => {
      if (observer) {
        observer.disconnect();
      }
      if (animationTimeoutRef.current) {
        clearTimeout(animationTimeoutRef.current);
      }
    };
  }, [currentFileData, calculateTableHeight, isAnimating]);

  // 初始化图表数据
  useEffect(() => {
    if (!isAnimating) {
      setChartData(currentFileData);
    }
  }, [currentFileData, isAnimating]);

  const handleLabelData = useCallback((data: any[], points: number[] | undefined) => {
    const _data = cloneDeep(data).map((item, index) => ({
      ...item,
      index
    }));
    if (!points) {
      setCurrentFileData(data);
      setTableData([]);
      return;
    }
    points.forEach(item => {
      _data[item] = {
        ..._data[item],
        label: 1
      }
    });
    setCurrentFileData(_data);
    setTableData(_data.filter((item) => item.label === 1))
  }, []);

  const getCurrentFileData = useCallback(async () => {
    setLoadingState(prev => ({ ...prev, loading: true, chartLoading: true }));

    try {
      if (!key) return;
      const data = await getTrainDataInfoMap[key](id as string, true, true);
      handleLabelData(data?.train_data, data?.metadata?.anomaly_point);
    } catch (e) {
      console.log(e);
    } finally {
      setLoadingState(prev => ({ ...prev, loading: false, chartLoading: false }));
    }
  }, [searchParams]);

  const onXRangeChange = useCallback((data: any[]) => {
    if (!isChange) setIsChange(true);
    setLoadingState(prev => ({ ...prev, chartLoading: true }));
    if (!currentFileData.length) {
      setLoadingState(prev => ({ ...prev, chartLoading: false }));
      return;
    }
    try {
      const minTime = data[0].unix();
      const maxTime = data[1].unix();
      let newData;
      if (minTime === maxTime) {
        newData = currentFileData.map((item: any) =>
          item.timestamp === minTime ? { ...item, label: 1 } : item
        );
        setCurrentFileData(newData);
      } else {
        newData = currentFileData.map((item: any, index) =>
          item.timestamp >= minTime && item.timestamp <= maxTime
            ? { ...item, label: 1, index }
            : item
        );
      }
      const _tableData = newData.filter((item: any) => item.label === 1);
      setTableData(_tableData);
      setCurrentFileData(newData);
    } finally {
      setLoadingState(prev => ({ ...prev, chartLoading: false }));
    }
  }, [currentFileData]);

  const onAnnotationClick = useCallback((value: any[]) => {
    if (!value) return;
    if (!isChange) setIsChange(true);
    setLoadingState(prev => ({ ...prev, chartLoading: true }));
    try {
      const _data: any[] = cloneDeep(currentFileData);
      value.map((item: any) => {
        const index = _data.findIndex((k) => k.timestamp === item.timestamp);
        _data.splice(index, 1, {
          ...item,
          label: item.label ? 0 : 1
        })
      });
      const _tableData = _data.filter((item: any) => item.label === 1);
      setTableData(_tableData);
      setCurrentFileData(_data);
    } finally {
      setLoadingState(prev => ({ ...prev, chartLoading: false }));
    }
  }, [currentFileData]);

  const handleDelete = useCallback((record: ColumnItem) => {
    setIsChange(true);
    setLoadingState(prev => ({ ...prev, chartLoading: true }));
    try {
      const newData = currentFileData.map((item: any) =>
        item.timestamp === record.timestamp ? { ...item, label: 0 } : item
      );
      const _tableData = newData.filter((item: any) => item.label === 1);
      setCurrentFileData(newData);
      setTableData(_tableData);
    } finally {
      setLoadingState(prev => ({ ...prev, chartLoading: false }));
    }
  }, [currentFileData]);

  const handleSava = useCallback(async () => {
    setLoadingState(prev => ({ ...prev, saveLoading: true }));
    const id = searchParams.get('id');
    try {
      const points = tableData.map(item => item.index);
      const params = {
        metadata: {
          anomaly_point: points
        },
      }
      await labelingData(id as string, params);
      message.success(t('datasets.saveSuccess'));
      getCurrentFileData();
    } catch (e) {
      console.log(e);
      message.error(t('datasets.saveError'));
    } finally {
      setLoadingState(prev => ({ ...prev, saveLoading: false }));
      setIsChange(false);
    }
  }, [currentFileData, colmuns]);

  const handleCancel = () => {
    getCurrentFileData();
    setIsChange(false);
  };

  const onTimeLineChange = (value: any) => {
    setTimeline(value);
  };

  return (
    <>
      <Spin className="w-full" spinning={loadingState.chartLoading}>
        <div
          className="flex justify-between"
          style={{
            transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            height: `calc(100vh - 120px)`,
            minHeight: `calc(100vh - 120px)`,
            transform: 'translateZ(0)',
            willChange: 'width',
            backfaceVisibility: 'hidden',
          }}
        >
          <div className="w-[74%]">
            <div
              style={{
                width: '100%',
                height: '100%',
                // 在动画期间禁用pointer events提升性能
                pointerEvents: isAnimating ? 'none' : 'auto',
                // 启用硬件加速
                transform: 'translateZ(0)',
                backfaceVisibility: 'hidden',
              }}
            >
              <LineChart
                key="main-line-chart"
                data={chartData}
                timeline={timeline}
                showDimensionTable
                showDimensionFilter
                showBrush
                allowSelect={key === 'anomaly'}
                onXRangeChange={onXRangeChange}
                onTimeLineChange={onTimeLineChange}
                onAnnotationClick={key === 'anomaly' ? onAnnotationClick : undefined}
              />
            </div>
          </div>
          <div
            className="w-[25%] min-w-[285px] anomaly-container relative"
            ref={tableContainerRef}
            style={{
              height: `calc(100vh - 120px)`,
              minHeight: `calc(100vh - 120px)`,
              maxHeight: `calc(100vh - 120px)`,
              transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              willChange: 'width',
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            <div style={{
              width: '100%',
              height: '100%',
              position: 'absolute',
              top: 0,
              left: 0,
              transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              display: 'flex',
              flexDirection: 'column',
              pointerEvents: isAnimating ? 'none' : 'auto',
              transform: 'translateZ(0)',
              backfaceVisibility: 'hidden',
            }}>
              <CustomTable
                virtual
                size="small"
                rowKey="timestamp"
                scroll={{ y: tableScrollHeight }}
                columns={colmuns}
                dataSource={pagedData}
              />
              <div className="absolute bottom-0 right-0 flex justify-end gap-2 mb-4">
                {
                  key === 'anomaly' && (
                    <>
                      <Button className="mr-4" onClick={handleCancel}>{t('common.cancel')}</Button>
                      <PermissionWrapper requiredPermissions={['File Edit']}>
                        <Button type="primary" loading={loadingState.saveLoading} onClick={handleSava}>{t('common.save')}</Button>
                      </PermissionWrapper>
                    </>
                  )
                }
              </div>
            </div>
          </div>
        </div>
      </Spin>
    </>
  )
};

export default ChartContent;