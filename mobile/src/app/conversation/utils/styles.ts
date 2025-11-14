export const conversationStyles = `
  .ant-bubble {
    margin-top: 10px !important;
  }
  .recommendation-item {
    transition: all 0.2s ease;
  }
  .recommendation-item:active {
    transform: scale(0.98);
  }
  .thinking-process-header {
    user-select: none;
  }
  .thinking-arrow {
    transition: transform 0.2s ease;
    font-size: 12px;
  }

  .markdown-body h1,
  .markdown-body h2,
  .markdown-body h3,
  .markdown-body h4,
  .markdown-body h5,
  .markdown-body h6 {
    margin-top: 16px;
    margin-bottom: 8px;
    font-weight: 600;
  }

  .markdown-body code {
    background: var(--color-fill-2);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: monospace;
    font-size: 14px;
  }
  .markdown-body pre {
    background: var(--color-fill-2);
    padding: 12px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 8px 0;
  }
  .markdown-body pre code {
    background: transparent;
    padding: 0;
  }
  .markdown-body ul,
  .markdown-body ol {
    padding-left: 24px;
    margin: 8px 0;
  }
  .markdown-body li {
    margin: 4px 0;
  }
  .markdown-body blockquote {
    border-left: 4px solid var(--color-primary);
    padding-left: 12px;
    margin: 8px 0;
    color: var(--color-text-3);
  }
  .markdown-body a {
    color: var(--color-primary);
    text-decoration: none;
  }
  .markdown-body a:hover {
    text-decoration: underline;
  }
  .markdown-body table {
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
  }
  .markdown-body th,
  .markdown-body td {
    border: 1px solid var(--color-border);
    padding: 8px;
    text-align: left;
  }
  .markdown-body th {
    background: var(--color-fill-1);
    font-weight: 600;
  }

  .sender-container .ant-sender-input {
    font-size: 16px !important;
  }
  .ant-bubble-footer {
    margin-top: 5px !important;
  }
  .ant-bubble-content {
    font-size: 16px !important;
  }
  
  .ant-actions-list-item {
    color: rgba(29, 108, 221);
    background-color: rgba(230, 237, 247);
    border-radius: 6px;
  }

  .dark .ant-actions-list-item {
    background-color: rgba(230, 237, 247, 0.1);
  }

  .regenerate-button {
    width: 24px;
    height: 24px;
    padding: 4px;
    color: rgba(29, 108, 221);
    background-color: rgba(230, 237, 247);
    border-radius: 6px;
  }

  .dark .regenerate-button {
    background-color: rgba(230, 237, 247, 0.1);
  }

  .action-icon {
    cursor: pointer;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
  }
  .voice-tip-top {
    font-size: 12px;
    color: var(--color-text-3);
    padding: 4px 12px;
    display: inline-block;
  }
  .voice-tip-cancel {
    color: #ff4d4f;
  }
  .voice-record-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10;
  }
  .wave-container {
    width: 100%;
    height: 100%;
    background: #4096ff;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
    overflow: hidden;
  }
  .wave-bar {
    width: 3px;
    background: white;
    border-radius: 2px;
    animation: wave 1.2s ease-in-out infinite;
  }
  @keyframes wave {
    0%, 100% {
      height: 8px;
    }
    50% {
      height: 24px;
    }
  }
  .wave-bar:nth-child(1) { animation-delay: 0s; }
  .wave-bar:nth-child(2) { animation-delay: 0.1s; }
  .wave-bar:nth-child(3) { animation-delay: 0.2s; }
  .wave-bar:nth-child(4) { animation-delay: 0.3s; }
  .wave-bar:nth-child(5) { animation-delay: 0.4s; }
  .wave-bar:nth-child(6) { animation-delay: 0.5s; }
  .wave-bar:nth-child(7) { animation-delay: 0.6s; }
  .wave-bar:nth-child(8) { animation-delay: 0.7s; }
  .wave-bar:nth-child(9) { animation-delay: 0.8s; }
  .wave-bar:nth-child(10) { animation-delay: 0.9s; }
  .wave-bar:nth-child(11) { animation-delay: 1s; }
  .wave-bar:nth-child(12) { animation-delay: 1.1s; }
  .wave-bar:nth-child(13) { animation-delay: 0.05s; }
  .wave-bar:nth-child(14) { animation-delay: 0.15s; }
  .wave-bar:nth-child(15) { animation-delay: 0.25s; }
  .wave-bar:nth-child(16) { animation-delay: 0.35s; }
  .wave-bar:nth-child(17) { animation-delay: 0.45s; }
  .wave-bar:nth-child(18) { animation-delay: 0.55s; }
  .wave-bar:nth-child(19) { animation-delay: 0.65s; }
  .wave-bar:nth-child(20) { animation-delay: 0.75s; }
  .voice-button {
    width: 100%;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-fill-2);
    border-radius: 20px;
    font-size: 15px;
    color: var(--color-text-1);
    user-select: none;
    -webkit-user-select: none;
    cursor: pointer;
    touch-action: none;
  }
  .voice-button:active {
    background: var(--color-fill-3);
  }
`;
