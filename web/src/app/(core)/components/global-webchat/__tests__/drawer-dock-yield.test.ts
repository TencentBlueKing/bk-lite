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
  it('keeps the yield rules only in global-webchat.css', () => {
    expect(globalsCss).toMatch(/--bk-webchat-dock-width:\s*0px;/);
    expect(globalsCss).not.toMatch(/\.ant-drawer\.ant-drawer-right/);
    expect(webchatCss).toMatch(/\.ant-drawer\.ant-drawer-right\.ant-drawer-open/);
    expect(webchatCss).not.toMatch(/width:\s*calc\(\s*100vw/);
    expect(globalsCss).not.toMatch(/width:\s*calc\(\s*100vw\s*-\s*var\(--bk-webchat-dock-width/);
  });

  it('gates every right-drawer rule on a non-zero inline dock width', () => {
    const style = injectSheet(webchatCss);
    const rules = drawerRightRules(style.sheet as CSSStyleSheet);
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) {
      expect(rule.selectorText.startsWith(DOCK_OPEN_GATE)).toBe(true);
      expect(rule.selectorText).toContain('.ant-drawer.ant-drawer-right.ant-drawer-open');
      expect(rule.style.width).not.toMatch(/100vw/);
    }
  });

  it('does not match the yield gate while the dock width is 0px', () => {
    document.documentElement.style.setProperty('--bk-webchat-dock-width', '0px');
    expect(document.documentElement.matches(DOCK_OPEN_GATE)).toBe(false);
  });

  it('matches the yield gate when the dock is open and restores no 100vw width', () => {
    const style = injectSheet(webchatCss);
    document.documentElement.style.setProperty('--bk-webchat-dock-width', '380px');
    expect(document.documentElement.matches(DOCK_OPEN_GATE)).toBe(true);

    const overlay = document.createElement('div');
    overlay.className = 'ant-drawer ant-drawer-right ant-drawer-open';
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    const mask = document.createElement('div');
    mask.className = 'ant-drawer-mask';
    const wrapper = document.createElement('div');
    wrapper.className = 'ant-drawer-content-wrapper';
    overlay.append(mask, wrapper);
    document.body.appendChild(overlay);

    const rules = drawerRightRules(style.sheet as CSSStyleSheet);
    const overlayRule = rules.find(
      (rule) =>
        rule.selectorText === `${DOCK_OPEN_GATE} .ant-drawer.ant-drawer-right.ant-drawer-open`,
    );
    const wrapperRule = rules.find((rule) =>
      rule.selectorText.includes('.ant-drawer-content-wrapper'),
    );

    expect(overlayRule).toBeTruthy();
    expect(overlay.matches(overlayRule!.selectorText.replace(/^html/, ''))).toBe(true);
    expect(overlayRule!.style.inset).toBe('0 var(--bk-webchat-dock-width) 0 0');
    expect(overlayRule!.style.width).toBe('');
    expect(wrapperRule!.style.maxWidth).toBe('100%');
    expect(wrapperRule!.style.width).not.toMatch(/100vw/);
  });

  it('does not restyle a closed right drawer or a left drawer while the dock is open', () => {
    const style = injectSheet(webchatCss);
    document.documentElement.style.setProperty('--bk-webchat-dock-width', '380px');
    const rules = drawerRightRules(style.sheet as CSSStyleSheet);

    const closedRight = document.createElement('div');
    closedRight.className = 'ant-drawer ant-drawer-right';
    const leftOpen = document.createElement('div');
    leftOpen.className = 'ant-drawer ant-drawer-left ant-drawer-open';
    document.body.append(closedRight, leftOpen);

    for (const rule of rules) {
      const drawerSelector = rule.selectorText.slice(DOCK_OPEN_GATE.length).trim();
      expect(closedRight.matches(drawerSelector.split(/\s+/)[0])).toBe(false);
      expect(leftOpen.matches(drawerSelector.split(/\s+/)[0])).toBe(false);
    }
  });
});
