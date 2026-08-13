export type DataConnectionType = 'mysql' | 'postgresql' | 'rest_api';

export interface DataConnectionItem {
  id: number;
  name: string;
  connection_type: DataConnectionType;
  description?: string;
  groups: number[];
  is_active: boolean;
  config: Record<string, any>;
  reference_count?: number;
  endpoint_summary?: string;
  created_at?: string;
  updated_at?: string;
}

export interface DataConnectionOperateModalProps {
  open: boolean;
  currentRow?: DataConnectionItem | null;
  onClose: () => void;
  onSuccess?: () => void;
}
