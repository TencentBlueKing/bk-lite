import { useCallback, useEffect, useRef, useState } from 'react';
import { Size } from 'src/types';

export const useResizeObserver = (el?: HTMLElement | null) => {
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });

  const disconnect = useCallback(() => {
    if (resizeObserverRef.current) {
      resizeObserverRef.current.disconnect();
      resizeObserverRef.current = null;
    }
  }, []);

  const observe = useCallback((element: HTMLElement) => {
    if (resizeObserverRef.current) {
      resizeObserverRef.current.disconnect();
    }

    resizeObserverRef.current = new ResizeObserver(() => {
      setSize({
        width: element.clientWidth,
        height: element.clientHeight
      });
    });

    resizeObserverRef.current.observe(element);
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  useEffect(() => {
    if (el) observe(el);
  }, [observe, el]);

  return {
    size,
    disconnect,
    observe
  };
};
