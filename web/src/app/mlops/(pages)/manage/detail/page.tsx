'use client'
import React, { useMemo } from 'react';
import {
  useSearchParams,
} from 'next/navigation';
// import { useTranslation } from '@/utils/i18n';
import { useRouter } from 'next/navigation';
import AnomalyDetail from './components/anomaly/AnomalyDetail';
import LogDetail from './components/log/LogDetail';
import TimeSeriesPredict from './components/timeseries/TimeSeriesPredict';
import ClassificationDetail from './components/classification/classificationDetail';
import ImageClassificationDetail from './components/image-classification/imageClassificationDetail';
import ObjectDetectionDetail from './components/object-detection/objectDetection';
import Sublayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';


const Detail = () => {
  
  // const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    // folder_id,
    folder_name,
    description,
    activeTap,
    // menu,
  } = useMemo(() => ({
    folder_id: searchParams.get('folder_id') || '',
    folder_name: searchParams.get('folder_name') || '',
    description: searchParams.get('description') || '',
    activeTap: searchParams.get('activeTap') || '',
    menu: searchParams.get('menu') || '',
  }), [searchParams]);


  // const datasetInfo = `folder_id=${folder_id}&folder_name=${folder_name}&description=${description}&activeTap=${activeTap}`;

  const renderPage: Record<string, React.ReactNode> = useMemo(() => {
    return {
      anomaly_detection: <AnomalyDetail />,
      log_clustering: <LogDetail />,
      timeseries_predict: <TimeSeriesPredict />,
      classification: <ClassificationDetail />,
      image_classification: <ImageClassificationDetail />,
      object_detection: <ObjectDetectionDetail />
    };
  }, [activeTap]);

  const topSection = useMemo(() => {
    return <TopSection title={folder_name} content={description} />;
  }, [folder_name, description]);

  const backToList = () => router.push(`/mlops/manage/list`);

  return (
    <>
      <div className='w-full'>
        <Sublayout
          topSection={topSection}
          showSideMenu={false}
          activeKeyword
          keywordName='menu'
          customMenuItems={[]}
          onBackButtonClick={backToList}
        >
          <div className='w-full h-full relative'>
            {renderPage[activeTap]}
          </div>
        </Sublayout>
      </div>
    </>
  )
};

export default Detail;