export interface ConfigFileItem {
  latest_version_id: number;
  file_path: string;
  file_name: string;
  collect_task_id: number | null;
  latest_version: string;
  latest_status: string;
  latest_created_at: string;
}

export interface ConfigFileContentResponse {
  content: string;
  encoding: string;
  raw_base64: string;
}

export interface ConfigFileVersion {
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

export interface ConfigFileDiffResponse {
  version_1: string;
  version_2: string;
  diff_text: string;
}

export interface CreateManualConfigFileParams {
  instance_id: string;
  model_id: string;
  file_path: string;
  content: string;
}
