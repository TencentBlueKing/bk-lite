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
      case 'started': case 'running': case 'parallel_started': return '#1890ff';
      case 'completed': case 'parallel_completed': return '#52c41a';
      case 'error': return '#ff4d4f';
      default: return '#8c8c8c';
    }
  };
  
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'started': case 'running': case 'parallel_started': return '⏳';
      case 'completed': case 'parallel_completed': return '✅';
      case 'error': return '❌';
      default: return '⚙️';
    }
  };
  
  return (
    <div style={{ 
      margin: '8px 0', 
      padding: '8px 12px', 
      background: '#f6f8fa', 
      borderRadius: '6px',
      fontSize: '13px',
      lineHeight: '1.6'
    }}>
      {Array.from(agentGroups.entries()).map(([agentName, agentSteps]) => {
        const latestStep = agentSteps[agentSteps.length - 1];
        const isActive = ['started', 'running', 'parallel_started'].includes(latestStep.status);
        
        return (
          <div key={agentName} style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '8px',
            padding: '2px 0',
            opacity: isActive ? 1 : 0.7,
          }}>
            <span>{getStatusIcon(latestStep.status)}</span>
            <span style={{ 
              fontWeight: 500, 
              color: getStatusColor(latestStep.status),
              minWidth: '80px',
            }}>
              {agentName === 'main' ? t('chatflow.mainAgent') : agentName}
            </span>
            {latestStep.max_steps > 0 && (
              <span style={{ color: '#8c8c8c' }}>
                {t('chatflow.stepProgress', '', { current: latestStep.step, total: latestStep.max_steps })}
              </span>
            )}
            <span style={{ color: '#595959', flex: 1 }}>
              {latestStep.description || latestStep.tool_name || ''}
            </span>
            {latestStep.total_elapsed_seconds != null && latestStep.total_elapsed_seconds > 0 && (
              <span style={{ color: '#8c8c8c', fontSize: '12px' }}>
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