export interface ApplicationTopologyNodePayload {
  id: string;
  name: string;
  model_id: string;
  hop: number;
  category?: string;
  app_topo_layer?: string;
  monitor_id: string;
  alert_count: number | null;
  max_level: string | null;
}

export interface ApplicationTopologyLinkPayload {
  id: string;
  source: string;
  target: string;
  asst_id?: string;
}

export interface ApplicationTopologyResponse {
  center_inst_uuid: string;
  depth: number;
  center: ApplicationTopologyNodePayload;
  nodes: ApplicationTopologyNodePayload[];
  links: ApplicationTopologyLinkPayload[];
}
