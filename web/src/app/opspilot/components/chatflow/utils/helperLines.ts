import type { Node, NodePositionChange, XYPosition } from '@xyflow/react';

const SNAP_DISTANCE = 5;

interface NodeBounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
  centerX: number;
  centerY: number;
}

interface HelperLinesResult {
  horizontal?: number;
  vertical?: number;
  snapPosition: Partial<XYPosition>;
}

function getNodeBounds(node: Node, defaultWidth = 240, defaultHeight = 120): NodeBounds {
  const width = node.measured?.width ?? defaultWidth;
  const height = node.measured?.height ?? defaultHeight;
  
  return {
    left: node.position.x,
    right: node.position.x + width,
    top: node.position.y,
    bottom: node.position.y + height,
    centerX: node.position.x + width / 2,
    centerY: node.position.y + height / 2,
  };
}

export function getHelperLines(
  change: NodePositionChange,
  nodes: Node[],
  distance = SNAP_DISTANCE
): HelperLinesResult {
  const defaultResult: HelperLinesResult = {
    horizontal: undefined,
    vertical: undefined,
    snapPosition: { x: undefined, y: undefined },
  };

  const draggingNode = nodes.find((node) => node.id === change.id);
  if (!draggingNode || !change.position) {
    return defaultResult;
  }

  const draggingBounds = getNodeBounds({
    ...draggingNode,
    position: change.position,
  });

  let horizontalLine: number | undefined;
  let verticalLine: number | undefined;
  let snapX: number | undefined;
  let snapY: number | undefined;

  const otherNodes = nodes.filter((node) => node.id !== change.id);

  for (const node of otherNodes) {
    const bounds = getNodeBounds(node);

    if (horizontalLine === undefined) {
      if (Math.abs(draggingBounds.top - bounds.top) < distance) {
        horizontalLine = bounds.top;
        snapY = bounds.top;
      } else if (Math.abs(draggingBounds.bottom - bounds.bottom) < distance) {
        horizontalLine = bounds.bottom;
        snapY = bounds.bottom - (draggingBounds.bottom - draggingBounds.top);
      } else if (Math.abs(draggingBounds.centerY - bounds.centerY) < distance) {
        horizontalLine = bounds.centerY;
        snapY = bounds.centerY - (draggingBounds.bottom - draggingBounds.top) / 2;
      } else if (Math.abs(draggingBounds.top - bounds.bottom) < distance) {
        horizontalLine = bounds.bottom;
        snapY = bounds.bottom;
      } else if (Math.abs(draggingBounds.bottom - bounds.top) < distance) {
        horizontalLine = bounds.top;
        snapY = bounds.top - (draggingBounds.bottom - draggingBounds.top);
      }
    }

    if (verticalLine === undefined) {
      if (Math.abs(draggingBounds.left - bounds.left) < distance) {
        verticalLine = bounds.left;
        snapX = bounds.left;
      } else if (Math.abs(draggingBounds.right - bounds.right) < distance) {
        verticalLine = bounds.right;
        snapX = bounds.right - (draggingBounds.right - draggingBounds.left);
      } else if (Math.abs(draggingBounds.centerX - bounds.centerX) < distance) {
        verticalLine = bounds.centerX;
        snapX = bounds.centerX - (draggingBounds.right - draggingBounds.left) / 2;
      } else if (Math.abs(draggingBounds.left - bounds.right) < distance) {
        verticalLine = bounds.right;
        snapX = bounds.right;
      } else if (Math.abs(draggingBounds.right - bounds.left) < distance) {
        verticalLine = bounds.left;
        snapX = bounds.left - (draggingBounds.right - draggingBounds.left);
      }
    }

    if (horizontalLine !== undefined && verticalLine !== undefined) {
      break;
    }
  }

  return {
    horizontal: horizontalLine,
    vertical: verticalLine,
    snapPosition: { x: snapX, y: snapY },
  };
}
