export interface CollectorItem {
  name: string;
  default_template: string;
  id: string;
  introduction: string;
  node_operating_system: string;
}

export interface CollectorListResponse {
  value: string;
  label: string;
  template: string;
}

export interface CollectorCardProps {
  id: string;
  name: string;
  system: string[];
  introduction: string;
  icon: string;
}
