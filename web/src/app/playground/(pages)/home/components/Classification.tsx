import { Button, Upload, message, Select, Typography } from "antd";
import type { UploadProps } from 'antd';
import {
  handleClassFile,
  // formatProbability 
} from "@/app/playground/utils/common";
import { useCallback, useState, useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "@/utils/i18n";
// import LineChart from "@/app/playground/components/charts/lineChart";
// import CustomTable from "@/components/custom-table";
// import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import usePlayroundApi from "@/app/playground/api";
import cssStyle from './index.module.scss'
import {
  // ColumnItem,
  Option
} from "@/types";
const { Paragraph } = Typography

const Classification = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  // const { convertToLocalizedTime } = useLocalizedTime();
  const {
    classificationReason,
    getCapabilityDetail,
    getSampleFileOfCapability,
    getSampleFileDetail
  } = usePlayroundApi();
  const [currentFileId, setCurrentFileId] = useState<string | null>(null);
  const [selectId, setSelectId] = useState<number | null>(null);
  const [servingData, setServingData] = useState<any>(null);
  const [sampleOptions, setSampleOptions] = useState<Option[]>([]);
  const [chartLoading, setChartLoading] = useState<boolean>(false);
  const [headers, setHeaders] = useState<string[]>([]);
  const [allData, setAllData] = useState<any[]>([]);
  const [resultData, setResultData] = useState<any>({});
  const [maxRenderCount] = useState(2000);


  // 添加初始化标记，防止重复调用
  const [isInitialized, setIsInitialized] = useState(false);

  const getConfigData = useCallback(async () => {
    if (isInitialized) return;

    const id = searchParams.get('id') || '';
    if (!id) return;

    try {
      const [capabilityData, sampleList] = await Promise.all([
        getCapabilityDetail(id),
        getSampleFileOfCapability(id)
      ]);

      const options = sampleList.filter((item: any) => item?.is_active).map((item: any) => ({
        label: item?.name,
        value: item?.id,
      }));

      setSampleOptions(options);
      setServingData(capabilityData?.config);
      setIsInitialized(true);

    } catch (e) {
      console.error('获取配置数据失败:', e);
    }
  }, [isInitialized, getCapabilityDetail, getSampleFileOfCapability]);

  useEffect(() => {
    setIsInitialized(false);
    getConfigData();
  }, [searchParams.get('id')]);

  // 样本选择处理
  const onSelectChange = async (value: number) => {
    if (!value) {
      setSelectId(null);
      setAllData([]);
      return;
    }

    setChartLoading(true);
    try {
      setSelectId(value);
      const data = await getSampleFileDetail(value as number);
      const trainData = data?.train_data || [];
      const _trainData = trainData.map((item: any) => {
        if (Object.hasOwn(item, 'label')) delete item.label;
        return item;
      });
      console.log(_trainData);
      setAllData(_trainData);
      setCurrentFileId(null);
    } catch (e) {
      console.log(e);
      message.error('获取样本文件失败');
    } finally {
      setChartLoading(false);
    }
  };

  // 文件上传处理
  const onUploadChange: UploadProps['onChange'] = useCallback(async ({ fileList }: { fileList: any }) => {
    if (!fileList.length) {
      setCurrentFileId(null);
      setAllData([]);
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
      const processData = (text: string): Promise<{
        train_data: any[],
        headers: string[]
      }> => {
        return new Promise((resolve, reject) => {
          setTimeout(() => {
            try {
              const data = handleClassFile(text);
              resolve(data);
            } catch (error) {
              reject(error);
            }
          }, 100);
        });
      };
      const { train_data, headers } = await processData(text);
      const _train_data = train_data.map(item => {
        if (Object.hasOwn(item, 'label')) delete item.label;
        return item
      });
      console.log(_train_data)
      setAllData(_train_data);
      setHeaders(headers);
    } catch (e) {
      console.error('文件处理失败:', e);
      message.error('文件处理失败，请检查文件格式');
    } finally {
      setChartLoading(false);
    }
  }, [currentFileId, maxRenderCount]);

  const props: UploadProps = {
    name: 'file',
    multiple: false,
    maxCount: 1,
    showUploadList: false,
    onChange: onUploadChange,
    beforeUpload: (file) => {
      const isCSV = file.type === "text/csv" || file.name.endsWith('.csv');
      if (!isCSV) {
        message.warning(t(`playground-common.uploadError`));
      }
      return isCSV;
    },
    accept: '.csv'
  };

  // 内部提交函数
  const handleSubmitInternal = useCallback(async (serving: any, dataToSubmit?: any[]) => {
    console.log(headers);
    const dataSource = dataToSubmit;

    if (!dataSource || dataSource.length === 0) {
      return message.error(t(`playground-common.uploadMsg`));
    }

    if (chartLoading) return;

    setChartLoading(true);
    try {
      const params = {
        serving_id: serving.serving_id,
        model_name: `Classification_RandomForest_${serving.serving_id}`,
        algorithm: "RandomForest",
        model_version: serving.model_version,
        data: dataSource,
      };
      const result = await classificationReason(params);
      console.log(result);
      const { success, model_name, model_version, predictions } = result
      setResultData({
        success,
        model_name,
        model_version,
        predictions: {
          predicted_label: `[${predictions.predicted_label?.join(',')}]`,
          prob_0: `[${predictions.prob_0.join(',')}]`,
          prob_1: `[${predictions.prob_1.join(',')}]`
        }
      });
      // const anomalyCount = labelData.filter((item: any) => item.label === 1).length;
      message.success(`检测完成`);
    } catch (e) {
      console.error('检测失败:', e);
      message.error(t(`common.error`));
    } finally {
      setChartLoading(false);
    }
  }, [classificationReason, t, maxRenderCount, chartLoading]);

  // 用户点击提交的处理函数
  const handleSubmit = useCallback(async (serving = servingData) => {
    if (!serving) {
      message.error('服务配置未加载');
      return;
    }
    await handleSubmitInternal(serving, allData);
  }, [servingData, handleSubmitInternal, allData]);


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
      <div className="banner-content w-full h-[460px] pr-[400px] pl-[200px] pt-[80px] bg-[url(/app/pg_banner_1.png)] bg-cover">
        {renderBanner}
      </div>

      <div className="model-experience bg-[#F8FCFF] py-4">
        <div className="header text-3xl text-center">{t(`playground-common.functionExper`)}</div>
        <div className="content flex flex-col">
          <div className="file-input w-[90%] mx-auto">
            <div className={`link-search mt-8 flex justify-center flex-col`}>
              <div className="flex w-full justify-center items-center">
                <span className="align-middle text-sm mr-4">使用系统样本文件: </span>
                <Select
                  className={`w-[70%] max-w-[500px] text-sm ${cssStyle.customSelect}`}
                  size="large"
                  allowClear
                  options={sampleOptions}
                  placeholder={t(`playground-common.selectSampleMsg`)}
                  onChange={onSelectChange}
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
                  onClick={() => handleSubmit(servingData)}
                >
                  {t(`playground-common.clickTest`)}
                </Button>
              </div>
              <div className="flex w-full justify-center items-center">
                <Paragraph className="">
                  <pre className="border-none">
                    {
                      JSON.stringify(resultData, null, 2)
                    }
                  </pre>
                </Paragraph>
              </div>
            </div>

          </div>


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

export default Classification;