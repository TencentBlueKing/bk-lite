export interface CompletedToolResult {
  toolCallId: string;
  toolCallName: string;
  content: string;
}

type ToolResultHandler = (result: CompletedToolResult) => void;

const handlers = new Map<string, Set<ToolResultHandler>>();

export const registerToolResultHandler = (toolName: string, handler: ToolResultHandler) => {
  const current = handlers.get(toolName) ?? new Set<ToolResultHandler>();
  current.add(handler);
  handlers.set(toolName, current);
  return () => {
    const next = handlers.get(toolName);
    next?.delete(handler);
    if (next && next.size === 0) handlers.delete(toolName);
  };
};

export const dispatchCompletedToolResult = (result: CompletedToolResult) => {
  if (!result.toolCallName) return;
  handlers.get(result.toolCallName)?.forEach((handler) => handler(result));
};

export const resetToolResultHandlersForTests = () => {
  handlers.clear();
};
