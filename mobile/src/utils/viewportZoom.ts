const VIEWPORT_SELECTOR = 'meta[name="viewport"]';
const NATIVE_ZOOM_SETTINGS = ['maximum-scale=1', 'user-scalable=no'];

function withoutZoomSettings(content: string): string[] {
  return content
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .filter((part) => {
      const key = part.split('=', 1)[0]?.trim().toLowerCase();
      return key !== 'maximum-scale' && key !== 'user-scalable';
    });
}

/**
 * 原生 Tauri WebView 按 App 交互禁用页面缩放；H5 保持浏览器默认缩放能力。
 */
export function applyNativeViewportZoomPolicy(): () => void {
  if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) {
    return () => undefined;
  }

  const viewport = document.querySelector<HTMLMetaElement>(VIEWPORT_SELECTOR);
  const originalContent = viewport?.getAttribute('content') || '';

  if (viewport) {
    const nativeContent = [
      ...withoutZoomSettings(originalContent),
      ...NATIVE_ZOOM_SETTINGS,
    ].join(', ');
    viewport.setAttribute('content', nativeContent);
  }

  const preventPinchZoom = (event: TouchEvent) => {
    if (event.touches.length > 1) event.preventDefault();
  };

  let lastTouchEnd = 0;
  const preventDoubleTapZoom = (event: TouchEvent) => {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) event.preventDefault();
    lastTouchEnd = now;
  };

  const preventGestureZoom = (event: Event) => event.preventDefault();

  document.addEventListener('touchstart', preventPinchZoom, { passive: false });
  document.addEventListener('touchend', preventDoubleTapZoom, { passive: false });
  document.addEventListener('gesturestart', preventGestureZoom, { passive: false });

  return () => {
    if (viewport) viewport.setAttribute('content', originalContent);
    document.removeEventListener('touchstart', preventPinchZoom);
    document.removeEventListener('touchend', preventDoubleTapZoom);
    document.removeEventListener('gesturestart', preventGestureZoom);
  };
}
