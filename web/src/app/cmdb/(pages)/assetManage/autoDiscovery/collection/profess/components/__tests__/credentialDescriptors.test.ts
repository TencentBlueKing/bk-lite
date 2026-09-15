import { describe, expect, it } from 'vitest';

import { getCredentialDescriptor } from '../credentialDescriptors';


describe('network config file credential descriptors', () => {
  it('declares SSH/Telnet protocol and default ports', () => {
    const descriptor = getCredentialDescriptor({
      model_id: 'network_config_file',
    });

    expect(descriptor?.formKind).toBe('network_config_file');
    expect(descriptor?.protocolKey).toBe('sshOrTelnet');
    expect(descriptor?.defaultPort).toBe(22);
    expect(descriptor?.defaultPortLabel).toBe('SSH 22 / Telnet 23');
    expect(descriptor?.fields.map((field) => field.key)).toContain('transportProtocol');
  });
});

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
