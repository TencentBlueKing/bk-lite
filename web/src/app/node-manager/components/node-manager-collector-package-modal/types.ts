export interface NodeManagerCollectorPackageModalFormData {
  id?: string | number;
  [key: string]: any;
}

export interface NodeManagerCollectorPackageModalConfig {
  type: string;
  title?: string;
  form?: NodeManagerCollectorPackageModalFormData;
  key?: string;
  ids?: string[];
  selectedsystem?: string;
  selectedArchitecture?: string;
  nodes?: string[];
  [key: string]: any;
}

export interface NodeManagerCollectorPackageModalRef {
  showModal: (config: NodeManagerCollectorPackageModalConfig) => void;
}

export interface NodeManagerCollectorPackageModalSuccess {
  onSuccess: (config?: any) => void;
  config?: any;
}
