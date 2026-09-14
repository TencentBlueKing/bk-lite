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

  it('keeps screen mode independent of the share viewport lock and drops the desktop min-width floor', () => {
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
    expect(source).not.toMatch(/\['--custom-height' as string\]: '100vh'/);
    expect(source).not.toMatch(/lockConsoleViewport \|\| screenMode \? 'h-screen'/);
    expect(source).toMatch(/shouldRenderMenu/);
    expect(source).toMatch(/screenMode \? \(/);
  });
});

describe('screen mode height chain', () => {
  it('locks a definite viewport on the outer shell without share-style overflow-hidden', () => {
    expect(source).toMatch(
      /lockConsoleViewport \? 'h-screen overflow-hidden' : screenMode \? 'h-screen overflow-x-hidden' : showAppTopSide \? 'h-screen overflow-x-auto overflow-y-hidden' : 'min-h-screen'/,
    );
    expect(source).not.toMatch(/screenMode \? 'h-screen overflow-hidden'/);
    expect(source).not.toMatch(/lockConsoleViewport \|\| screenMode/);
  });

  it('gives screen main a min-h-0 full-height flex column and the app-top custom-height token', () => {
    expect(source).toMatch(
      /screenMode\s*\?\s*'min-h-0 min-w-0 h-full flex-1 flex-col p-0'/,
    );
    expect(source).toMatch(
      /style=\{showAppTopSide \|\| screenMode \? \{ \['--custom-height' as string\]: '100%' \} : undefined\}/,
    );
    expect(source).not.toMatch(/screenMode\s*\?\s*'min-w-0 flex-1 flex-col p-0'/);
  });

  it('makes the screen workspace the only default scrollport', () => {
    expect(source).toMatch(
      /data-console-screen-workspace="true"[\s\S]*className="flex h-full min-h-0 min-w-0 w-full flex-col overflow-auto"/,
    );
    expect(source).not.toMatch(
      /data-console-screen-workspace="true"[\s\S]*className="min-w-0 w-full flex-1 overflow-auto"/,
    );
  });

  it('does not add overflow-auto on the screen outer or main branches', () => {
    expect(source).not.toMatch(/screenMode \? 'h-screen overflow-auto'/);
    expect(source).not.toMatch(/screenMode\s*\?\s*'min-h-0[^']*overflow-auto/);
  });

  it('leaves the share lock and daily app-top branches intact', () => {
    expect(source).toMatch(/lockConsoleViewport \? 'h-screen overflow-hidden'/);
    expect(source).toMatch(/isDashboardShareRoute \? 'min-h-0 overflow-hidden'/);
    expect(source).toMatch(
      /!isAuthenticated \|\| isAuthRoute \|\| lockConsoleViewport \? 'h-screen'/,
    );
    expect(source).toMatch(/showAppTopSide \? 'h-screen overflow-x-auto overflow-y-hidden'/);
    expect(source).toMatch(/min-w-0 flex-col py-4 pr-4/);
  });
});
