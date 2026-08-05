import type { SelectTool, ToolVariable } from '@/app/opspilot/types/tool';

export const MONITOR_TOOL_CANONICAL_NAME = 'monitor';

interface MonitorToolConfigLike {
  name?: string;
  rawName?: string;
}

export const isMonitorToolConfig = (tool?: MonitorToolConfigLike | null) => (
  (tool?.rawName || tool?.name) === MONITOR_TOOL_CANONICAL_NAME
);

export const normalizeMonitorToolConfig = (tool: SelectTool): SelectTool => {
  if (!isMonitorToolConfig(tool)) {
    return tool;
  }

  return {
    ...tool,
    kwargs: [],
  };
};

export const normalizeMonitorToolConfigs = (tools: SelectTool[]): SelectTool[] => (
  tools.map(normalizeMonitorToolConfig)
);

export interface SkillSaveToolPayload {
  id: number;
  name: string;
  icon: string;
  kwargs: ToolVariable[];
}

export const buildSkillSaveTools = (tools: SelectTool[]): SkillSaveToolPayload[] => (
  normalizeMonitorToolConfigs(tools).map((tool) => ({
    id: tool.id,
    name: tool.rawName || tool.name,
    icon: tool.icon,
    kwargs: (tool.kwargs || []).filter((kwarg) => kwarg.key),
  }))
);

export const buildStudioRuntimeTools = (tools: SelectTool[]): SelectTool[] => (
  normalizeMonitorToolConfigs(tools)
);
