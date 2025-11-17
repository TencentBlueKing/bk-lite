'use client';
import React from 'react';
import MarkdownRenderer from '@/components/markdown';
import { useSearchParams } from 'next/navigation';

const Output: React.FC = () => {
  const searchParams = useSearchParams();
  const collectType = searchParams.get('name') || '';
  const collector = searchParams.get('collector') || '';
  const fileName = collectType + collector;

  return (
    <div className="p-4 overflow-y-auto h-[calc(100vh-270px)]">
      <MarkdownRenderer filePath="outputs" fileName={fileName} />
    </div>
  );
};

export default Output;
