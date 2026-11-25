export interface PptSkillToolCall {
  id: string;
  name: string;
  args?: string;
  result?: string;
  status: string;
}

export interface PptSkillFoldCopy {
  name: string;
  action: string;
}

const PPT_SKILL_MARKERS = ['ppt-master', 'ppt-workspace', 'svg_output'] as const;
const PPT_SHELL_TOOLS = new Set(['execute', 'shell', 'execute_command']);

export function isPptSkillToolCall(tool: { name?: string; args?: string }): boolean {
  const blob = `${tool.name || ''}\n${tool.args || ''}`;
  return PPT_SKILL_MARKERS.some((marker) => blob.includes(marker));
}

function isPptShellTool(tool: { name?: string }): boolean {
  return PPT_SHELL_TOOLS.has(tool.name || '');
}

function foldedStatus(tools: readonly { status: string }[]): string {
  const active = tools.find((tool) => tool.status === 'calling' || tool.status === 'running');
  if (active) return active.status;
  if (tools.some((tool) => tool.status === 'error')) return 'error';
  return 'completed';
}

/** 同一步里的 ppt-master 脚本和页面写入，对用户只算一次 PPT 技能。 */
export function foldPptSkillToolCalls<T extends PptSkillToolCall>(
  tools: readonly T[],
  copy: PptSkillFoldCopy,
): T[] {
  const groupHasPpt = tools.some((tool) => isPptSkillToolCall(tool));
  const belongs = (tool: T) => isPptSkillToolCall(tool) || (groupHasPpt && isPptShellTool(tool));
  const ppt = tools.filter(belongs);
  if (ppt.length === 0) return tools.slice();
  const status = foldedStatus(ppt);
  const failed = status === 'error' ? ppt.find((tool) => tool.status === 'error') : undefined;
  const bundle = {
    ...ppt[0],
    id: `ppt-skill:${ppt[0].id}`,
    name: copy.name,
    args: JSON.stringify({ action: copy.action }),
    status,
    result: failed?.result,
  } as T;
  const folded: T[] = [];
  let placed = false;
  for (const tool of tools) {
    if (!belongs(tool)) {
      folded.push(tool);
      continue;
    }
    if (!placed) {
      folded.push(bundle);
      placed = true;
    }
  }
  return folded;
}
