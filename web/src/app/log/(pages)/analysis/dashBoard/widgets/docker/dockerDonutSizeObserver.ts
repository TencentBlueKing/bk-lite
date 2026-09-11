export interface DonutSize {
  w: number;
  h: number;
}

export type DonutResizeObserverCtor = new (
  callback: ResizeObserverCallback
) => Pick<ResizeObserver, 'observe' | 'disconnect'>;

export function createDockerDonutSizeBinder(
  onSize: (size: DonutSize) => void,
  Observer: DonutResizeObserverCtor = ResizeObserver
) {
  let observer: Pick<ResizeObserver, 'observe' | 'disconnect'> | null = null;

  const unbind = () => {
    observer?.disconnect();
    observer = null;
  };

  const bind = (node: Element | null) => {
    unbind();
    if (!node) {
      return;
    }
    observer = new Observer((entries) => {
      for (const entry of entries) {
        onSize({
          w: entry.contentRect.width,
          h: entry.contentRect.height
        });
      }
    });
    observer.observe(node);
  };

  return { bind, unbind };
}
