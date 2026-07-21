export interface RoomRack {
  inst_id: string;
  inst_name: string;
  row: number;
  col: number;
  col_letter: string;
  location: string | null;
  u_count: number;
  used_u: number;
  usage: number;
  free_u: number;
  max_free_u: number;
  datacenter_type: string | null;
  datacenter_state: string | null;
}

export interface RoomLayoutData {
  racks: RoomRack[];
  unplaced: Array<
    Omit<RoomRack, 'col_letter' | 'usage'> & {
      unplaced_reason: 'missing_location' | 'invalid_location';
    }
  >;
  conflicts: Array<{ row: number; col: number; inst_ids: string[] }>;
  grid: { max_row: number; max_col: number };
}

export interface RackDevice {
  inst_id: string;
  inst_name: string;
  model_id: string;
  rack_u_start: number;
  u_size: number;
  u_end: number;
  overflow: boolean;
}

export interface RackLayoutData {
  u_count: number;
  free_u: number;
  max_free_u: number;
  rack: { inst_id: string; inst_name: string; u_count: number };
  placed: RackDevice[];
  unplaced: Array<Pick<RackDevice, 'inst_id' | 'inst_name' | 'model_id'>>;
  overlaps: string[][];
}
