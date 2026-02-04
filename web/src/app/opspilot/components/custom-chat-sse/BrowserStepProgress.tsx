'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Progress, Image } from 'antd';
import { RightOutlined, CheckCircleFilled, LoadingOutlined, EyeOutlined } from '@ant-design/icons';
import { BrowserStepProgressData, BrowserStepAction, BrowserStepsHistory } from '@/app/opspilot/types/global';

interface BrowserStepProgressProps {
  history: BrowserStepsHistory;
}

const getActionIcon = (action: BrowserStepAction): string => {
  if (action.navigate) return '🌐';
  if (action.wait) return '⏳';
  if (action.input) return '⌨️';
  if (action.click) return '🖱️';
  if (action.scroll) return '📜';
  if (action.screenshot) return '📸';
  return '⚡';
};

const getActionText = (action: BrowserStepAction): string => {
  if (action.navigate) {
    const url = action.navigate.url;
    const displayUrl = url.length > 40 ? url.substring(0, 40) + '...' : url;
    return `Navigate to ${displayUrl}${action.navigate.new_tab ? ' (new tab)' : ''}`;
  }
  if (action.wait) return `Wait ${action.wait.seconds}s`;
  if (action.input) {
    const text = action.input.text.length > 20 ? action.input.text.substring(0, 20) + '...' : action.input.text;
    return `Input "${text}" at element #${action.input.index}`;
  }
  if (action.click) return `Click element #${action.click.index}`;
  if (action.scroll) return `Scroll ${action.scroll.direction || 'down'}`;
  if (action.screenshot) return 'Take screenshot';
  return 'Execute action';
};

const getActionSummary = (actions: BrowserStepAction[]): string => {
  if (!actions || actions.length === 0) return 'Execute action';
  const firstAction = actions[0];
  const actionType = Object.keys(firstAction).find(k => k !== 'undefined' && firstAction[k as keyof BrowserStepAction]);
  const suffix = actions.length > 1 ? ` +${actions.length - 1}` : '';
  return `${getActionIcon(firstAction)} ${actionType || 'action'}${suffix}`;
};

const ThinkingDots: React.FC = () => (
  <span className="inline-flex items-center gap-1 ml-2">
    <span className="w-1.5 h-1.5 bg-[#1677ff] rounded-full animate-[thinking-dot_1.4s_ease-in-out_infinite_both]" style={{ animationDelay: '-0.32s' }} />
    <span className="w-1.5 h-1.5 bg-[#1677ff] rounded-full animate-[thinking-dot_1.4s_ease-in-out_infinite_both]" style={{ animationDelay: '-0.16s' }} />
    <span className="w-1.5 h-1.5 bg-[#1677ff] rounded-full animate-[thinking-dot_1.4s_ease-in-out_infinite_both]" />
  </span>
);

interface StepDetailProps {
  data: BrowserStepProgressData;
  isExpanded: boolean;
}

