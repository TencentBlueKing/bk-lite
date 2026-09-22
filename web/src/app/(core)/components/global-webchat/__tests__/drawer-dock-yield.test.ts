import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

const webchatCss = readFileSync(resolve(__dirname, '../global-webchat.css'), 'utf8');
const globalsCss = readFileSync(resolve(__dirname, '../../../../../styles/globals.css'), 'utf8');

/** 与 global-webchat.css 中 dock 打开门控保持一致；host 用 setProperty 写入非 0 宽度。 */
const DOCK_OPEN_GATE =
  'html[style*="--bk-webchat-dock-width:"]:not([style*="--bk-webchat-dock-width: 0px"])';

const injectSheet = (css: string) => {
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
  return style;
};

const drawerRightRules = (sheet: CSSStyleSheet): CSSStyleRule[] =>
  Array.from(sheet.cssRules).filter(
    (rule): rule is CSSStyleRule =>
      rule instanceof CSSStyleRule && rule.selectorText.includes('.ant-drawer-right'),
  );

afterEach(() => {
  document.querySelectorAll('style').forEach((node) => node.remove());
  document.documentElement.removeAttribute('style');
  document.body.replaceChildren();
});

describe('WebChat dock drawer yield CSS', () => {
  it('keeps the yield rules only in global-webchat.css and does not demote webchat z-index', () => {
    expect(globalsCss).toMatch(/--bk-webchat-dock-width:\s*0px;/);
    expect(globalsCss).not.toMatch(/\.ant-drawer\.ant-drawer-right/);
    expect(webchatCss).toMatch(/\.ant-drawer\.ant-drawer-right/);
    expect(webchatCss).toMatch(/overflow:\s*hidden/);
    expect(webchatCss).not.toMatch(/z-index:\s*950/);
    expect(webchatCss).not.toMatch(/\.ant-drawer[^{]*\{[^}]*width:\s*calc\(\s*100vw/);
    expect(globalsCss).not.toMatch(/width:\s*calc\(\s*100vw\s*-\s*var\(--bk-webchat-dock-width/);
  });

  it('anchors right drawers to --bk-webchat-dock-width with overflow hidden across lifecycle', () => {
    const style = injectSheet(webchatCss);
    const rules = drawerRightRules(style.sheet as CSSStyleSheet);
    expect(rules.length).toBeGreaterThan(0);

    const overlayRule = rules.find((rule) => rule.selectorText === '.ant-drawer.ant-drawer-right');
    const wrapperRule = rules.find((rule) =>
      rule.selectorText === '.ant-drawer.ant-drawer-right .ant-drawer-content-wrapper',
    );

    expect(overlayRule).toBeTruthy();
    expect(overlayRule!.style.right).toContain('var(--bk-webchat-dock-width');
    expect(overlayRule!.style.overflow).toBe('hidden');
    expect(overlayRule!.style.width).toBe('');

    expect(wrapperRule).toBeTruthy();
    expect(wrapperRule!.style.maxWidth).toBe('100%');
    expect(wrapperRule!.style.transition).toBe('');
    expect(wrapperRule!.style.width).not.toMatch(/100vw/);
  });

  it('leaves modal mask below webchat z-1200 and offsets modal-wrap when dock is open', () => {
    const style = injectSheet(webchatCss);
    document.documentElement.style.setProperty('--bk-webchat-dock-width', '380px');
    const rules = Array.from((style.sheet as CSSStyleSheet).cssRules).filter(
      (rule): rule is CSSStyleRule => rule instanceof CSSStyleRule && rule.selectorText.includes('.ant-modal'),
    );
    expect(rules.length).toBeGreaterThan(0);

    const wrapRule = rules.find((rule) => rule.selectorText.includes('.ant-modal-wrap'));
    expect(wrapRule).toBeTruthy();
    expect(wrapRule!.selectorText.startsWith(DOCK_OPEN_GATE)).toBe(true);
    expect(wrapRule!.style.right).toContain('var(--bk-webchat-dock-width)');
  });
});
