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
  id?: number;
  name: string;
  icon?: string;
  kwargs: ToolVariable[];
}

function serializeTool(tool: SelectTool): SkillSaveToolPayload {
  const kwargs = normalizeMonitorToolConfig(tool).kwargs;
  return {
    id: tool.id,
    name: tool.rawName || tool.name,
    icon: tool.icon,
    kwargs: (Array.isArray(kwargs) ? kwargs : []).filter(kwarg => kwarg.key),
  };
}

export const buildSkillSaveTools = (tools: SelectTool[]) => tools.map(serializeTool);

/** Omit an untouched selection. An explicit empty selection means remove all bindings. */
export function skillToolUpdate(edited: SelectTool[] | null, saved: SelectTool[]): { tools?: SelectTool[] } {
  if (edited === null) return {};
  return { tools: edited.map(tool => saved.includes(tool) ? normalizeMonitorToolConfig(tool) : serializeTool(tool)) };
}

export const buildStudioRuntimeTools = (tools: SelectTool[]): SelectTool[] => (
  normalizeMonitorToolConfigs(tools)
);
