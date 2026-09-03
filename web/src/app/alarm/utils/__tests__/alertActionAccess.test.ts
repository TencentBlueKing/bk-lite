import { describe, expect, it } from 'vitest';
import {
  alarmActionsForStatus,
  canReassignAlert,
} from '../alertActionAccess';

describe('canReassignAlert', () => {
  it('lets a platform superuser reassign a pending alert', () => {
    expect(
      canReassignAlert(
        { status: 'pending', operator: ['alice'] },
        { username: 'admin', isSuperUser: true }
      )
    ).toBe(true);
  });

  it('blocks a normal user from reassigning a pending alert', () => {
    expect(
      canReassignAlert(
        { status: 'pending', operator: ['alice'] },
        { username: 'admin', isSuperUser: false }
      )
    ).toBe(false);
  });

  it('lets only the current assignee reassign a processing alert', () => {
    const alert = { status: 'processing', operator: ['alice'] };
    expect(canReassignAlert(alert, { username: 'alice', isSuperUser: true })).toBe(true);
    expect(canReassignAlert(alert, { username: 'admin', isSuperUser: true })).toBe(false);
  });

  it('never allows reassign on unassigned alerts', () => {
    expect(
      canReassignAlert({ status: 'unassigned' }, { username: 'admin', isSuperUser: true })
    ).toBe(false);
  });
});

describe('alarmActionsForStatus', () => {
  it('shows reassign on pending only for superusers', () => {
    expect(alarmActionsForStatus('pending', { isSuperUser: true })).toEqual([
      'acknowledge',
      'reassign',
    ]);
    expect(alarmActionsForStatus('pending', { isSuperUser: false })).toEqual(['acknowledge']);
  });

  it('never exposes close on pending, even for a superuser', () => {
    expect(alarmActionsForStatus('pending', { isSuperUser: true })).not.toContain('close');
  });
});
