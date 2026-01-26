"use client";
import {
  useMemo,
  useEffect,
  useState,
} from "react";
import { useSearchParams } from 'next/navigation';
import useMlopsManageApi from "@/app/mlops/api/manage";
import Aside from "./aside";
import { AnomalyTrainData } from '@/app/mlops/types/manage';
import sideMenuStyle from './aside/index.module.scss';
import ChartContent from "./charContent";
import TableContent from "./tableContent";
import ImageContent from "./imageContent";
import dynamic from 'next/dynamic';
import { DatasetType } from "@/app/mlops/types";

const ObjectDetection = dynamic(() => import('./objectDetection'), {
  ssr: false,
  loading: () => <div>Loading...</div>
});

const AnnotationPage = () => {
  const searchParams = useSearchParams();
  const {
    getTrainDataByDataset,
  } = useMlopsManageApi();
  const [menuItems, setMenuItems] = useState<AnomalyTrainData[]>([]);
  const [loadingState, setLoadingState] = useState({
    loading: false,
    chartLoading: false,
    saveLoading: false,
  });
  // const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [isChange, setIsChange] = useState<boolean>(false);
  const [flag, setFlag] = useState<boolean>(true);
  const chartList = [DatasetType.ANOMALY_DETECTION, DatasetType.TIMESERIES_PREDICT];
  const tableList = [DatasetType.LOG_CLUSTERING, DatasetType.CLASSIFICATION];
  const imageList = [DatasetType.IMAGE_CLASSIFICATION];

  useEffect(() => {
    getMenuItems();
  }, [searchParams]);

  const {
    dataset,
    key
  } = useMemo(() => ({
    dataset: searchParams.get('folder_id') || '',
    key: searchParams.get('activeTap') || ''
  }), [searchParams])

  const getMenuItems = async () => {
    setLoadingState((prev) => ({ ...prev, loading: true }));
    try {
      if (dataset && key) {
        const data = await getTrainDataByDataset({ key: key as DatasetType, dataset: dataset });
        setMenuItems(data)
      }
    } catch (e) {
      console.log(e)
    } finally {
      setLoadingState((prev) => ({ ...prev, loading: false }));
    }
  };

  return (
    <div className={`flex w-full h-full text-sm ${sideMenuStyle.sideMenuLayout} grow`}>
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
            {chartList.includes(key as DatasetType) &&
              <ChartContent flag={flag} setFlag={setFlag} isChange={isChange} setIsChange={setIsChange} />
            }
            {tableList.includes(key as DatasetType) &&
              <TableContent />
            }
            {imageList.includes(key as DatasetType) &&
              <ImageContent />
            }
            {key === DatasetType.OBJECT_DETECTION && 
              <ObjectDetection isChange={isChange} setIsChange={setIsChange} />
            }
          </div>
        </section>
      </div>
    </div>
  )
};

export default AnnotationPage;