export interface IncidentLevelFilterSource {
  level_id: number;
  level_display_name: string;
  color?: string;
}

export interface IncidentLevelFilterOption {
  value: string;
  label: string;
  color?: string;
}

export function toIncidentLevelFilterOptions(
  levelListIncident: IncidentLevelFilterSource[]
): IncidentLevelFilterOption[] {
  return (levelListIncident || []).map((item) => ({
    value: String(item.level_id),
    label: item.level_display_name,
    color: item.color,
  }));
}
