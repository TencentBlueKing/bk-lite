import { useAuditbeatConfig } from '../collectors/auditbeat/auditd';

export const useAuditdConfig = () => {
  const auditbeat = useAuditbeatConfig();
  const plugins = {
    Auditbeat: auditbeat,
  };

  return {
    type: 'auditd',
    plugins,
  };
};
