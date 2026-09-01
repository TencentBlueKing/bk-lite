'use client';

import React from 'react';
import { createThemeCss } from './css-adapter';
import { defaultTheme } from './defaults';

const themeBootstrapScript = `(()=>{let m='light';try{m=localStorage.getItem('theme')==='dark'?'dark':'light'}catch{}const e=document.documentElement;e.classList.toggle('dark',m==='dark');e.classList.toggle('light',m==='light');e.style.colorScheme=m;window.__BK_LITE_THEME_MODE__=m})();`;

declare global {
  interface Window {
    __BK_LITE_THEME_MODE__?: 'light' | 'dark';
  }
}

export const ThemeBootstrap = () => (
  <>
    <style
      id="bklite-theme-tokens"
      dangerouslySetInnerHTML={{ __html: createThemeCss(defaultTheme) }}
    />
    <script
      id="bklite-theme-bootstrap"
      dangerouslySetInnerHTML={{ __html: themeBootstrapScript }}
    />
  </>
);
