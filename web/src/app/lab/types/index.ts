// Container state types
export type ContarinerState = 'running' | 'stopped' | 'starting' | 'stopping' | 'restarting' | 'paused' | 'unknown' | 'error';

// Lab image types
export interface LabImageItem {
  id: number | string;
  name: string;
  version: string;
  image_type: 'ide' | 'infra';
  image_url: string;
  default_port?: number;
  description?: string;
  environment?: Record<string, string>;
  command?: string[];
  args?: string[];
  exposed_ports?: number[];
  volumes?: Array<{
    container_path: string;
    host_path?: string;
    read_only?: boolean;
  }>;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  icon?: string;
  creator?: string;
}

// Lab environment types
export interface InfraInstanceInfo {
  id: number | string;
  name: string;
  image: number | string;
  image_id?: number | string;
  image_name?: string;
  image_version?: string;
}

export interface LabEnvItem {
  id: number | string;
  name: string;
  description?: string;
  ide_image: number | string;
  ide_image_name?: string;
  ide_image_version?: string;
  infra_images?: (number | string)[];
  infra_instances?: (number | string)[];
  infra_instances_info?: InfraInstanceInfo[];
  cpu: number;
  memory: string;
  gpu: number;
  volume_size: string;
  state?: ContarinerState;
  endpoint?: string;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  icon?: string;
  creator?: string;
}

export interface TableData {
  id: number,
  name: string,
  anomaly?: number,
  [key: string]: any
}

//调用弹窗的类型
export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

//调用弹窗接口传入的类型
export interface ModalConfig {
  type: string;
  title?: string;
  form?: any;
  key?: string;
  ids?: string[];
  selectedsystem?: string;
  nodes?: string[];
}