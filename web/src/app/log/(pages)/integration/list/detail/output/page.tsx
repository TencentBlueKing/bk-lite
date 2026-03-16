'use client';
import React from 'react';
import IntroRenderer from './introRenderer';
import { useSearchParams } from 'next/navigation';

const Output: React.FC = () => {
  const searchParams = useSearchParams();
  const collectType = searchParams.get('name') || '';
  const collector = searchParams.get('collector') || '';
  const fileName = collectType + collector;

  return (
    <div className="p-4 overflow-y-auto h-[calc(100vh-270px)]">
      <IntroRenderer filePath="introductions" fileName={fileName} />
    </div>
  );
};

export default Output;
