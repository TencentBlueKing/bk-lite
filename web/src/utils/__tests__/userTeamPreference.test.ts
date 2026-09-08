import Cookies from 'js-cookie';
import { afterEach, describe, expect, it } from 'vitest';

import {
  clearUserTeamPreference,
  CURRENT_TEAM_COOKIE,
  CURRENT_TEAM_OWNER_COOKIE,
  persistUserTeamPreference,
} from '@/utils/userTeamPreference';

afterEach(() => {
  Cookies.remove(CURRENT_TEAM_COOKIE);
  Cookies.remove(CURRENT_TEAM_OWNER_COOKIE);
  Cookies.remove('include_children');
});

describe('user team preference cookies', () => {
  it('persists the current team together with its owning account', () => {
    persistUserTeamPreference('2', 'kent');

    expect(Cookies.get(CURRENT_TEAM_COOKIE)).toBe('2');
    expect(Cookies.get(CURRENT_TEAM_OWNER_COOKIE)).toBe('kent');
  });

  it('clears only account-scoped team state during logout', () => {
    persistUserTeamPreference('2', 'kent');
    Cookies.set('include_children', '1');

    clearUserTeamPreference();

    expect(Cookies.get(CURRENT_TEAM_COOKIE)).toBeUndefined();
    expect(Cookies.get(CURRENT_TEAM_OWNER_COOKIE)).toBeUndefined();
    expect(Cookies.get('include_children')).toBe('1');
  });
});
