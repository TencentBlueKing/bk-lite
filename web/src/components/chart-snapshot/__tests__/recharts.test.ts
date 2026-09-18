import { describe, expect, it } from 'vitest';

import {
  captionFromRechartsRoot,
  captureRechartsFromDoms,
  svgElementToDataUrl,
} from '../recharts';

const svgMarkup = `
  <svg xmlns="http://www.w3.org/2000/svg" width="80" height="40">
    <rect width="80" height="40" fill="#f00" />
  </svg>
`;

describe('captureRechartsFromDoms', () => {
  it('returns empty when there is no svg', async () => {
    document.body.innerHTML = '<div class="recharts-wrapper"></div>';
    const root = document.querySelector<HTMLElement>('.recharts-wrapper');
    expect(await captureRechartsFromDoms(root ? [root] : [])).toEqual([]);
  });

  it('serializes svg to a data url and reads nearby collapse title', async () => {
    document.body.innerHTML = `
      <div>
        <div class="collapse-title"><span class="title">告警级别分布</span></div>
        <div class="collapse-content">
          <div class="recharts-wrapper">${svgMarkup}</div>
        </div>
      </div>
    `;
    const root = document.querySelector<HTMLElement>('.recharts-wrapper');
    expect(root && captionFromRechartsRoot(root)).toBe('告警级别分布');
    const images = await captureRechartsFromDoms(root ? [root] : [], 6);
    expect(images).toHaveLength(1);
    expect(images[0].caption).toBe('告警级别分布');
    expect(images[0].dataUrl.startsWith('data:image/')).toBe(true);
  });

  it('caps at the given limit', async () => {
    document.body.innerHTML = `
      <div id="a">${svgMarkup}</div>
      <div id="b">${svgMarkup}</div>
    `;
    const roots = [
      document.getElementById('a') as HTMLElement,
      document.getElementById('b') as HTMLElement,
    ];
    expect(await captureRechartsFromDoms(roots, 1)).toHaveLength(1);
  });

  it('encodes svg xml as a data url', () => {
    document.body.innerHTML = svgMarkup;
    const svg = document.querySelector('svg') as SVGSVGElement;
    expect(svgElementToDataUrl(svg).startsWith('data:image/svg+xml')).toBe(true);
  });
});
