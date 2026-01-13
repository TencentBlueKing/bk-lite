export interface AssetListItem {
  model_id: string;
  _id: number;
  inst_name?: string;
  organization?: number[];
  organization_display?: string;
  _creator?: string;
  _labels?: string;
  [key: string]: unknown;
}

export interface ModelStat {
  model_id: string;
  count: number;
}

export interface SearchStatsResponse {
  total: number;
  model_stats: ModelStat[];
}

export interface SearchByModelParams {
  search: string;
  model_id: string;
  page?: number;
  page_size?: number;
  case_sensitive?: boolean;
}

export interface SearchByModelResponse {
  model_id: string;
  total: number;
  page: number;
  page_size: number;
  data: AssetListItem[];
}

export interface TabItem {
  key: string;
  label: string;
  children: Array<AssetListItem>;
}

export interface TabJsxItem {
  key: string;
  label: string;
  children: React.ReactElement;
}

export interface InstDetailItem {
  key: string;
  label?: string;
  children: unknown;
  id: number;
}
