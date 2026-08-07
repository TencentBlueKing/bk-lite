/**
 * Browser Global Entry Point
 * This file creates a global WebChat object for script injection
 */

import './styles/chat.css';
import './styles/floating-button.css';
import { Chat } from './Chat';
import { FloatingButton } from './FloatingButton';
import React from 'react';
import ReactDOM from 'react-dom/client';
import type { Root } from 'react-dom/client';

let floatingRoot: Root | null = null;
let floatingContainer: HTMLElement | null = null;

const destroyFloatingWebChat = () => {
  floatingRoot?.unmount();
  floatingRoot = null;
  floatingContainer?.remove();
  floatingContainer = null;
};

// Create global WebChat namespace
declare global {
  interface Window {
    WebChat: {
      default: (config: any, elementId: string | null) => void;
      destroy: () => void;
      Chat: typeof Chat;
      FloatingButton: typeof FloatingButton;
    };
  }
}

/**
 * Main WebChat initialization function
 * Usage: window.WebChat.default(config, elementId)
 */
const WebChatInit = (
  config: any,
  elementId?: string | null
) => {
  // If no elementId provided, create floating button mode
  if (!elementId) {
    destroyFloatingWebChat();

    // Create container
    const container = document.createElement('div');
    container.id = 'webchat-root';
    document.body.appendChild(container);

    // Create root and render floating button
    floatingContainer = container;
    floatingRoot = ReactDOM.createRoot(container);
    floatingRoot.render(React.createElement(FloatingButton, config));
    return;
  }

  // If elementId provided, render chat in specific container
  const element = document.getElementById(elementId);
  if (!element) {
    console.error(`Element with id "${elementId}" not found`);
    return;
  }

  const root = ReactDOM.createRoot(element);
  root.render(React.createElement(Chat, config));
};

// Export as global
if (typeof window !== 'undefined') {
  window.WebChat = {
    default: WebChatInit,
    destroy: destroyFloatingWebChat,
    Chat,
    FloatingButton,
  };
}

export default {
  default: WebChatInit,
  destroy: destroyFloatingWebChat,
  Chat,
  FloatingButton,
};
