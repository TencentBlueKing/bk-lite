'use client';

/**
 * CSS-free entry for hosts that already compile Tailwind (e.g. BK-Lite).
 * Only FloatingButton is a value export so the console does not eagerly load Chat
 * (markdown / syntax highlighter) on every page. Open the FAB to load the panel.
 * The package `index.ts` still bundles webchat CSS for standalone embeds.
 */
export { FloatingButton, type FloatingButtonProps } from './FloatingButton';
export { PlatformChat, type PlatformChatProps } from './PlatformChat';
export type { ChatProps } from './chatProps';
