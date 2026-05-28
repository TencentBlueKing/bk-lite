export interface RelatedAlertIncidentItem {
  id: number;
  incident_id: string;
  title: string;
}

export interface RelatedAlertItem {
  id: number;
  alert_id: string;
  title: string;
  content: string;
  level: string;
  status: string;
  first_event_time: string | null;
  last_event_time: string | null;
  incidents: RelatedAlertIncidentItem[];
  similarity_score: number;
  match_reason: string;
  matched_dimensions: Record<string, string>;
  time_proximity: string;
}

export interface RelatedAlertsResponse {
  related_count: number;
  maybe_related_count: number;
  current_incidents: RelatedAlertIncidentItem[];
  items: RelatedAlertItem[];
}
