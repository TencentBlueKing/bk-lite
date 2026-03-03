// 自定义连接器，用于绘制反向曲线
import { Graph, Line, Curve, Path } from '@antv/x6';
let isRegistered = false;

/**
 * Register a custom connector that draws a smooth curved edge for reverse links.
 * Safeguarded to run only once even if invoked multiple times.
 */
export const registerReverseCurveConnector = () => {
  if (isRegistered) return;

  Graph.registerConnector(
    'reverse-curve',
    (
      sourcePoint,
      targetPoint,
      routePoints,
      options: { raw?: boolean; curvature?: number; direction?: 'up' | 'down' },
    ) => {
      const { raw = false, curvature = 50, direction = 'up' } = options || {};

      // Base line between source and target
      const line = new Line(sourcePoint, targetPoint);
      const center = line.getCenter();

      // Perpendicular direction to determine curve direction
      const angle = line.angle();
      const perpendicularAngle = angle + 90;

      // Upwards or downwards curve
      const curvatureSign = direction === 'up' ? 1 : -1;

      // Control point displaced from the center
      const controlPoint = {
        x:
          center.x +
          Math.cos((perpendicularAngle * Math.PI) / 180) *
          curvature *
          curvatureSign,
        y:
          center.y +
          Math.sin((perpendicularAngle * Math.PI) / 180) *
          curvature *
          curvatureSign,
      };

      // Quadratic bezier path
      const pathData = `M ${sourcePoint.x} ${sourcePoint.y} Q ${controlPoint.x} ${controlPoint.y} ${targetPoint.x} ${targetPoint.y}`;

      if (raw) {
        const points = [sourcePoint, controlPoint, targetPoint];
        const curves = Curve.throughPoints(points);
        const path = new Path(curves);
        return path;
      }

      return pathData;
    },
    true,
  );

  isRegistered = true;
};