import { describe, expect, it } from 'vitest';

import {
  RELATED_TOPOLOGY_CANVAS_STYLE,
  RELATED_TOPOLOGY_DEFAULT_CHROME,
  RELATED_TOPOLOGY_SCREEN_CANVAS_STYLE,
  RELATED_TOPOLOGY_SCREEN_DARK_CHROME,
  RELATED_TOPOLOGY_VISUAL,
  relatedTopologyCanvasStyle,
  relatedTopologyGraphChrome,
} from '../visual';

describe('related topology canvas chrome', () => {
  it('keeps the dashboard canvas on the default surface', () => {
    expect(relatedTopologyCanvasStyle(false)).toBe(RELATED_TOPOLOGY_CANVAS_STYLE);
    expect(RELATED_TOPOLOGY_CANVAS_STYLE.background).toContain('radial-gradient');
    expect(RELATED_TOPOLOGY_CANVAS_STYLE.background).not.toContain(
      '--screen-widget-bg',
    );
  });

  it('uses screen widget tokens on the screen surface', () => {
    expect(relatedTopologyCanvasStyle(true)).toBe(
      RELATED_TOPOLOGY_SCREEN_CANVAS_STYLE,
    );
    expect(RELATED_TOPOLOGY_SCREEN_CANVAS_STYLE.background).toContain(
      '--screen-widget-bg',
    );
    expect(RELATED_TOPOLOGY_SCREEN_CANVAS_STYLE.border).toContain(
      '--screen-widget-border',
    );
    expect(RELATED_TOPOLOGY_SCREEN_CANVAS_STYLE.boxShadow).toContain(
      '--screen-widget-shadow',
    );
  });
});

describe('related topology graph chrome', () => {
  it('keeps dashboard cards, edges, and labels on the default surface', () => {
    expect(relatedTopologyGraphChrome()).toBe(RELATED_TOPOLOGY_DEFAULT_CHROME);
    expect(relatedTopologyGraphChrome('default')).toBe(
      RELATED_TOPOLOGY_DEFAULT_CHROME,
    );
    expect(relatedTopologyGraphChrome('screen-light')).toBe(
      RELATED_TOPOLOGY_DEFAULT_CHROME,
    );
    expect(RELATED_TOPOLOGY_DEFAULT_CHROME.cardDefaultBody.fill).toBe(
      RELATED_TOPOLOGY_VISUAL.card.defaultBody.fill,
    );
    expect(RELATED_TOPOLOGY_DEFAULT_CHROME.labelFill).toBe(
      RELATED_TOPOLOGY_VISUAL.card.label.fill,
    );
    expect(RELATED_TOPOLOGY_DEFAULT_CHROME.edgeLabelFill).toBe(
      RELATED_TOPOLOGY_VISUAL.labelFill,
    );
    expect(RELATED_TOPOLOGY_DEFAULT_CHROME.edgeLabelRectFill).toBe('#fcfeff');
  });

  it('uses the dark status-topology palette on the screen-dark surface', () => {
    expect(relatedTopologyGraphChrome('screen-dark')).toBe(
      RELATED_TOPOLOGY_SCREEN_DARK_CHROME,
    );
    expect(RELATED_TOPOLOGY_SCREEN_DARK_CHROME.cardDefaultBody.fill).not.toBe(
      RELATED_TOPOLOGY_DEFAULT_CHROME.cardDefaultBody.fill,
    );
    expect(RELATED_TOPOLOGY_SCREEN_DARK_CHROME.labelFill).toBe('#eef4fc');
    expect(RELATED_TOPOLOGY_SCREEN_DARK_CHROME.subFill).toBe(
      'rgba(211, 225, 241, 0.82)',
    );
    expect(RELATED_TOPOLOGY_SCREEN_DARK_CHROME.edgeStroke).toBe(
      'rgba(168, 196, 228, 0.78)',
    );
    expect(RELATED_TOPOLOGY_SCREEN_DARK_CHROME.edgeLabelFill).toBe(
      'rgba(211, 225, 241, 0.92)',
    );
    expect(RELATED_TOPOLOGY_SCREEN_DARK_CHROME.cardActiveBody.stroke).toBe(
      '#73A7FF',
    );
    expect(RELATED_TOPOLOGY_SCREEN_DARK_CHROME.edgeLabelRectFill).not.toBe(
      '#fcfeff',
    );
  });
});
