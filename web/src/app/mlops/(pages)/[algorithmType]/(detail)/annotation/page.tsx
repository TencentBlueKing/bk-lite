"use client";
import {
  useEffect,
  useState,
} from "react";
import { useSearchParams, useParams } from 'next/navigation';
import useMlopsManageApi from "@/app/mlops/api/manage";
import Aside from "@/app/mlops/components/annotation/aside";
import { AnomalyTrainData } from '@/app/mlops/types/manage';
import sideMenuStyle from '@/app/mlops/components/annotation/aside/index.module.scss';
import ChartContent from "@/app/mlops/components/annotation/charContent";
import TableContent from "@/app/mlops/components/annotation/tableContent";
import ImageContent from "@/app/mlops/components/annotation/imageContent";
import dynamic from 'next/dynamic';
import { DatasetType } from "@/app/mlops/types";

const ObjectDetection = dynamic(() => import('@/app/mlops/components/annotation/objectDetection'), {
  ssr: false,
  loading: () => <div>Loading...</div>
});

const AnnotationPage = () => {
  const params = useParams();
  const searchParams = useSearchParams();
  const algorithmType = params.algorithmType as DatasetType;

  // Get params from query
  const datasetId = searchParams.get('dataset_id') || '';

  const {
    getTrainDataByDataset,
  } = useMlopsManageApi();
  const [menuItems, setMenuItems] = useState<AnomalyTrainData[]>([]);
  const [loadingState, setLoadingState] = useState({
    loading: false,
    chartLoading: false,
    saveLoading: false,
  });
  const [isChange, setIsChange] = useState<boolean>(false);
  const [flag, setFlag] = useState<boolean>(true);
  const chartList = [DatasetType.ANOMALY_DETECTION, DatasetType.TIMESERIES_PREDICT];
  const tableList = [DatasetType.LOG_CLUSTERING, DatasetType.CLASSIFICATION];
  const imageList = [DatasetType.IMAGE_CLASSIFICATION];

  useEffect(() => {
    getMenuItems();
  }, [algorithmType, datasetId]);

  const getMenuItems = async () => {
    setLoadingState((prev) => ({ ...prev, loading: true }));
    try {
      if (datasetId && algorithmType) {
        const data = await getTrainDataByDataset({ key: algorithmType, dataset: datasetId });
        setMenuItems(data)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingState((prev) => ({ ...prev, loading: false }));
    }
  };


  return (
    <div className={`flex flex-1 text-sm ${sideMenuStyle.sideMenuLayout} grow overflow-hidden h-full`}>
      <div
        className="w-full flex grow flex-1 h-full"
        style={{
          transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          willChange: 'width',
          position: 'relative',
          height: '100%',
        }}
      >
        <Aside
          loading={loadingState.loading}
          menuItems={menuItems}
          isChange={isChange}
          onChange={(value: boolean) => setIsChange(value)}
          changeFlag={(value: boolean) => setFlag(value)}
        >
        </Aside>
        <section
          className="flex-1 flex flex-col overflow-hidden"
          style={{
            transition: 'flex 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            willChange: 'flex',
            height: '100%',
          }}
        >
          <div
            className={`p-3 flex-1 rounded-md overflow-auto ${sideMenuStyle.sectionContainer} ${sideMenuStyle.sectionContext}`}
            style={{
              transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              willChange: 'width',
              height: '100%',
            }}
          >
            {chartList.includes(algorithmType) &&
              <ChartContent flag={flag} setFlag={setFlag} isChange={isChange} setIsChange={setIsChange} />
            }
            {tableList.includes(algorithmType) &&
              <TableContent />
            }
            {imageList.includes(algorithmType) &&
              <ImageContent />
            }
            {algorithmType === DatasetType.OBJECT_DETECTION &&
              <ObjectDetection isChange={isChange} setIsChange={setIsChange} />
            }
          </div>
        </section>
      </div>
    </div>
  )
};

export default AnnotationPage;
