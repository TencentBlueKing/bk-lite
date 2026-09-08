import { describe, expect, it } from 'vitest';

import {
  buildRedfishCredential,
  createRedfishCredential,
  restoreRedfishCredential,
} from '../redfishCredential';

describe('Redfish credential TLS verification', () => {
  it('defaults certificate verification to enabled', () => {
    expect(createRedfishCredential()).toEqual({
      username: '',
      password: '',
      port: 443,
      verify_tls: true,
    });
  });

  it('preserves explicitly disabled verification and password whitespace when submitting', () => {
    expect(buildRedfishCredential({
      username: ' Administrator ',
      password: ' secret ',
      port: '443',
      verify_tls: false,
    })).toEqual({
      username: 'Administrator',
      password: ' secret ',
      port: 443,
      verify_tls: false,
    });
  });

  it('treats an old task without the field as verification enabled', () => {
    expect(restoreRedfishCredential({
      username: 'Administrator',
      port: 443,
    }, false)).toMatchObject({
      verify_tls: true,
    });
  });
});
