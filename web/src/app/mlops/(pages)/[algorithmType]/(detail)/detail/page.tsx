'use client'
import React, { useMemo } from 'react';
import { useSearchParams, useParams, useRouter } from 'next/navigation';
import AlgorithmDetail from '@/app/mlops/components/algorithm-detail/AlgorithmDetail';
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
      <AlgorithmDetail datasetType={algorithmType} />
    </SubLayout>
  )
};

export default DatasetDetailPage;
