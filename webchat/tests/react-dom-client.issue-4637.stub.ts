export const createRoot = () => ({
  render: (node: unknown) => {
    (globalThis as typeof globalThis & { __webchatRendered?: unknown }).__webchatRendered = node;
  },
  unmount: () => undefined,
});

export default { createRoot };
