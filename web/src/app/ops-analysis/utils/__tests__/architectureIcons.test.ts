import assert from 'node:assert/strict';
import test from 'node:test';
import {
  selectCmdbIsometricIcons,
  selectIsometricIsopackIcons,
} from '../architectureIcons';

test('architecture palette keeps only CMDB 2.5D realistic icons', () => {
  const selected = selectCmdbIsometricIcons([
    {
      key: 'cc-host',
      describe: '主机',
      source: 'icons-realistic',
      src: '/assets/icons-realistic/cc-host_主机.svg',
    },
    {
      key: 'mm-cisco',
      describe: 'cisco',
      source: 'icons',
      src: '/assets/icons/mm-cisco_cisco.svg',
    },
    {
      key: 'cc-host',
      describe: '主机平面',
      source: 'icons',
      src: '/assets/icons/cc-host_主机.svg',
    },
  ]);

  assert.deepEqual(selected, [
    {
      id: 'cmdb-cc-host',
      name: '主机',
      src: '/assets/icons-realistic/cc-host_主机.svg',
      isIsometric: true,
    },
  ]);
});

test('architecture palette drops non-isometric isopack picture icons', () => {
  const selected = selectIsometricIsopackIcons([
    {
      id: 'server',
      name: 'Server',
      url: 'data:image/svg+xml;base64,iso',
      isIsometric: true,
    },
    {
      id: 'aws-ec2',
      name: 'EC2',
      url: 'data:image/svg+xml;base64,aws',
      isIsometric: false,
    },
    {
      id: 'azure-vm',
      name: 'VM',
      url: 'data:image/svg+xml;base64,azure',
    },
  ]);

  assert.deepEqual(selected, [
    {
      id: 'server',
      name: 'Server',
      url: 'data:image/svg+xml;base64,iso',
      isIsometric: true,
    },
  ]);
});
