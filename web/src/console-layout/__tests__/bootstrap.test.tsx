import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ConsoleLayoutBootstrap } from '../bootstrap';

describe('ConsoleLayoutBootstrap', () => {
  it('applies stored layout before paint without reading other keys', () => {
    const markup = renderToStaticMarkup(<ConsoleLayoutBootstrap />);
    expect(markup).toContain('id="bklite-console-layout-bootstrap"');
    expect(markup).toContain("localStorage.getItem('console-chrome-layout')");
    expect(markup).not.toContain("localStorage.getItem('theme')");
  });
});
