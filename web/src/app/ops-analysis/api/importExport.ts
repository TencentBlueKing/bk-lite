import useApiClient from '@/utils/request';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import { canvasImportUpdatePath } from '@/app/ops-analysis/utils/canvasImportUpdate';

export type ObjectType =
  | 'dashboard'
  | 'topology'
  | 'architecture'
  | 'screen'
  | 'report'
  | 'networkTopology'
  | 'datasource'
  | 'namespace';
export type ConflictAction = 'skip' | 'overwrite' | 'rename';

export interface ExportRequest {
  object_type: ObjectType;
  object_ids: number[];
}

export interface ExportResponse {
  yaml_content: string;
  summary: {
    dashboards?: number;
    topologies?: number;
    architectures?: number;
    screens?: number;
    reports?: number;
    datasources?: number;
    namespaces?: number;
  };
}

export interface PrecheckRequest {
  yaml_content: string;
  target_directory_id?: number | null;
}

export interface ConflictItem {
  object_key: string;
  object_type: ObjectType;
  reason: string;
  suggested_actions: ConflictAction[];
}

export interface WarningItem {
  code: string;
  message: string;
  object_key?: string;
  field?: string;
}

export interface ErrorItem {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ObjectCounts {
  total: number;
  by_type: Record<ObjectType, number>;
}

export interface PrecheckResponse {
  valid: boolean;
  counts: ObjectCounts;
  conflicts: ConflictItem[];
  warnings: WarningItem[];
  errors: ErrorItem[];
}

export interface ConflictDecision {
  object_key: string;
  action: ConflictAction;
}

export interface SecretSupplement {
  object_key: string;
  field: string;
  value: string;
}

export interface ImportSubmitRequest {
  yaml_content: string;
  target_directory_id?: number | null;
  conflict_decisions?: ConflictDecision[];
  secret_supplements?: SecretSupplement[];
}

export interface ImportResultItem {
  object_key: string;
  object_type: ObjectType;
  status: 'success' | 'failed' | 'skipped' | 'overwritten';
  message: string;
  new_id: number | null;
}

export interface ImportSummary {
  total: number;
  success: number;
  failed: number;
  skipped: number;
  overwritten: number;
}

export interface ImportSubmitResponse {
  success: boolean;
  results: ImportResultItem[];
  summary: ImportSummary;
}

export interface ImportUpdateRequest {
  object_type: CanvasType;
  object_id: number;
  yaml_content: string;
}

export interface ImportUpdateResponse {
  canvas_id: number;
  name: string;
  desc: string;
  object_type: CanvasType;
  summary: ImportSummary;
}

export const useImportExportApi = () => {
  const { post } = useApiClient();

  const exportObjects = async (params: ExportRequest): Promise<ExportResponse> => {
    return post('/operation_analysis/api/import_export/export/', params);
  };

  const importPrecheck = async (params: PrecheckRequest): Promise<PrecheckResponse> => {
    return post('/operation_analysis/api/import_export/import/precheck/', params);
  };

  const importSubmit = async (params: ImportSubmitRequest): Promise<ImportSubmitResponse> => {
    return post('/operation_analysis/api/import_export/import/submit/', params);
  };

  const importUpdateCanvas = async (params: ImportUpdateRequest): Promise<ImportUpdateResponse> => {
    return post(canvasImportUpdatePath(params.object_type, params.object_id), {
      yaml_content: params.yaml_content,
    });
  };

  const downloadYaml = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'application/x-yaml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.yaml`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return {
    exportObjects,
    importPrecheck,
    importSubmit,
    importUpdateCanvas,
    downloadYaml,
  };
};
