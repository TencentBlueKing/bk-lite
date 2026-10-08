export interface PageCommandEvent {
  type?: string;
  name: string;
  value?: unknown;
}

type PageCommandHandler = (value: unknown) => void;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

const handlers = new Map<string, Set<PageCommandHandler>>();

export const registerPageCommand = (name: string, handler: PageCommandHandler) => {
  const current = handlers.get(name) ?? new Set<PageCommandHandler>();
  current.add(handler);
  handlers.set(name, current);
  return () => {
    const next = handlers.get(name);
    next?.delete(handler);
    if (next && next.size === 0) handlers.delete(name);
  };
};

export const dispatchPageCommand = (event: PageCommandEvent) => {
  const name = event.name === 'CUSTOM' && isRecord(event.value) && typeof event.value.type === 'string'
    ? event.value.type
    : event.name;
  const value = event.name === 'CUSTOM' && isRecord(event.value) && 'payload' in event.value
    ? event.value.payload
    : event.value;
  handlers.get(name)?.forEach((handler) => handler(value));
};

export const resetPageCommandsForTests = () => {
  handlers.clear();
};
