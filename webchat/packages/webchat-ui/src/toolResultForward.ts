export interface CompletedToolResult {
  toolCallId: string;
  toolCallName: string;
  content: string;
}

export const rememberToolCall = (
  names: Map<string, string>,
  toolCallId: string | undefined,
  toolCallName: string | undefined,
) => {
  if (!toolCallId || !toolCallName) return;
  names.set(toolCallId, toolCallName);
};

/** Pair a finished tool result with the name recorded at TOOL_CALL_START. */
export const completedToolResult = (
  names: Map<string, string>,
  toolCallId: string,
  content: string | undefined,
): CompletedToolResult | null => {
  const toolCallName = names.get(toolCallId);
  if (!toolCallId || !toolCallName) return null;
  return {
    toolCallId,
    toolCallName,
    content: content ?? '',
  };
};
