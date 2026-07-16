'use client';

import React from 'react';
import OpsAnalysisImportModal, {
  type OpsAnalysisImportModalProps,
} from '@/components/ops-analysis-import-modal';
import { useImportExportApi } from '@/app/ops-analysis/api/importExport';

type RuntimeProps = Omit<
  OpsAnalysisImportModalProps,
  'importPrecheck' | 'importSubmit'
>;

const OpsAnalysisImportModalRuntime: React.FC<RuntimeProps> = (props) => {
  const { importPrecheck, importSubmit } = useImportExportApi();

  return (
    <OpsAnalysisImportModal
      {...props}
      importPrecheck={importPrecheck}
      importSubmit={importSubmit}
    />
  );
};

export default OpsAnalysisImportModalRuntime;
