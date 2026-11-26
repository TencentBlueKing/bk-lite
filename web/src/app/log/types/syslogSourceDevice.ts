export interface SyslogSourceDeviceRow {
  cloud_region_id: string;
  cloud_region_name: string;
  source_ip: string;
  hostname: string;
  first_seen: string;
  last_seen: string;
  status: 'active' | 'silent';
  search_query: string;
  search_start: number;
  search_end: number;
}

export interface SyslogSourceDeviceListResponse {
  count: number;
  items: SyslogSourceDeviceRow[];
}

export interface SyslogSourceDeviceQuery {
  cloud_region_id?: string;
  source_ip?: string;
  hostname?: string;
  keyword?: string;
  status?: 'active' | 'silent';
  page?: number;
  page_size?: number;
}
