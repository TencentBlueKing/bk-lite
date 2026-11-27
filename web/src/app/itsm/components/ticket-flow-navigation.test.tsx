import React from 'react';
import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { TicketFlowBoard } from './ticket-flow-board';
const fitView = vi.hoisted(() => vi.fn());
vi.mock('@xyflow/react', () => ({
  ReactFlowProvider: ({children}: React.PropsWithChildren) => <>{children}</>,
  ReactFlow: ({children, fitViewOptions}: React.PropsWithChildren<{fitViewOptions: unknown}>) => <div data-testid="canvas" data-fit={JSON.stringify(fitViewOptions)}>{children}</div>,
  useReactFlow: () => ({fitView}), Background: () => null, Controls: () => null, MiniMap: () => null,
  Handle: () => null, Position: {Left:'left',Right:'right'},
}));
vi.mock('./ticket-collaboration', () => ({formatTicketTime:(x:string)=>x}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('已结束的长流程默认展示全图，定位当前节点不可用',()=>{
  const nodes=Array.from({length:20},(_,i)=>({id:String(i),name:`节点${i}`,type:'manual',state:'done' as const,assignees:[]}));
  render(<TicketFlowBoard nodes={nodes} edges={[]} />);fireEvent.click(screen.getByRole('button',{name:'流程图'}));
  const fit=JSON.parse(screen.getByTestId('canvas').getAttribute('data-fit')!);
  expect(fit.nodes).toBeUndefined();
  expect((screen.getByRole('button',{name:'定位当前节点'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'查看全图'}));expect(fitView).toHaveBeenCalledWith(expect.objectContaining(fit));
});
it('当前节点默认保持可读，并可重新定位',()=>{
  render(<TicketFlowBoard nodes={[{id:'a',name:'审批',type:'approval',state:'current',assignees:[]}]} edges={[]} />);
  fireEvent.click(screen.getByRole('button',{name:'流程图'}));
  fireEvent.click(screen.getByRole('button',{name:'定位当前节点'}));expect(fitView).toHaveBeenCalledWith(expect.objectContaining({nodes:[{id:'a'}],minZoom:.75}));
});
it('自动节点失败时，打开流程图定位到失败节点', () => {
  render(<TicketFlowBoard nodes={[
    { id: 'start', name: '开始', type: 'start', state: 'done' },
    { id: 'auto', name: '自动处理', type: 'auto', state: 'failed' },
  ]} edges={[{ from: 'start', to: 'auto' }]} />);
  fireEvent.click(screen.getByRole('button', { name: '流程图' }));
  const fit = JSON.parse(screen.getByTestId('canvas').getAttribute('data-fit')!);
  expect(fit.nodes).toEqual([{ id: 'auto' }]);
});
