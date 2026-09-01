'use client';

import React from 'react';

const consoleLayoutBootstrapScript = `(()=>{let m='classic';try{m=localStorage.getItem('console-chrome-layout')==='app-top'?'app-top':'classic'}catch{}const e=document.documentElement;e.classList.toggle('console-layout-app-top',m==='app-top');e.classList.toggle('console-layout-classic',m==='classic');e.dataset.consoleLayout=m;window.__BK_LITE_CONSOLE_LAYOUT__=m})();`;

declare global {
  interface Window {
    __BK_LITE_CONSOLE_LAYOUT__?: 'classic' | 'app-top';
  }
}

export const ConsoleLayoutBootstrap = () => (
  <script
    id="bklite-console-layout-bootstrap"
    dangerouslySetInnerHTML={{ __html: consoleLayoutBootstrapScript }}
  />
);
