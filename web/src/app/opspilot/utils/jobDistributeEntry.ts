/** 与服务端 skill_has_job_mgmt 使用同一个工具名。 */
export const JOB_MGMT_TOOL_NAME = 'job_mgmt';

export function skillSelectionEnablesJobDistribute(
  tools: Array<{ name?: string; rawName?: string }>,
): boolean {
  return tools.some((tool) => (tool.rawName || tool.name) === JOB_MGMT_TOOL_NAME);
}

/** 技能测试没有 SkillConversation，会话键与 thread_id 归一结果一致。 */
export function skillDebugDistributeSessionId(threadId: string): string {
  const id = threadId.trim();
  return id ? `thread:${id}` : '';
}
