import { useEffect, useRef, useState } from 'react';

export interface VisualViewportState {
    width: number;
    height: number;
    offsetTop: number;
    offsetLeft: number;
    isKeyboardOpen: boolean;
}

const KEYBOARD_HEIGHT_THRESHOLD = 120;

const isEditableElement = (element: Element | null): boolean => (
    element instanceof HTMLInputElement
    || element instanceof HTMLTextAreaElement
    || (element instanceof HTMLElement && element.isContentEditable)
);

/**
 * 提供移动端当前真正可见的视口边界。
 *
 * iOS 聚焦输入框时既可能缩小 visual viewport，也可能平移它；因此高度和
 * offset 必须一起跟踪，并同时监听 resize/scroll，不能只读取 window.innerHeight。
 */
export const useVisualViewport = (): VisualViewportState | null => {
    const [viewportState, setViewportState] = useState<VisualViewportState | null>(null);
    const restingHeightRef = useRef(0);

    useEffect(() => {
        const visualViewport = window.visualViewport;
        let animationFrame = 0;
        let orientationTimer = 0;

        const updateViewport = () => {
            cancelAnimationFrame(animationFrame);
            animationFrame = requestAnimationFrame(() => {
                const width = Math.round(visualViewport?.width ?? window.innerWidth);
                const height = Math.round(visualViewport?.height ?? window.innerHeight);
                const editableFocused = isEditableElement(document.activeElement);

                if (!editableFocused) {
                    restingHeightRef.current = Math.max(restingHeightRef.current, height);
                } else if (restingHeightRef.current === 0) {
                    restingHeightRef.current = height;
                }

                const heightLoss = Math.max(
                    0,
                    restingHeightRef.current - height,
                    window.innerHeight - height,
                );

                setViewportState({
                    width,
                    height,
                    offsetTop: Math.round(visualViewport?.offsetTop ?? 0),
                    offsetLeft: Math.round(visualViewport?.offsetLeft ?? 0),
                    isKeyboardOpen: editableFocused && heightLoss >= KEYBOARD_HEIGHT_THRESHOLD,
                });
            });
        };

        const resetAfterOrientationChange = () => {
            restingHeightRef.current = 0;
            window.clearTimeout(orientationTimer);
            orientationTimer = window.setTimeout(updateViewport, 250);
        };

        updateViewport();
        visualViewport?.addEventListener('resize', updateViewport);
        visualViewport?.addEventListener('scroll', updateViewport);
        window.addEventListener('resize', updateViewport);
        window.addEventListener('orientationchange', resetAfterOrientationChange);
        document.addEventListener('focusin', updateViewport);
        document.addEventListener('focusout', updateViewport);

        return () => {
            cancelAnimationFrame(animationFrame);
            window.clearTimeout(orientationTimer);
            visualViewport?.removeEventListener('resize', updateViewport);
            visualViewport?.removeEventListener('scroll', updateViewport);
            window.removeEventListener('resize', updateViewport);
            window.removeEventListener('orientationchange', resetAfterOrientationChange);
            document.removeEventListener('focusin', updateViewport);
            document.removeEventListener('focusout', updateViewport);
        };
    }, []);

    return viewportState;
};
