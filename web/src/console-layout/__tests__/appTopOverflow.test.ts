import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../app/layout.tsx'),
  'utf8',
);

describe('app-top chrome overflow', () => {
  it('does not clip the shell on the x-axis after adding the left rail', () => {
    expect(source).not.toMatch(/showAppTopSide \? 'h-screen overflow-hidden'/);
    expect(source).toMatch(/overflow-x-auto overflow-y-hidden/);
    expect(source).toMatch(/min-w-0 flex-col py-4 pr-4/);
  });

  it('keeps screen mode scrollable and drops the desktop min-width floor', () => {
    expect(source).toMatch(/isScreenModeEnabled/);
    expect(source).toMatch(/shouldHideConsoleChrome/);
    expect(source).toMatch(/syncScreenModePersistence/);
    expect(source).toMatch(/!screenMode && shouldShowAppTopSideNav/);
    expect(source).toMatch(/lockConsoleViewport \? 'h-screen overflow-hidden'/);
    expect(source).not.toMatch(/hideConsoleChrome \? 'h-screen'/);
    expect(source).not.toMatch(/isDashboardShareRoute \|\| hideConsoleTopNav \? 'h-screen overflow-hidden'/);
    expect(source).toMatch(/!isAuthRoute && !isResponsiveAppRoute && !screenMode \? 'min-w-\[1280px\]'/);
    expect(source).toMatch(/isAuthenticated && !isAuthRoute && !screenMode && <GlobalWebchat/);
    expect(source).toMatch(/data-console-screen-workspace/);
    expect(source).toMatch(/min-w-0 w-full flex-1 overflow-auto/);
    expect(source).not.toMatch(/\['--custom-height' as string\]: '100vh'/);
    expect(source).not.toMatch(/lockConsoleViewport \|\| screenMode \? 'h-screen'/);
    expect(source).toMatch(/shouldRenderMenu/);
    expect(source).toMatch(/screenMode \? \(/);
  });
});
