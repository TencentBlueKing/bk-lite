import { Button, Upload, message, Select, Spin, Slider, Modal, InputNumber } from "antd";
import type { UploadProps } from 'antd';
import { handleFileRead } from "@/app/playground/utils/common";
import { useCallback, useState, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/utils/i18n";
import LineChart from "@/app/playground/components/charts/lineChart";
import CustomTable from "@/components/custom-table";
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import usePlayroundApi from "@/app/playground/api";
import cssStyle from './index.module.scss'
import { ColumnItem, Option } from "@/types";

// 定义数据类型
interface ChartDataItem {
  timestamp: number;
  value: number;
  label?: number;
  anomaly_probability?: number;
  [key: string]: any
}

const TimeseriesPredict = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { convertToLocalizedTime } = useLocalizedTime();
  const {
    timeseriesPredictReason,
    getCapabilityDetail,
    getSampleFileOfCapability,
    getSampleFileDetail
  } = usePlayroundApi();

  // 基础状态
  const [currentFileId, setCurrentFileId] = useState<string | null>(null);
  const [selectId, setSelectId] = useState<number | null>(null);
  const [capabilityData, setCapabilityData] = useState<any>(null);
  const [steps, setSteps] = useState<number>(1);
  const [sampleOptions, setSampleOptions] = useState<Option[]>([]);
  const [chartLoading, setChartLoading] = useState<boolean>(false);
  const [predictData, setPredictData] = useState<any[]>([]);

  // 弹窗相关状态
  const [modalVisible, setModalVisible] = useState<boolean>(false);

  // 懒加载相关状态
  const [allData, setAllData] = useState<ChartDataItem[]>([
    {
      "value": 27.43789942218143,
      "timestamp": 1704038400
    },
    {
      "value": 26.033612999373652,
      "timestamp": 1704038460
    },
    {
      "value": 36.30777324191053,
      "timestamp": 1704038520
    },
    {
      "value": 33.70226097527219,
      "timestamp": 1704038580
    }
  ]);
  const [visibleRange, setVisibleRange] = useState<number[]>([0, 100]);
  const [maxRenderCount] = useState(2000);
  const [isLargeDataset, setIsLargeDataset] = useState(false);
  const [isRangeChanging, setIsRangeChanging] = useState(false);

  //  使用 ref 来存储临时范围，避免频繁的状态更新
  const tempVisibleRangeRef = useRef<number[]>([0, 100]);
  const [tempVisibleRange, setTempVisibleRange] = useState<number[]>([0, 100]); // 只用于显示

  // 添加初始化标记，防止重复调用
  const [isInitialized, setIsInitialized] = useState(false);

  // 使用 useRef 来处理防抖和缓存值
  const rangeChangeTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isDraggingRef = useRef(false);
  const allDataRef = useRef<ChartDataItem[]>(allData);

  // 同步状态到 ref
  useEffect(() => {
    allDataRef.current = allData;
    tempVisibleRangeRef.current = tempVisibleRange;
  }, [allData, tempVisibleRange]);

  // 合并历史数据和预测数据
  const mergedData = useMemo(() => {
    if (!allData || allData.length === 0) return [];
    
    // 只有历史数据，没有预测数据
    if (!predictData || predictData.length === 0) {
      return allData.map(item => ({
        timestamp: item.timestamp,
        value1: item.value,  // 使用 value1
        value2: null
      }));
    }
    
    // 转换历史数据格式
    const historyData = allData.map(item => ({
      timestamp: item.timestamp,
      value1: item.value,  // 使用 value1
      value2: null
    }));
    
    // 获取最后一个历史数据点，作为分界点
    const lastHistoryItem = allData[allData.length - 1];
    
    // 转换预测数据格式（直接使用Unix时间戳）
    const predictDataFormatted = predictData.map(item => {
      return {
        timestamp: item.timestamp,  // 直接使用Unix时间戳（秒级）
        value1: null,
        value2: item.value  // 使用 value2
      };
    });
    
    // 在分界点添加重叠点，实现平滑过渡
    if (historyData.length > 0) {
      historyData[historyData.length - 1].value2 = lastHistoryItem.value;
    }
    
    return [...historyData, ...predictDataFormatted];
  }, [allData, predictData]);

  // 计算当前显示的数据
  const chartData = useMemo(() => {
    if (!mergedData || mergedData.length === 0) return [];

    // 如果数据量小于阈值，直接返回所有数据
    if (mergedData.length <= maxRenderCount) {
      return mergedData;
    }

    // 计算可见范围内的数据索引（使用实际范围，不是临时范围）
    const totalCount = mergedData.length;
    const startIndex = Math.floor((visibleRange[0] / 100) * totalCount);
    const endIndex = Math.min(
      Math.ceil((visibleRange[1] / 100) * totalCount),
      totalCount
    );

    // 确保渲染的数据量不超过最大值
    const rangeSize = endIndex - startIndex;
    if (rangeSize > maxRenderCount) {
      // 等间距采样
      const step = Math.ceil(rangeSize / maxRenderCount);
      const sampledData: any[] = [];
      for (let i = startIndex; i < endIndex; i += step) {
        sampledData.push(mergedData[i]);
      }
      return sampledData;
    }

    return mergedData.slice(startIndex, endIndex);
  }, [mergedData, visibleRange, maxRenderCount]);

  const timeline = useMemo(() => {
    const length = chartData.length;
    return {
      startIndex: 0,
      endIndex: length > 10 ? Math.floor(length / 10) : Math.max(0, length - 1)
    };
  }, [chartData.length]);

  const columns: ColumnItem[] = useMemo(() => [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 80,
      align: 'center',
      render: (_, record) => {
        const time = new Date(record.timestamp * 1000) + '';
        return <p>{convertToLocalizedTime(time, 'YYYY-MM-DD HH:mm:ss')}</p>;
      },
    },
    {
      title: '值',
      dataIndex: 'value',
      key: 'value',
      align: 'center',
      width: 30,
      render: (_, record) => {
        const value = Number(record.value || 0).toFixed(2);
        return <p>{value}</p>
      },
    }
  ], [convertToLocalizedTime]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (rangeChangeTimeoutRef.current) {
        clearTimeout(rangeChangeTimeoutRef.current);
      }
    };
  }, []);

  // 数据加载后的初始化逻辑
  const initializeDataState = useCallback((data: ChartDataItem[]) => {
    setAllData(data);
    setPredictData([]);
    setIsLargeDataset(data.length > maxRenderCount);
    
    const initialRange = [0, data.length > maxRenderCount ? 10 : 100];
    setVisibleRange(initialRange);
    setTempVisibleRange(initialRange);
    tempVisibleRangeRef.current = initialRange;
  }, [maxRenderCount]);

  // 初始化配置数据
  const initializeCapability = useCallback(async () => {
    if (isInitialized) return;

    const id = searchParams.get('id') || '';
    if (!id) return;

    try {
      const [capabilityData, sampleList] = await Promise.all([
        getCapabilityDetail(id),
        getSampleFileOfCapability(id)
      ]);

      const _data = {
        url: capabilityData?.url || '',
        ...capabilityData.config
      };


      const options = sampleList.filter((item: any) => item?.is_active).map((item: any) => ({
        label: item?.name,
        value: item?.id,
      }));

      setSampleOptions(options);
      setCapabilityData(_data);
      setIsInitialized(true);

    } catch (e) {
      console.error('获取配置数据失败:', e);
    }
  }, [isInitialized, getCapabilityDetail, getSampleFileOfCapability]);

  useEffect(() => {
    setIsInitialized(false);
    initializeCapability();
  }, [searchParams.get('id')]);

  // 样本选择处理
  const handleSampleSelect = async (value: number) => {
    if (!value) {
      setSelectId(null);
      setAllData([]);
      setPredictData([]);
      setIsLargeDataset(false);
      setVisibleRange([0, 100]);
      setTempVisibleRange([0, 100]);
      tempVisibleRangeRef.current = [0, 100];
      return;
    }

    setChartLoading(true);
    try {
      setSelectId(value);
      const data = await getSampleFileDetail(value as number);
      const trainData = data?.train_data || [];

      initializeDataState(trainData);
      setCurrentFileId(null);
    } catch (e) {
      console.error('获取样本文件失败:', e);
      message.error('获取样本文件失败');
    } finally {
      setChartLoading(false);
    }
  };

  // 文件上传处理
  const handleFileUpload: UploadProps['onChange'] = useCallback(async ({ fileList }: { fileList: any }) => {
    if (!fileList.length) {
      setCurrentFileId(null);
      setAllData([]);
      setPredictData([]);
      setIsLargeDataset(false);
      setVisibleRange([0, 100]);
      setTempVisibleRange([0, 100]);
      tempVisibleRangeRef.current = [0, 100];
      return;
    }

    const file = fileList[0];
    const fileId = file?.uid;

    if (currentFileId === fileId) return;

    setCurrentFileId(fileId);
    setChartLoading(true);
    setSelectId(null);

    try {
      const text = await file?.originFileObj?.text();
      const data = await new Promise<any[]>((resolve, reject) => {
        setTimeout(() => {
          try {
            resolve(handleFileRead(text));
          } catch (error) {
            reject(error);
          }
        }, 100);
      });

      initializeDataState(data);

      if (data.length > maxRenderCount) {
        const initialPercent = Math.min(20, (maxRenderCount / data.length) * 100);
        message.info(`文件较大（${data.length.toLocaleString()} 条数据），当前显示前 ${initialPercent.toFixed(1)}%，可通过底部滑块查看更多数据`);
      } else {
        message.success(`文件上传成功，共 ${data.length.toLocaleString()} 条数据`);
      }

    } catch (e) {
      console.error('文件处理失败:', e);
      message.error('文件处理失败，请检查文件格式');
    } finally {
      setChartLoading(false);
    }
  }, [currentFileId, maxRenderCount, initializeDataState]);

  const props: UploadProps = {
    name: 'file',
    multiple: false,
    maxCount: 1,
    showUploadList: false,
    onChange: handleFileUpload,
    beforeUpload: (file) => {
      const isCSV = file.type === "text/csv" || file.name.endsWith('.csv');
      if (!isCSV) {
        message.warning(t(`playground-common.uploadError`));
      }
      return isCSV;
    },
    accept: '.csv'
  };

  // 格式化数据为API所需格式
  const formatDataForAPI = useCallback((data: ChartDataItem[]) => {
    return data.map(item => ({
      timestamp: item.timestamp,  // 直接使用Unix时间戳（秒级）
      value: item.value
    }));
  }, []);

  // 执行预测
  const executePrediction = useCallback(async (serving: any, stepsValue: number, dataToSubmit?: ChartDataItem[]) => {
    const dataSource = dataToSubmit || allDataRef.current;

    if (!dataSource || dataSource.length === 0) {
      return message.error(t(`playground-common.uploadMsg`));
    }

    if (chartLoading) return;

    setChartLoading(true);
    try {
      const submitData = formatDataForAPI(dataSource);
      const params = {
        url: capabilityData.url,
        data: submitData,
        steps: stepsValue
      };

      const result = await timeseriesPredictReason(serving.serving_id, params);
      console.log(result);
      setPredictData(result.prediction || []);
    } catch (e) { 
      console.error('预测失败:', e);
      message.error(t(`common.error`));
    } finally {
      setChartLoading(false);
    }
  }, [timeseriesPredictReason, t, chartLoading, formatDataForAPI, capabilityData]);

  // 显示预测参数设置弹窗
  const showPredictionModal = useCallback((serving = capabilityData) => {
    if (!serving) {
      message.error('服务配置未加载');
      return;
    }

    if (!allData || allData.length === 0) {
      message.error(t(`playground-common.uploadMsg`));
      return;
    }

    setModalVisible(true);
  }, [capabilityData, allData, t]);

  // 弹窗确认并执行预测
  const handleModalConfirm = useCallback(async () => {
    if (!steps || steps <= 0) {
      message.error('请输入有效的预测步数');
      return;
    }

    setModalVisible(false);
    await executePrediction(capabilityData, steps);
  }, [steps, capabilityData, executePrediction]);

  // 弹窗取消处理函数
  const handleModalCancel = useCallback(() => {
    setModalVisible(false);
  }, []);

  //  使用 ref 避免依赖 allData
  const applyRangeChange = useCallback((newRange: number[]) => {
    console.log('应用范围变化:', newRange);
    setIsRangeChanging(true);

    setTimeout(() => {
      setVisibleRange(newRange);
      setTempVisibleRange(newRange); //  同步更新临时范围
      tempVisibleRangeRef.current = newRange;
      setIsRangeChanging(false);

      const totalCount = allDataRef.current.length;
      const startIndex = Math.floor((newRange[0] / 100) * totalCount);
      const endIndex = Math.min(Math.ceil((newRange[1] / 100) * totalCount), totalCount);
      const displayCount = Math.min(endIndex - startIndex, maxRenderCount);

      message.success(`数据范围已更新，当前显示 ${displayCount.toLocaleString()} 条数据`);
    }, 300);
  }, [maxRenderCount]);

  // 优化滑块变化处理，减少状态更新频率
  const handleRangeChange = useCallback((value: number[]) => {
    console.log('滑块变化:', value);

    // 更新 ref，但不立即更新状态
    tempVisibleRangeRef.current = value;

    // 使用防抖更新显示状态，减少更新频率
    if (rangeChangeTimeoutRef.current) {
      clearTimeout(rangeChangeTimeoutRef.current);
    }

    // 立即更新显示状态（用于滑块显示）
    setTempVisibleRange([...value]);

    // 如果还没有开始拖动，标记为拖动状态
    if (!isDraggingRef.current) {
      isDraggingRef.current = true;
    }

    rangeChangeTimeoutRef.current = setTimeout(() => {
      isDraggingRef.current = false;
      applyRangeChange(tempVisibleRangeRef.current);
    }, 500);
  }, [applyRangeChange]);

  const handleQuickNav = useCallback((type: 'start' | 'end' | 'anomaly') => {
    let newRange: number[] = [0, 100];

    if (type === 'start') {
      newRange = [0, Math.min(20, 100)];
    } else if (type === 'end') {
      newRange = [Math.max(80, 0), 100];
    } else if (type === 'anomaly') {
      const firstAnomalyIndex = allDataRef.current.findIndex(item => item.label === 1);
      if (firstAnomalyIndex !== -1) {
        const percent = (firstAnomalyIndex / allDataRef.current.length) * 100;
        const start = Math.max(0, percent - 10);
        const end = Math.min(100, percent + 10);
        newRange = [start, end];
      } else {
        message.info('未找到异常数据点');
        return;
      }
    }

    if (rangeChangeTimeoutRef.current) {
      clearTimeout(rangeChangeTimeoutRef.current);
    }
    isDraggingRef.current = false;

    setTempVisibleRange(newRange);
    tempVisibleRangeRef.current = newRange;
    applyRangeChange(newRange);
  }, [applyRangeChange]);

  //  优化时间信息计算，减少依赖
  const rangeTimeInfo = useMemo(() => {
    if (!allDataRef.current.length || !tempVisibleRange) return null;

    const totalCount = allDataRef.current.length;
    const startIndex = Math.floor((tempVisibleRange[0] / 100) * totalCount);
    const endIndex = Math.min(Math.ceil((tempVisibleRange[1] / 100) * totalCount), totalCount);

    const startTimestamp = allDataRef.current[startIndex]?.timestamp;
    const endTimestamp = allDataRef.current[Math.max(0, endIndex - 1)]?.timestamp;

    if (!startTimestamp || !endTimestamp) return null;

    const startDate = new Date(startTimestamp * 1000);
    const endDate = new Date(endTimestamp * 1000);

    return {
      start: startDate.toLocaleString(),
      end: endDate.toLocaleString(),
      count: endIndex - startIndex
    };
  }, [tempVisibleRange]);

  const renderBanner = useMemo(() => {
    const name = searchParams.get('name') || '异常检测';
    const description = searchParams.get('description');
    return (
      <>
        <div className="banner-title text-5xl font-bold pt-5">
          {name}
        </div>
        <div className="banner-info mt-8 max-w-[500px] text-[var(--color-text-3)]">
          {description || '基于机器学习的智能异常检测服务，能够自动识别时序数据中的异常模式和突变点。支持CSV文件上传，提供实时数据分析和可视化结果，帮助用户快速发现数据中的异常情况。广泛应用于系统监控、质量检测、金融风控、工业设备监控等场景。'}
        </div>
      </>
    )
  }, [searchParams]);

  const infoText = {
    applicationScenario: [
      {
        title: '资源状态监控',
        content: '通过持续采集CPU、内存、磁盘等关键指标时序数据，构建动态基线模型，可精准识别资源使用率异常波动、内存泄漏等潜在风险。',
        img: `bg-[url(/app/anomaly_detection_1.png)]`
      },
      {
        title: '网络流量分析',
        content: '基于流量时序特征建模，检测DDoS攻击、端口扫描等异常流量模式，支持实时阻断与安全告警',
        img: `bg-[url(/app/anomaly_detection_2.png)]`
      },
      {
        title: '数据库性能诊断',
        content: '分析SQL执行耗时、事务日志等时序数据，定位慢查询、死锁等性能瓶颈问题。',
        img: `bg-[url(/app/anomaly_detection_3.png)]`
      },
      {
        title: '容器健康管理',
        content: '监控容器化环境中Pod的资源使用、重启频率等时序指标，实现服务异常的早期预警。',
        img: `bg-[url(/app/anomaly_detection_4.png)]`
      },
    ]
  };

  const renderElement = () => {
    return infoText.applicationScenario.map((item: any) => (
      <div key={item.title} className="content overflow-auto pb-[20px] border-b mt-4">
        <div className={`float-right w-[250px] h-[160px] ${item.img} bg-cover`}></div>
        <div className="content-info mr-[300px]">
          <div className="content-title text-lg font-bold">{item.title}</div>
          <div className="content-intro mt-3 text-sm text-[var(--color-text-3)]">{item.content}</div>
        </div>
      </div>
    ))
  };

  return (
    <div className="relative">
      {/* 预测步数输入弹窗 */}
      <Modal
        title="设置预测参数"
        open={modalVisible}
        onOk={handleModalConfirm}
        onCancel={handleModalCancel}
        okText="开始检测"
        cancelText="取消"
        width={400}
      >
        <div className="py-4">
          <div className="mb-2 text-sm">请输入预测未来的步数：</div>
          <InputNumber
            min={1}
            max={1000}
            value={steps}
            onChange={(value) => setSteps(value || 10)}
            placeholder="请输入步数"
            className="w-full"
            size="large"
          />
          <div className="mt-2 text-xs text-[var(--color-text-3)]">
            步数表示预测未来多少个时间点的数据，建议设置为 1-100
          </div>
        </div>
      </Modal>

      <div className="banner-content w-full h-[460px] pr-[400px] pl-[200px] pt-[80px] bg-[url(/app/pg_banner_1.png)] bg-cover">
        {renderBanner}
      </div>

      <div className="model-experience bg-[#F8FCFF] py-4">
        <div className="header text-3xl text-center">{t(`playground-common.functionExper`)}</div>
        <div className="content flex flex-col">
          <div className="file-input w-[90%] mx-auto">
            <div className={`link-search mt-8 flex justify-center `}>
              <div className="flex w-full justify-center items-center">
                <span className="align-middle text-sm mr-4">使用系统样本文件: </span>
                <Select
                  className={`w-[70%] max-w-[500px] text-sm ${cssStyle.customSelect}`}
                  size="large"
                  allowClear
                  options={sampleOptions}
                  placeholder={t(`playground-common.selectSampleMsg`)}
                  onChange={handleSampleSelect}
                  value={selectId}
                />
                <span className="mx-4 text-base pt-1">{t(`playground-common.or`)}</span>
                <Upload {...props}>
                  <Button size="large" className="rounded-none text-sm">
                    {t(`playground-common.localUpload`)}
                  </Button>
                </Upload>
                <Button
                  size="large"
                  className="rounded-none ml-4 text-sm"
                  type="primary"
                  loading={chartLoading}
                  onClick={() => showPredictionModal(capabilityData)}
                >
                  {t(`playground-common.clickTest`)}
                </Button>
              </div>
            </div>

            {allData.length > 0 && (
              <div className="text-center mt-4 text-sm text-[var(--color-text-3)]">
                <span className="mr-4">
                  总数据量: {allData.length.toLocaleString()} 条
                </span>
                <span className="mr-4">
                  当前显示: {chartData.length.toLocaleString()} 条
                </span>
                {isRangeChanging && (
                  <span className="ml-4 text-blue-500">
                    正在更新数据范围...
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="content w-[80%] mx-auto h-[604px] mt-6">
            <div className="flex h-full overflow-auto">
              <Spin spinning={chartLoading || isRangeChanging} wrapperClassName="w-[70%] flex-1 h-full" className="h-full">
                <div className="iframe w-full bg-[var(--color-bg-1)] border p-6" style={{ height: 604 }}>
                  <LineChart
                    data={chartData}
                    timeline={timeline}
                    allowSelect={false}
                  />
                </div>
              </Spin>
              <div className="params w-[30%] max-w-[360px] bg-[var(--color-bg-4)]">
                <header className="pl-2">
                  <span className="inline-block h-[60px] text-[var(--color-text-2)] content-center ml-10 text-sm">
                    预测结果 ({predictData.length})
                  </span>
                </header>
                <div className="[&_.ant-table]:!h-[543px]">
                  <CustomTable
                    virtual
                    className="h-[543px]"
                    scroll={{ y: 480 }}
                    rowKey='timestamp'
                    columns={columns}
                    sticky={{ offsetHeader: 0 }}
                    dataSource={predictData}
                    pagination={false}
                  />
                </div>
              </div>
            </div>
          </div>

          {isLargeDataset && (
            <div className="data-navigator w-[80%] mx-auto mt-4 p-4 bg-white border rounded-lg shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-sm font-medium text-[var(--color-text-1)]">
                  数据导航器 ({allData.length.toLocaleString()} 条数据)
                  {isRangeChanging && (
                    <span className="ml-2 text-xs text-blue-500">
                      <Spin size="small" className="mr-1" />
                      正在加载...
                    </span>
                  )}
                </h4>
                <div className="flex gap-2">
                  <Button
                    size="small"
                    onClick={() => handleQuickNav('start')}
                    disabled={isRangeChanging}
                  >
                    开头
                  </Button>
                  <Button
                    size="small"
                    onClick={() => handleQuickNav('anomaly')}
                    disabled={isRangeChanging}
                  >
                    定位异常
                  </Button>
                  <Button
                    size="small"
                    onClick={() => handleQuickNav('end')}
                    disabled={isRangeChanging}
                  >
                    结尾
                  </Button>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <span className="text-xs text-[var(--color-text-3)] min-w-[60px]">
                  {tempVisibleRange[0].toFixed(1)}%
                </span>
                <div className="flex-1">
                  <Slider
                    range
                    min={0}
                    max={100}
                    step={0.1}
                    value={tempVisibleRange}
                    onChange={handleRangeChange}
                    disabled={isRangeChanging}
                    tooltip={{
                      formatter: (value) => {
                        if (!rangeTimeInfo) return `${value!.toFixed(1)}%`;

                        const isStart = value === tempVisibleRange[0];
                        const time = isStart ? rangeTimeInfo.start : rangeTimeInfo.end;
                        return (
                          <div className="text-center">
                            <div>{value!.toFixed(1)}%</div>
                            <div className="text-xs">{time}</div>
                          </div>
                        );
                      }
                    }}
                  />
                </div>
                <span className="text-xs text-[var(--color-text-3)] min-w-[60px]">
                  {tempVisibleRange[1].toFixed(1)}%
                </span>
              </div>

              <div className="text-xs text-[var(--color-text-3)] mt-2 text-center">
                {isRangeChanging ? (
                  <span className="text-blue-500">正在更新数据范围，请稍候...</span>
                ) : (
                  <>
                    拖动滑块查看不同时间段的数据，当前显示 {chartData.length.toLocaleString()} 条数据
                    {rangeTimeInfo && (
                      <div className="mt-1">
                        时间范围: {rangeTimeInfo.start} 至 {rangeTimeInfo.end}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="usage-scenarios pt-[80px] bg-[#F8FCFF]">
        <div className="header text-center text-3xl">
          {t(`playground-common.useScenario`)}
        </div>
        <div className="mt-8 w-[80%] mx-auto">
          {renderElement()}
        </div>
      </div>
    </div>
  )
};

export default TimeseriesPredict;