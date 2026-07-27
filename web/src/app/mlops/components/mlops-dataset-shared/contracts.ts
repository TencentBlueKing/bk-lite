export interface MlopsDatasetModalConfig {
  type: string;
  title?: string;
  form?: MlopsDatasetModalFormData;
  key?: string;
  ids?: string[];
  selectedsystem?: string;
  nodes?: string[];
}

export interface MlopsDatasetModalRef {
  showModal: (config: MlopsDatasetModalConfig) => void;
}

export interface MlopsDatasetModalFormData {
  id?: number | string;
  dataset_id?: number | string;
  name?: string;
  anomaly?: number;
  [key: string]: any;
}
