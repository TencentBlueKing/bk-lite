/**
 * 全零折线的绘制层上移。
 * 采样值保持 0，轴下限保持 0。只把彩色笔画中心在像素上抬离 X 轴。
 */

export interface FlatZeroPoint {
  time: number;
  value: number | null;
}

export interface FlatZeroStrokeInput {
  name: string;
  color: string;
  points: ReadonlyArray<readonly [number, number | null]>;
  liftPx: number;
  dashed?: boolean;
  /** 缺省画出采样点。点数多的趋势可以关掉。 */
  symbols?: boolean;
  /** 采样点半径。缺省 3，与原来的零线点一致。 */
  symbolRadius?: number;
  /** 缺省把采样连成一条。打开后，空点把折线断开。 */
  breakOnNull?: boolean;
}

interface RenderParams {
  dataIndex: number;
}

interface RenderApi {
  coord: (value: [number, number]) => number[];
}

/** 像素 Y 向下增长，减去间距就是离开 X 轴向上。 */
export const liftStrokeY = (pixelY: number, liftPx: number) => pixelY - liftPx;

const strokeSegments = (
  points: ReadonlyArray<readonly [number, number | null]>,
  liftPx: number,
  api: RenderApi,
  breakOnNull: boolean
) => {
  const segments: number[][][] = [];
  let current: number[][] = [];
  const flush = () => {
    if (current.length) segments.push(current);
    current = [];
  };
  points.forEach((point) => {
    const time = point[0];
    const value = point[1];
    if (typeof value !== 'number' || !Number.isFinite(value) || !Number.isFinite(time)) {
      if (breakOnNull) flush();
      return;
    }
    const pixel = api.coord([time, value]);
    if (!pixel || pixel.length < 2 || !Number.isFinite(pixel[0]) || !Number.isFinite(pixel[1])) {
      if (breakOnNull) flush();
      return;
    }
    current.push([pixel[0], liftStrokeY(pixel[1], liftPx)]);
  });
  flush();
  return segments;
};

export const flatZeroStrokeSeries = ({
  name,
  color,
  points,
  liftPx,
  dashed = false,
  symbols = true,
  symbolRadius = 3,
  breakOnNull = false
}: FlatZeroStrokeInput) => ({
  type: 'custom' as const,
  name,
  coordinateSystem: 'cartesian2d' as const,
  clip: false as const,
  z: 4,
  silent: false,
  data: points.map((point) => [point[0], point[1]]),
  encode: { x: 0, y: 1, tooltip: [1] },
  renderItem: (params: RenderParams, api: RenderApi) => {
    if (params.dataIndex !== 0) return null;
    const segments = strokeSegments(points, liftPx, api, breakOnNull);
    if (!segments.length) return null;
    return {
      type: 'group' as const,
      children: [
        ...segments.map((coords) => ({
          type: 'polyline' as const,
          shape: { points: coords },
          style: {
            stroke: color,
            fill: 'none',
            lineWidth: dashed ? 1.2 : 1.6,
            lineDash: dashed ? [4, 4] : undefined
          }
        })),
        ...(symbols ? segments.flatMap((coords) => coords.map((coord) => ({
          type: 'circle' as const,
          shape: { cx: coord[0], cy: coord[1], r: symbolRadius },
          style: { fill: color }
        }))) : [])
      ]
    };
  }
});
