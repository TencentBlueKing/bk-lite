export const withAlpha = (hexColor: string, alphaHex: string) =>
  `${hexColor}${alphaHex}`;

export const createHorizontalBarGradient = (color: string) => ({
  type: 'linear',
  x: 0,
  y: 0,
  x2: 1,
  y2: 0,
  colorStops: [
    { offset: 0, color: withAlpha(color, '66') },
    { offset: 1, color }
  ]
});

export const createVerticalBarGradient = (color: string) => ({
  type: 'linear',
  x: 0,
  y: 0,
  x2: 0,
  y2: 1,
  colorStops: [
    { offset: 0, color: withAlpha(color, 'CC') },
    { offset: 1, color }
  ]
});

export const createSoftLineArea = (color: string) => ({
  color: {
    type: 'linear',
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: withAlpha(color, '1F') },
      { offset: 1, color: withAlpha(color, '03') }
    ]
  }
});
