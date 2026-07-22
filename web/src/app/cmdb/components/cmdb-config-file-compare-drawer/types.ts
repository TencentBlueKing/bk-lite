export interface CmdbConfigFileCompareTargetLike {
  latest_version_id: number;
  file_path: string;
  file_name: string;
  collect_task_id: number | null;
  latest_version: string;
  latest_status: string;
  latest_created_at: string;
}

export interface CmdbConfigFileVersionLike {
  id: number;
  collect_task_id: number | null;
  instance_id: string;
  model_id: string;
  version: string;
  file_path: string;
  file_name: string;
  content_hash: string;
  content_key: string;
  file_size: number;
  status: string;
  error_message: string;
  created_at: string;
}
