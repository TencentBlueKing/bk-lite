'use client'
import React, { useMemo } from 'react';
import { useSearchParams, useParams, useRouter } from 'next/navigation';
import AnomalyDetail from '@/app/mlops/components/algorithm-detail/anomaly/AnomalyDetail';
import LogDetail from '@/app/mlops/components/algorithm-detail/log/LogDetail';
import TimeSeriesPredict from '@/app/mlops/components/algorithm-detail/timeseries/TimeSeriesPredict';
import ClassificationDetail from '@/app/mlops/components/algorithm-detail/classification/classificationDetail';
import ImageClassificationDetail from '@/app/mlops/components/algorithm-detail/image-classification/imageClassificationDetail';
import ObjectDetectionDetail from '@/app/mlops/components/algorithm-detail/object-detection/objectDetection';
import { DatasetType } from '@/app/mlops/types';
import SubLayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';

const DatasetDetailPage = () => {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();

  const algorithmType = params.algorithmType as DatasetType;

  const { folder_name, description } = useMemo(() => ({
    folder_name: searchParams.get('folder_name') || '',
    description: searchParams.get('description') || ''
  }), [searchParams]);

  const renderPage: Record<string, React.ReactNode> = useMemo(() => {
    return {
      [DatasetType.ANOMALY_DETECTION]: <AnomalyDetail />,
      [DatasetType.LOG_CLUSTERING]: <LogDetail />,
      [DatasetType.TIMESERIES_PREDICT]: <TimeSeriesPredict />,
      [DatasetType.CLASSIFICATION]: <ClassificationDetail />,
      [DatasetType.IMAGE_CLASSIFICATION]: <ImageClassificationDetail />,
      [DatasetType.OBJECT_DETECTION]: <ObjectDetectionDetail />
    };
  }, []);

  const topSection = useMemo(() => {
    return <TopSection title={folder_name} content={description} />;
  }, [folder_name, description]);

  const backToList = () => router.push(`/mlops/${algorithmType}/datasets`);

  return (
    <SubLayout
      showBackButton
      topSection={topSection}
      onBackButtonClick={backToList}
      showSideMenu={false}
      intro={<div className="text-base font-medium">{folder_name}</div>}
    >
      {renderPage[algorithmType]}
    </SubLayout>
  )
};

export default DatasetDetailPage;
