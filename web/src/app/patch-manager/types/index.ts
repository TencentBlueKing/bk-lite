// ── 枚举类型 ─────────────────────────────────────────────────────────────────

export type OSType = 'windows' | 'linux';
export type PatchType = 'security' | 'generic';
export type PatchSeverity = 'critical' | 'important' | 'moderate' | 'low' | 'unspecified';
export type PackageStatus = 'pending' | 'downloading' | 'ready' | 'download_failed';
export type ConnectivityStatus = 'unknown' | 'connected' | 'failed';
export type SSHCredentialType = 'password' | 'key';
export type WinRMScheme = 'http' | 'https';
export type WinRMTransport = 'basic' | 'ntlm' | 'kerberos' | 'credssp';
export type PatchSourceType = 'wsus' | 'yum_repo' | 'dnf_repo' | 'apt_repo';
export type PatchTargetSource = 'manual' | 'node_mgmt';
export type ComplianceStatus = 'compliant' | 'non_compliant' | 'pending' | 'evaluating' | 'failed' | 'unconfigured';

// ── 通知配置候选 ──────────────────────────────────────────────────────────────

export interface NoticeChannel {
  id: number;
  name: string;
  channel_type: string;
}

export interface NoticeUser {
  username: string;
  display_name?: string;
}

// ── 通用响应 ──────────────────────────────────────────────────────────────────

export interface ListResponse<T> {
  count: number;
  items: T[];
}

// ── 补丁源 ────────────────────────────────────────────────────────────────────

export interface PatchSource {
  id: number;
  name: string;
  source_type: PatchSourceType;
  source_type_display?: string;
  connectivity_status_display?: string;
  url: string;
  distro_name: string;
  os_version: string;
  arch: string;
  proxy_host: string;
  proxy_port: number | null;
  auth_user?: string;
  auth_password?: string;
  has_auth_password?: boolean;
  is_enabled: boolean;
  connectivity_status: ConnectivityStatus;
  last_checked_at: string | null;
  team: number[];
  created_at: string;
  updated_at: string;
}

export interface PatchSourceParams {
  page?: number;
  page_size?: number;
  source_type?: PatchSourceType;
  is_enabled?: boolean;
  team?: string;
  search?: string;
}

export interface ScanSetting {
  id: number;
  frequency: 'hourly' | 'daily' | 'weekly';
  hour_interval: number;
  weekday: number;
  time: string;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

// ── 补丁库 ────────────────────────────────────────────────────────────────────

export interface Patch {
  id: number;
  title: string;
  os_type: OSType;
  patch_type: PatchType;
  severity: PatchSeverity;
  cve_list: string[];
  pkg_status: PackageStatus;
  os_type_display?: string;
  patch_type_display?: string;
  severity_display?: string;
  pkg_status_display?: string;
  applicable_scope: Record<string, unknown>;
  windows_detail?: WindowsPatchDetail | null;
  linux_detail?: LinuxPatchDetail | null;
  sources: number[];
  source_type: PatchSourceType | null;
  released_at: string | null;
  last_synced_at: string | null;
  team: number[];
  created_at: string;
  updated_at: string;
  package_info?: {
    file_name: string;
    file_size: number;
    sha256: string;
    extension: '.msu' | '.cab';
  } | null;
}

export interface WindowsPatchDetail {
  kb_number: string;
  product_list: string[];
  architectures: string[];
  ms_bulletin: string;
}

export interface LinuxPatchDetail {
  pkg_name: string;
  pkg_version: string;
  distro_name: string;
  os_version_range: string;
  architectures: string[];
  repo_type: string;
}

export interface PatchParams {
  page?: number;
  page_size?: number;
  os_type?: OSType;
  patch_type?: PatchType;
  severity?: PatchSeverity;
  pkg_status?: PackageStatus;
  source_isnull?: boolean;
  team?: string;
  search?: string;
  name?: string;
  version?: string;
  arch?: string;
}

// ── 目标管理 ──────────────────────────────────────────────────────────────────

export interface PatchTarget {
  id: number;
  name: string;
  ip: string;
  os_type: OSType;
  source_type: PatchTargetSource;
  source_type_display?: string;
  node_id: string;
  cloud_region_id: number | null;
  ssh_port: number;
  ssh_user: string;
  ssh_credential_type: SSHCredentialType;
  ssh_password?: string;
  ssh_key_passphrase?: string;
  ssh_key_file?: string | null;
  has_ssh_password?: boolean;
  has_ssh_key?: boolean;
  ssh_key_file_name?: string;
  winrm_port: number;
  winrm_scheme: WinRMScheme;
  winrm_transport: WinRMTransport;
  winrm_user: string;
  winrm_password?: string;
  has_winrm_password?: boolean;
  connectivity_status: ConnectivityStatus;
  os_type_display?: string;
  connectivity_status_display?: string;
  baseline_name?: string | null;
  compliance_status?: ComplianceStatus;
  missing_count?: number;
  last_evaluated_at?: string | null;
  last_detected_at?: string | null;
  has_active_task?: boolean;
  has_pending_reboot?: boolean;
  arch?: string;
  team: number[];
  created_at: string;
  updated_at: string;
}

export interface PatchTargetParams {
  page?: number;
  page_size?: number;
  ip?: string;
  os_type?: OSType;
  team?: string;
  search?: string;
  compliance_status?: ComplianceStatus;
  baseline_id?: number;
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export interface DistributionItem {
  count: number;
  severity?: string;
  severity_display?: string;
  status?: string;
  status_display?: string;
}

export interface ComplianceDistributionItem {
  label: string;
  count: number;
  color: string;
  filter?: string;
}

export interface RecentTaskItem {
  id: number;
  name: string;
  status: string;
  status_color: string;
  progress: string;
  time: string;
  created_at: string | null;
}

export interface TopRiskItem {
  id: number;
  patch: string;
  hosts: number;
  sev: string;
  severity: PatchSeverity;
}

export interface PatchDashboardStats {
  high_severity_missing: number;
  affected_targets: number;
  pending_reboot_targets: number;
  failed_install_tasks: number;
  recent_scan_status: string | null;
  recent_scan_coverage: number | null;
  target_total?: number;
  patch_total?: number;
  compliance_rate?: number;
  coverage_rate?: number;
  non_compliant_hosts?: number;
  unconfigured_hosts?: number;
  pending_risk_count?: number;
  failed_tasks?: number;
  compliance_distribution?: ComplianceDistributionItem[];
  scan_tasks?: { total: number; running: number; pending: number; completed: number; failed: number };
  install_tasks?: { total: number; running: number; pending: number; success: number; failed: number };
  patch_severity_distribution?: DistributionItem[];
  scan_result_distribution?: DistributionItem[];
  recent_tasks?: RecentTaskItem[];
  top_risks?: TopRiskItem[];
}

export interface CandidateItem {
  key: string;
  name: string;
  title: string;
  version?: string;
  dist?: string;
  arch: string;
  added: boolean;
  severity?: string;
}

export interface IngestSyncResult {
  created: number;
  updated: number;
  skipped: number;
  total: number;
}

export interface IngestAsyncResult {
  accepted: true;
  task_id: string;
}

export type IngestResult = IngestSyncResult | IngestAsyncResult;
