'use client';

import React from 'react';
import { useParams } from 'next/navigation';
import { notFound } from 'next/navigation';
import { isValidAlgorithmType } from '@/app/mlops/types';

interface AlgorithmLayoutProps {
  children: React.ReactNode;
}

export default function AlgorithmLayout({ children }: AlgorithmLayoutProps) {
  const params = useParams();
  const algorithmType = params.algorithmType as string;

  // Validate algorithm type
  if (!isValidAlgorithmType(algorithmType)) {
    notFound();
  }

  return <>{children}</>;
}
