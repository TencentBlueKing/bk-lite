enum TrainingStatus {
  'not_stared',
  'in_progress',
  'completed',
  'failed'
}

interface AnomalyTrainData {
  id: number;
  tenant_id: number;
  dataset_id: number;
  name: string,
  storage_path: string,
  metadata: any;
  user_id: string;
  latest_status?: TrainingStatus;
}

interface AsideProps {
  // children: any,
  menuItems: AnomalyTrainData[],
  loading: boolean,
  isChange: boolean,
  onChange: (value: boolean) => void,
  changeFlag: (value: boolean) => void
}

interface TrainData {
  id: number;
  name: string;
  dataset_id: string | number;
  is_train_data: boolean,
  is_val_data: boolean,
  is_test_data: boolean,
}

interface TrainDataModalProps {
  options?: any;
  onSuccess: () => void;
  trainData: TrainData[];
  [key: string]: any
}

interface TrainDataParams {
  timestamp: string;
  value: number;
  label?: number;
  index?: number;
  [key: string]: any
}

interface DataSet {
  id: number;
  name: string;
  description: string;
  icon: string;
  creator: string;
  // user_id: string;
  // tenant_id: number;
}

interface AnomalyDataSet {
  id: number,
  tenant_id: number,
  description: string,
  has_labels: boolean,
  created_at: string,
  user_id: string,
  [key: string]: any
}

interface LabelData {
  timestamp: string,
  value: number,
  label?: number
}

interface AnnotationData {
  timestamp: number;
  value: number;
  label: number;
  index?: number;
  [key: string]: unknown;
}

interface FileReadResult {
  train_data: TrainDataParams[] | string[];
  headers?: string[];
}

interface RasaMenus {
  menu: string;
  icon: string;
  content: string;
}

export type {
  AsideProps,
  TrainingStatus,
  AnomalyTrainData,
  TrainDataModalProps,
  TrainData,
  TrainDataParams,
  DataSet,
  AnomalyDataSet,
  LabelData,
  AnnotationData,
  FileReadResult,
  RasaMenus
}