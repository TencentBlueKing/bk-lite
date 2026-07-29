export interface CredentialPoolItem {
  credential_id?: string;
  _client_id?: string;
  username?: string;
  user?: string;
  password?: string;
  port?: number | string;
  database?: string;
  version?: string;
  level?: string;
  integrity?: string;
  privacy?: string;
  community?: string;
  authkey?: string;
  privkey?: string;
  snmp_port?: number | string;
  [key: string]: any;
}
