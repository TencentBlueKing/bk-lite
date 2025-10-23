import { useMemo } from 'react';
import { TableDataItem } from '@/app/log/types';
import { useFileConfig } from './collectTypes/file';
import { useExecConfig } from './collectTypes/exec';
import { useSyslogConfig } from './collectTypes/syslog';
import { useDockerConfig } from './collectTypes/docker';
import { useFilestreamConfig } from './collectTypes/filestream';
import { useAuditdConfig } from './collectTypes/auditd';
import { useSystemConfig } from './collectTypes/system';
import { useHttpConfig } from './collectTypes/http';
import { useDnsConfig } from './collectTypes/dns';
import { useFileIntegrityConfig } from './collectTypes/fileIntegrity';
import { useKubernetesConfig } from './collectTypes/kubernetes';
import { useIcmpConfig } from './collectTypes/icmp';
import { useDhcpConfig } from './collectTypes/dhcp';
import { useFlowsConfig } from './collectTypes/flows';

export const useCollectTypeConfig = () => {
  const fileConfig = useFileConfig();
  const execConfig = useExecConfig();
  const syslogConfig = useSyslogConfig();
  const dockerConfig = useDockerConfig();
  const filestreamConfig = useFilestreamConfig();
  const auditdConfig = useAuditdConfig();
  const systemConfig = useSystemConfig();
  const httpConfig = useHttpConfig();
  const dnsConfig = useDnsConfig();
  const fileIntegrityConfig = useFileIntegrityConfig();
  const kubernetesConfig = useKubernetesConfig();
  const icmpConfig = useIcmpConfig();
  const dhcpConfig = useDhcpConfig();
  const flowsConfig = useFlowsConfig();

  const configs: any = useMemo(
    () => ({
      file: fileConfig,
      exec: execConfig,
      syslog: syslogConfig,
      docker: dockerConfig,
      filestream: filestreamConfig,
      auditd: auditdConfig,
      system: systemConfig,
      http: httpConfig,
      file_integrity: fileIntegrityConfig,
      dns: dnsConfig,
      kubernetes: kubernetesConfig,
      icmp: icmpConfig,
      dhcp: dhcpConfig,
      flows: flowsConfig,
    }),
    []
  );

  // 获取指定插件的手动/自动/编辑配置模式
  const getCollectTypeConfig = (data: {
    mode: 'manual' | 'auto' | 'edit';
    type: string;
    collector: string;
    dataSource?: TableDataItem[];
    onTableDataChange?: (data: TableDataItem[]) => void;
  }) => {
    const collectTypeCfg =
      configs[data.type]?.plugins?.[data.collector]?.getConfig(data);
    const config = {
      collector: '',
      icon: '',
    };
    let defaultCollectTypeCfg: any = {
      getParams: () => ({
        instance_id: '',
        instance_name: '',
      }),
      getFormItems: () => null,
      configText: '',
    };
    if (data.mode === 'auto') {
      defaultCollectTypeCfg = {
        formItems: null,
        initTableItems: {},
        defaultForm: {},
        columns: [],
        getParams: () => ({}),
      };
    }
    return (
      collectTypeCfg || {
        ...config,
        ...defaultCollectTypeCfg,
      }
    );
  };

  return {
    configs,
    getCollectTypeConfig,
  };
};
