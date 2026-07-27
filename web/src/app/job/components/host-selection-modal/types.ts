export interface JobHostSelectionTarget {
  id: number | string;
  name: string;
  ip: string;
  os_type: string;
  os_type_display?: string;
  driver: string;
  cloud_region_name?: string;
}
