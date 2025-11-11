'use client';

import React from 'react';
import { OpsAnalysisProvider } from '../../context/common';

interface ViewLayoutProps {
  children: React.ReactNode;
}

const ViewLayout: React.FC<ViewLayoutProps> = ({ children }) => {
  return <OpsAnalysisProvider>{children}</OpsAnalysisProvider>;
};

export default ViewLayout;
