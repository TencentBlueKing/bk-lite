import { describe, expect, it } from 'vitest';

import { getCredentialDescriptor } from '../credentialDescriptors';


describe('physical server credential descriptors', () => {
  it('uses the explicit Redfish protocol instead of the legacy IPMI model default', () => {
    const descriptor = getCredentialDescriptor({
      model_id: 'physcial_server',
      type: 'protocol',
      credential_protocol: 'redfish',
      credential_default_port: 443,
    });

    expect(descriptor?.formKind).toBe('redfish');
    expect(descriptor?.protocolKey).toBe('redfish');
    expect(descriptor?.defaultPort).toBe(443);
  });

  it('keeps historical protocol tasks on the IPMI descriptor', () => {
    const descriptor = getCredentialDescriptor({
      model_id: 'physcial_server',
      type: 'protocol',
    });

    expect(descriptor?.formKind).toBe('ipmi');
    expect(descriptor?.defaultPort).toBe(623);
  });
});
