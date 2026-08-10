import { describe, expect, it } from 'vitest';
import { applyTableChangeHandler } from '../tableChangeHandler';

const nodeOptions = [
  {
    value: 'node-1',
    name: 'fusion-collector',
    label: 'fusion-collector (10.42.4.103)',
    ip: '10.42.4.103',
  },
];

describe('applyTableChangeHandler process instance name', () => {
  it('combines node label then process name into instance_name', () => {
    const afterNode = applyTableChangeHandler(
      { process_name: '' },
      'node-1',
      nodeOptions,
      {
        type: 'option_then_combine',
        source_field: 'label',
        stash_field: 'node_label',
        source_fields: ['process_name', 'node_label'],
        separator: '-',
        target_field: 'instance_name',
      }
    );
    expect(afterNode.node_label).toBe('fusion-collector (10.42.4.103)');
    expect(afterNode.instance_name).toBe('fusion-collector (10.42.4.103)');

    const afterProcess = applyTableChangeHandler(
      { ...afterNode, process_name: 'nginx' },
      'nginx',
      [],
      {
        type: 'combine',
        source_fields: ['process_name', 'node_label'],
        separator: '-',
        target_field: 'instance_name',
      }
    );
    expect(afterProcess.instance_name).toBe(
      'nginx-fusion-collector (10.42.4.103)'
    );
  });

  it('combines process name then node label into instance_name', () => {
    const afterProcess = applyTableChangeHandler(
      { process_name: 'nginx' },
      'nginx',
      [],
      {
        type: 'combine',
        source_fields: ['process_name', 'node_label'],
        separator: '-',
        target_field: 'instance_name',
      }
    );
    expect(afterProcess.instance_name).toBe('nginx');

    const afterNode = applyTableChangeHandler(
      afterProcess,
      'node-1',
      nodeOptions,
      {
        type: 'option_then_combine',
        source_field: 'label',
        stash_field: 'node_label',
        source_fields: ['process_name', 'node_label'],
        separator: '-',
        target_field: 'instance_name',
      }
    );
    expect(afterNode.instance_name).toBe(
      'nginx-fusion-collector (10.42.4.103)'
    );
  });

  it('skips empty combine segments without extra separators', () => {
    const onlyHost = applyTableChangeHandler(
      { host: 'db.example.com', port: '' },
      '',
      [],
      {
        type: 'combine',
        source_fields: ['host', 'port'],
        separator: ':',
        target_field: 'instance_name',
      }
    );
    expect(onlyHost.instance_name).toBe('db.example.com');
  });
});
