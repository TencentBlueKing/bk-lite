import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';

export interface CarouselItem {
  id: number;
  resource_type: CanvasType;
  canvas_id: number;
  position: number;
  dwell_seconds: number | null;
  resolved_dwell_seconds: number;
  exists: boolean;
  visible: boolean;
  available: boolean;
  canvas_name?: string | null;
  canvas_group_ids?: number[];
}

export interface CarouselDetail {
  id: number;
  name: string;
  desc: string;
  groups: number[];
  default_dwell_seconds: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  items: CarouselItem[];
}

export interface CarouselSummary {
  id: number;
  name: string;
  desc: string;
  groups: number[];
  default_dwell_seconds: number;
  item_count: number;
  playable_count?: number;
  duration_seconds?: number;
  canvas_keys?: string[];
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface CarouselItemInput {
  id?: number;
  resource_type: CanvasType;
  canvas_id: number;
  dwell_seconds?: number | null;
}

export interface CarouselWriteInput {
  name: string;
  desc?: string;
  groups: number[];
  default_dwell_seconds: number;
  items: CarouselItemInput[];
}
