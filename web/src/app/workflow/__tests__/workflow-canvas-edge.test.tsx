import './test-mocks';

import type { PropsWithChildren } from 'react';
import { Position } from '@xyflow/react';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual<typeof import('@xyflow/react')>('@xyflow/react');
  return {
    ...actual,
    EdgeLabelRenderer: ({ children }: PropsWithChildren) => <>{children}</>,
  };
});

import { WorkflowCanvasEdge } from '../components/workflow-canvas-edge';

describe('WorkflowCanvasEdge 分支标签', () => {
  it('在边中点展示分支文案，且保持正向可读', () => {
    render(
      <WorkflowCanvasEdge
        id="e1"
        source="a"
        target="b"
        sourceX={100}
        sourceY={80}
        targetX={280}
        targetY={120}
        sourcePosition={Position.Right}
        targetPosition={Position.Left}
        selected={false}
        data={{ branchLabel: '满足' }}
      />,
    );

    const label = screen.getByText('满足');
    expect(label.getAttribute('class') || '').toContain('text-xs');
    expect(label.getAttribute('style') || '').toContain('translate(');
  });
});
