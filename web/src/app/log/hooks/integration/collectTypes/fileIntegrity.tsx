import { useAuditbeatConfig } from '../collectors/auditbeat/fileIntegrity';

export const useFileIntegrityConfig = () => {
  const auditbeat = useAuditbeatConfig();
  const plugins = {
    Auditbeat: auditbeat,
  };

  return {
    type: 'file_integrity',
    plugins,
  };
};
