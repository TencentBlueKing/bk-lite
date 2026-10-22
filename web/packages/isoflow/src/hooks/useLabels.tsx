import React, { createContext, useContext, useMemo } from 'react';
import { DEFAULT_LABELS } from 'src/config';
import type { IsoflowLabels } from 'src/types';

const LabelsContext = createContext<IsoflowLabels>(DEFAULT_LABELS);

export const LabelsProvider = ({
  labels,
  children
}: {
  labels?: Partial<IsoflowLabels>;
  children: React.ReactNode;
}) => {
  const value = useMemo(() => {
    return { ...DEFAULT_LABELS, ...labels };
  }, [labels]);

  return (
    <LabelsContext.Provider value={value}>{children}</LabelsContext.Provider>
  );
};

export const useLabels = () => {
  return useContext(LabelsContext);
};