const StepDetail: React.FC<StepDetailProps> = ({ data, isExpanded }) => {
  if (!isExpanded) return null;
  
  return (
    <div className="px-3 pb-3 space-y-2 text-sm">
      <div className="p-2 bg-[var(--color-fill-2)] rounded-lg">
        <div className="flex items-center gap-1.5 text-[var(--color-text-3)] text-xs mb-1">
          <span>📄</span>
          <span>Page</span>
        </div>
        <div className="font-medium text-[var(--color-text-1)] break-all">
          {data.title || 'Loading...'}
        </div>
        <div className="text-xs text-[var(--color-text-3)] break-all mt-0.5">
          {data.url}
        </div>
      </div>
      
      {data.thinking && (
        <div>
          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)] mb-1">
            <span>💭</span>
            <span>Thinking</span>
          </div>
          <div className="text-[var(--color-text-1)] pl-4 break-words">
            {data.thinking}
          </div>
        </div>
      )}
      
      {data.memory && (
        <div>
          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)] mb-1">
            <span>📝</span>
            <span>Memory</span>
          </div>
          <div className="text-xs text-[var(--color-text-3)] pl-4 break-words">
            {data.memory}
          </div>
        </div>
      )}
      
      {data.next_goal && (
        <div>
          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)] mb-1">
            <span>🎯</span>
            <span>Next Goal</span>
          </div>
          <div className="text-[#1677ff] pl-4 break-words">
            {data.next_goal}
          </div>
        </div>
      )}
      
      {data.actions && data.actions.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)] mb-1">
            <span>⚡</span>
            <span>Actions</span>
          </div>
          <div className="flex flex-col gap-1 pl-4">
            {data.actions.map((action, index) => (
              <div 
                key={index}
                className="flex items-center gap-2 px-2 py-1 bg-[var(--color-fill-2)] rounded text-xs"
              >
                <span>{getActionIcon(action)}</span>
                <span className="text-[var(--color-text-2)] break-all">{getActionText(action)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {data.evaluation && (
        <div className="p-2 bg-[rgba(82,196,26,0.1)] rounded-lg border-l-2 border-[#52c41a]">
          <div className="flex items-center gap-1.5 text-xs text-[#52c41a] mb-1">
            <span>✅</span>
            <span>Evaluation</span>
          </div>
          <div className="text-xs text-[var(--color-text-2)] pl-4 break-words">
            {data.evaluation}
          </div>
        </div>
      )}
      
      {data.screenshot && (
        <div onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-3)] mb-1">
            <span>📸</span>
            <span>Screenshot</span>
          </div>
          <div className="pl-4">
            <Image 
              src={data.screenshot.startsWith('data:') ? data.screenshot : `data:image/png;base64,${data.screenshot}`}
              alt={`Step ${data.step_number} screenshot`}
              width={200}
              preview={{
                getContainer: () => document.body,
                mask: <span className="flex items-center gap-1"><EyeOutlined /> Preview</span>,
                zIndex: 9999
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

const BrowserStepProgress: React.FC<BrowserStepProgressProps> = ({ history }) => {
  const { steps, isRunning } = history;
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  
  const currentStepNumber = steps.length > 0 ? steps[steps.length - 1].step_number : 0;
  const totalSteps = steps.length;
  const progressPercent = isRunning ? 90 : 100;
  
  useEffect(() => {
    if (steps.length > 0) {
      setExpandedSteps(new Set([steps[steps.length - 1].step_number]));
    }
  }, [currentStepNumber]);
  
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [steps.length, currentStepNumber]);
  
  const toggleStep = (stepNumber: number) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(stepNumber)) {
        next.delete(stepNumber);
      } else {
        next.add(stepNumber);
      }
      return next;
    });
  };
  
  const expandAll = () => {
    setExpandedSteps(new Set(steps.map(s => s.step_number)));
  };
  
  const collapseAll = () => {
    setExpandedSteps(new Set());
  };

  return (
    <div className="browser-step-progress rounded-xl p-4 my-2 bg-[var(--color-fill-1)] max-w-full overflow-hidden">
      <style jsx>{`
        @keyframes thinking-dot {
          0%, 80%, 100% { transform: scale(0); opacity: 0.5; }
          40% { transform: scale(1); opacity: 1; }
        }
      `}</style>
      
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🤖</span>
          <span className="font-semibold text-sm text-[var(--color-text-1)]">Browser Automation</span>
          {isRunning && <ThinkingDots />}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[rgba(22,119,255,0.08)] rounded-xl">
            {isRunning ? (
              <LoadingOutlined className="text-[#1677ff] text-xs" spin />
            ) : (
              <CheckCircleFilled className="text-[#52c41a] text-xs" />
            )}
            <span className="text-xs font-medium text-[#1677ff]">
              Step {currentStepNumber}/{totalSteps}
            </span>
          </div>
        </div>
      </div>
      
      <Progress 
        percent={progressPercent} 
        showInfo={false}
        strokeColor={isRunning ? { from: '#1677ff', to: '#1677ff' } : { from: '#52c41a', to: '#52c41a' }}
        className="mb-3"
        size="small"
      />
      
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[var(--color-text-3)]">
          {steps.length} step{steps.length !== 1 ? 's' : ''} recorded
        </span>
        <div className="flex gap-2">
          <button 
            onClick={expandAll}
            className="text-xs text-[#1677ff] hover:text-[#4096ff] cursor-pointer bg-transparent border-none"
          >
            Expand All
          </button>
          <span className="text-[var(--color-text-4)]">|</span>
          <button 
            onClick={collapseAll}
            className="text-xs text-[#1677ff] hover:text-[#4096ff] cursor-pointer bg-transparent border-none"
          >
            Collapse All
          </button>
        </div>
      </div>
      
      <div ref={scrollContainerRef} className="max-h-[400px] overflow-y-auto pr-1">
        <div className="relative pl-4">
          <div className="absolute left-[7px] top-0 bottom-0 w-0.5 bg-[var(--color-border-1)]" />
          
          {steps.map((step, index) => {
            const isLast = index === steps.length - 1;
            const isExpanded = expandedSteps.has(step.step_number);
            const isCurrent = isLast && isRunning;
            
            return (
              <div key={step.step_number} className="relative pb-3 last:pb-0">
                <div 
                  className={`absolute left-[-12px] w-4 h-4 rounded-full flex items-center justify-center z-10
                    ${isCurrent 
                    ? 'bg-[#1677ff] ring-2 ring-[rgba(22,119,255,0.2)]' 
                    : isLast && !isRunning 
                      ? 'bg-[#52c41a]' 
                      : 'bg-[var(--color-fill-3)] border border-[var(--color-border-1)]'
                    }`}
                >
                  {isCurrent ? (
                    <LoadingOutlined className="text-white text-[10px]" spin />
                  ) : (
                    <span className={`text-[10px] font-medium ${isLast && !isRunning ? 'text-white' : 'text-[var(--color-text-2)]'}`}>
                      {step.step_number}
                    </span>
                  )}
                </div>
                
                <div 
                  className={`ml-4 rounded-lg border cursor-pointer transition-all duration-200
                    ${isCurrent 
                    ? 'border-[#1677ff] bg-[rgba(22,119,255,0.04)]' 
                    : 'border-[var(--color-border-1)] hover:border-[var(--color-border-2)] bg-[var(--color-fill-1)]'
                    }`}
                  onClick={() => toggleStep(step.step_number)}
                >
                  <div className="flex items-center justify-between p-2">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span className={`text-xs transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`}>
                        <RightOutlined className="text-[var(--color-text-3)]" />
                      </span>
                      <span className="text-xs font-medium text-[var(--color-text-1)]">
                        Step {step.step_number}
                      </span>
                      <span className="text-xs text-[var(--color-text-3)] truncate">
                        {getActionSummary(step.actions)}
                      </span>
                    </div>
                    {isCurrent && (
                      <span className="text-xs text-[#1677ff] font-medium shrink-0 ml-2">Running</span>
                    )}
                  </div>
                  
                  <StepDetail data={step} isExpanded={isExpanded} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
      
      {isRunning && (
        <div className="flex items-center justify-center mt-3 pt-3 border-t border-[var(--color-border-2)]">
          <span className="text-xs text-[var(--color-text-3)]">Processing</span>
          <ThinkingDots />
        </div>
      )}
    </div>
  );
};

export default BrowserStepProgress;
