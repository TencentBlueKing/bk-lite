import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { AgentStepProgressData } from '@/app/opspilot/types/global';

interface AgentStepProgressProps {
  steps: AgentStepProgressData[];
}

const AgentStepProgress: React.FC<AgentStepProgressProps> = ({ steps }) => {
  const { t } = useTranslation();
  
  if (!steps || steps.length === 0) return null;
  
  // Group by agent_name
  const agentGroups = new Map<string, AgentStepProgressData[]>();
  steps.forEach(step => {
    const key = step.agent_name || 'main';
    if (!agentGroups.has(key)) agentGroups.set(key, []);
    agentGroups.get(key)!.push(step);
  });
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'started': case 'running': case 'parallel_started': return 'var(--color-primary)';
      case 'completed': case 'parallel_completed': return 'var(--color-success, #52c41a)';
      case 'error': return 'var(--color-error)';
      default: return 'var(--color-text-3)';
    }
  };
  
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'started': case 'running': case 'parallel_started': return '⏳';
      case 'completed': case 'parallel_completed': return '✓';
      case 'error': return '✕';
      default: return '·';
    }
  };
  
  return (
    <div className="my-1.5 ml-1 space-y-1 border-l-2 border-[var(--color-fill-3)] pl-3 text-xs">
      {Array.from(agentGroups.entries()).map(([agentName, agentSteps]) => {
        const latestStep = agentSteps[agentSteps.length - 1];
        const isActive = ['started', 'running', 'parallel_started'].includes(latestStep.status);
        
        return (
          <div key={agentName} className={`flex items-center gap-2 py-0.5 ${isActive ? 'opacity-100' : 'opacity-80'}`}>
            <span className="text-[11px] font-mono">{getStatusIcon(latestStep.status)}</span>
            <span style={{ 
              fontWeight: 500, 
              color: getStatusColor(latestStep.status),
              minWidth: '70px',
            }}>
              {agentName === 'main' ? t('chatflow.mainAgent') : agentName}
            </span>
            {latestStep.max_steps > 0 && (
              <span className="text-[var(--color-text-4)] font-mono">
                {t('chatflow.stepProgress', '', { current: latestStep.step, total: latestStep.max_steps })}
              </span>
            )}
            <span className="text-[var(--color-text-3)] flex-1 truncate">
              {latestStep.description || latestStep.tool_name || ''}
            </span>
            {latestStep.total_elapsed_seconds != null && latestStep.total_elapsed_seconds > 0 && (
              <span className="text-[var(--color-text-4)] font-mono text-[11px]">
                {latestStep.total_elapsed_seconds.toFixed(1)}s
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default AgentStepProgress;