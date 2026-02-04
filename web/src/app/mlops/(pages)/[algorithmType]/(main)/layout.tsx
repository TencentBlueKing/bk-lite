'use client';

import React from 'react';
import { useParams  } from 'next/navigation';
import { notFound } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import TopSection from '@/components/top-section';
import SubLayout from '@/components/sub-layout';
import { isValidAlgorithmType, DatasetType, ALGORITHM_TYPE_CONFIG } from '@/app/mlops/types';

interface AlgorithmLayoutProps {
  children: React.ReactNode;
}

export default function AlgorithmLayout({ children }: AlgorithmLayoutProps) {
  const { t } = useTranslation();
  const params = useParams();
  const algorithmType = params.algorithmType as string;

  // Validate algorithm type
  if (!isValidAlgorithmType(algorithmType)) {
    notFound();
  }

  // Get algorithm display name
  const algorithmConfig = ALGORITHM_TYPE_CONFIG[algorithmType as DatasetType];
  const algorithmTitle = t(algorithmConfig.labelKey);

  const topSection = (
    <TopSection
      title={algorithmTitle}
      content={t('traintask.description')}
    />
  );


  const rightSection = (
    <div className="h-full overflow-auto">
      {children}
    </div>
  );

  return (
    <>
      <SubLayout
        topSection={topSection}
      >
        {rightSection}
      </SubLayout>
    </>
  );
}
