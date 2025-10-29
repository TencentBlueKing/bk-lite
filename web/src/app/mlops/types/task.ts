import { Option } from "."

interface TrainJob {
  id: string | number,
  name: string,
  // type: string,
  status?: string,
  created_at: string,
  train_data_id?: string | number;
  val_data_id?: string | number;
  test_data_id?: string | number;
  [key: string]: any
}

interface TrainTaskModalProps {
  options?: any;
  onSuccess: () => void;
  activeTag: string[];
  [key: string]: any
}

interface AlgorithmParam {
  name: string;
  type: 'randint' | 'choice';
  default: string[] | number | [number, number];
  options?: Option[]
}

interface TrainTaskHistory {
  id: number;
  job_id: number;
  tenant_id: number;
  train_data_id: number;
  user_id: string;
  parameters: string;
  status: string;
  created_at?: string;
  started_at?: string;
  updated_at?: string;
  completed_at?: string;
  anomaly_detection_train_jobs: {
    name: string;
  }
}

export type {
  TrainJob,
  TrainTaskModalProps,
  AlgorithmParam,
  TrainTaskHistory
}