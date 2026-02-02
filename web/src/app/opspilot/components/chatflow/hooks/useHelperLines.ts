import { useState, useCallback } from 'react';
import type { NodeChange, Node, NodePositionChange } from '@xyflow/react';
import { applyNodeChanges } from '@xyflow/react';
import { getHelperLines } from '../utils/helperLines';

interface HelperLinesState {
  horizontal?: number;
  vertical?: number;
}

interface UseHelperLinesReturn {
  helperLines: HelperLinesState;
  applyHelperLines: (changes: NodeChange[], nodes: Node[]) => Node[];
  clearHelperLines: () => void;
}

export const useHelperLines = (): UseHelperLinesReturn => {
  const [helperLines, setHelperLines] = useState<HelperLinesState>({
    horizontal: undefined,
    vertical: undefined,
  });

  const clearHelperLines = useCallback(() => {
    setHelperLines({ horizontal: undefined, vertical: undefined });
  }, []);

  const applyHelperLines = useCallback((changes: NodeChange[], nodes: Node[]): Node[] => {
    const positionChange = changes.find(
      (change): change is NodePositionChange =>
        change.type === 'position' && change.dragging === true
    );

    if (!positionChange) {
      if (changes.some((c) => c.type === 'position' && (c as NodePositionChange).dragging === false)) {
        clearHelperLines();
      }
      return applyNodeChanges(changes, nodes);
    }

    const { horizontal, vertical, snapPosition } = getHelperLines(positionChange, nodes);

    setHelperLines({ horizontal, vertical });

    const snappedChanges = changes.map((change) => {
      if (change.type === 'position' && change.id === positionChange.id && change.position) {
        return {
          ...change,
          position: {
            x: snapPosition.x ?? change.position.x,
            y: snapPosition.y ?? change.position.y,
          },
        };
      }
      return change;
    });

    return applyNodeChanges(snappedChanges, nodes);
  }, [clearHelperLines]);

  return {
    helperLines,
    applyHelperLines,
    clearHelperLines,
  };
};
