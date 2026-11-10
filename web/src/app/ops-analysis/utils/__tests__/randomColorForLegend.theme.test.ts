import { describe, expect, it } from 'vitest';

import { randomColorForLegend as widgetRandomColorForLegend } from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';

const COLOR_LIST = [
  '84,112,198',
  '145,204,117',
  '250,200,88',
  '238,102,102',
  '115,192,222',
  '59,162,114',
  '252,132,82',
  '154,96,180',
  '234,124,204',
  '50,197,233',
  '204,117,117',
  '204,117,181',
  '163,117,204',
  '117,154,204',
  '117,166,204',
  '117,198,204',
  '117,204,169',
  '142,204,117',
  '193,204,117',
  '204,147,117',
];

const LIGHT_OPACITY = [1, 0.8, 0.6, 0.4];
const DARK_OPACITY = [1, 0.92, 0.84, 0.76];

const themedPrefix = (opacity: number[]) => opacity.flatMap((alpha) => (
  COLOR_LIST.map((rgb) => `rgba(${rgb}, ${alpha})`)
));

describe('randomColorForLegend theme cache', () => {
  it('keeps the same palette until the theme changes', () => {
    const light = randomColorForLegend('light');
    const lightAgain = randomColorForLegend('light');
    const dark = randomColorForLegend('dark');
    const darkAgain = randomColorForLegend('dark');

    expect(lightAgain).toBe(light);
    expect(darkAgain).toBe(dark);
    expect(light.slice(0, 80)).toEqual(themedPrefix(LIGHT_OPACITY));
    expect(dark.slice(0, 80)).toEqual(themedPrefix(DARK_OPACITY));
    expect(light[80]).toBe(lightAgain[80]);
    expect(dark[80]).not.toBe(light[80]);
    expect(randomColorForLegend('light')[80]).toBe(light[80]);
  });

  it('caches the widget palette separately per theme', () => {
    const light = widgetRandomColorForLegend('light');
    expect(widgetRandomColorForLegend('light')).toBe(light);
    expect(widgetRandomColorForLegend('dark').slice(0, 80)).toEqual(themedPrefix(DARK_OPACITY));
    expect(widgetRandomColorForLegend('light')[80]).toBe(light[80]);
  });
});
