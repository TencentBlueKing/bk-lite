import { describe, expect, it } from 'vitest';

import {
  postgresFormFromName,
  postgresRoleLabel,
  visiblePostgresForm
} from '../architecture';

describe('postgres header form', () => {
  it('keeps standalone when recovery is present', () => {
    const nameForm = postgresFormFromName('k8s-pg-standalone-v15');
    expect(nameForm).toBe('单机');
    expect(visiblePostgresForm(nameForm, true, false)).toBe('单机');
    expect(visiblePostgresForm(postgresFormFromName('pg-single'), true, false)).toBe('单机');
    expect(postgresRoleLabel(0)).toBe('主库');
  });

  it('reads cluster from a ha name and does not treat shanghai as ha', () => {
    const nameForm = postgresFormFromName('k8s-pg-cluster-ha-v15');
    expect(nameForm).toBe('集群');
    expect(visiblePostgresForm(nameForm, true, false)).toBe('集群');
    expect(postgresFormFromName('db.shanghai.local')).toBeNull();
    expect(postgresFormFromName('Asia/Shanghai')).toBeNull();
  });

  it('uses recovery as 主从 only when the name does not name a form', () => {
    expect(visiblePostgresForm(null, true, false)).toBe('主从');
    expect(visiblePostgresForm(null, true, true)).toBeNull();
    expect(postgresRoleLabel(1)).toBe('备库');
    expect(postgresFormFromName('实例')).toBeNull();
  });
});
