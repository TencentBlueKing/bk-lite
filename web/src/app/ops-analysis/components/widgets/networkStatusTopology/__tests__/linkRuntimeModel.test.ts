import { describe, expect, it } from 'vitest';
import {
  applyLinkRuntime,
  buildInterfaceNameCandidates,
  matchIfDescr,
  mapOperStatus,
  normalizeLinkTrafficDisplays,
  pickBandwidth,
  pickTrafficValue,
  formatByteRate,
  resolveLinkConnectStatus,
  resolveTrafficLineFill,
  buildPortTrafficLines,
} from '../linkRuntimeModel';

describe('normalizeLinkTrafficDisplays', () => {
  it('defaults to both when the field is missing', () => {
    expect(normalizeLinkTrafficDisplays(undefined)).toEqual(['inbound', 'outbound']);
  });

  it('keeps an empty selection when the user cleared both', () => {
    expect(normalizeLinkTrafficDisplays([])).toEqual([]);
  });

  it('drops unknown keys', () => {
    expect(normalizeLinkTrafficDisplays(['inbound', 'custom'])).toEqual(['inbound']);
  });
});

describe('interface name matching', () => {
  it('matches abbreviated CMDB names to full ifDescr', () => {
    expect(buildInterfaceNameCandidates('Gi0/1').has('gigabitethernet0/1')).toBe(true);
    expect(matchIfDescr('Gi0/1', ['GigabitEthernet0/1', 'Gi0/2'])).toBe(
      'GigabitEthernet0/1',
    );
  });

  it('matches when names are already the same', () => {
    expect(matchIfDescr('GigabitEthernet0/1', ['GigabitEthernet0/1'])).toBe(
      'GigabitEthernet0/1',
    );
  });

  it('returns undefined when nothing matches', () => {
    expect(matchIfDescr('Gi0/1', ['Eth1/1'])).toBeUndefined();
  });
});

describe('oper status and link aggregation', () => {
  it('treats 1 as up, 2 and 7 as down, others unknown', () => {
    expect(mapOperStatus(1)).toBe('up');
    expect(mapOperStatus(2)).toBe('down');
    expect(mapOperStatus(7)).toBe('down');
    expect(mapOperStatus(3)).toBe('unknown');
    expect(mapOperStatus(undefined)).toBe('unknown');
  });

  it('marks the link down when either end is down', () => {
    expect(resolveLinkConnectStatus('up', 'down')).toBe('down');
    expect(resolveLinkConnectStatus('down', 'unknown')).toBe('down');
    expect(resolveLinkConnectStatus('up', 'up')).toBe('up');
    expect(resolveLinkConnectStatus('up', 'unknown')).toBe('unknown');
  });
});

describe('metric fallbacks', () => {
  it('prefers HC traffic and HighSpeed bandwidth', () => {
    expect(
      pickTrafficValue(
        { interface_ifHCInOctets: 10, interface_ifInOctets: 1 },
        'in',
      ),
    ).toBe(10);
    expect(pickTrafficValue({ interface_ifOutOctets: 3 }, 'out')).toBe(3);
    expect(
      pickBandwidth({ interface_ifHighSpeed: 1000, interface_ifSpeed: 100 }),
    ).toEqual({ mbps: 1000 });
    expect(pickBandwidth({ interface_ifSpeed: 100 })).toEqual({ bps: 100 });
    expect(formatByteRate(1024)).toBe('1 KiB/s');
    expect(formatByteRate(8)).toBe('8 B/s');
  });
});

describe('traffic threshold colors', () => {
  const thresholds = [
    { value: '1024', color: '#dc2626' },
    { value: '0', color: '#2563eb' },
  ];

  it('keeps the default fill when no thresholds are configured', () => {
    expect(resolveTrafficLineFill(4096, [], '#60758d')).toBe('#60758d');
    expect(resolveTrafficLineFill(4096, undefined, '#60758d')).toBe('#60758d');
  });

  it('uses the first threshold the value is greater than or equal to', () => {
    expect(resolveTrafficLineFill(1024, thresholds, '#60758d')).toBe('#dc2626');
    expect(resolveTrafficLineFill(8, thresholds, '#60758d')).toBe('#2563eb');
  });

  it('attaches fills onto inbound and outbound lines', () => {
    expect(
      buildPortTrafficLines(
        {
          portName: 'Gi0/1',
          matchReason: 'ok',
          operKind: 'up',
          inbound: 2048,
          outbound: 8,
        },
        ['inbound', 'outbound'],
        {
          inboundThresholds: thresholds,
          outboundThresholds: thresholds,
          defaultFill: '#60758d',
        },
      ),
    ).toEqual([
      { text: '↓ 2 KiB/s', fill: '#dc2626' },
      { text: '↑ 8 B/s', fill: '#2563eb' },
    ]);
  });
});

describe('applyLinkRuntime', () => {
  const nodes = [
    { id: 'a', model_id: 'switch', name: 'A', hop: 0, monitor_id: 'mon-a' },
    { id: 'b', model_id: 'switch', name: 'B', hop: 1, monitor_id: 'mon-b' },
  ];
  const links = [
    {
      id: 'l1',
      source: 'a',
      target: 'b',
      sourcePort: 'Gi0/1',
      targetPort: 'Gi0/2',
    },
  ];

  it('matches ports and paints a down link when one oper status is down', () => {
    const [link] = applyLinkRuntime({
      links,
      nodes,
      items: [
        {
          instance_id: 'mon-a',
          ifDescr: 'GigabitEthernet0/1',
          metrics: { interface_ifOperStatus: 1, interface_ifHCInOctets: 8 },
        },
        {
          instance_id: 'mon-b',
          ifDescr: 'GigabitEthernet0/2',
          metrics: { interface_ifOperStatus: 2 },
        },
      ],
    });
    expect(link.runtime.status).toBe('down');
    expect(link.runtime.source.matchReason).toBe('ok');
    expect(link.runtime.source.inbound).toBe(8);
    expect(link.runtime.target.operKind).toBe('down');
  });

  it('does not mark unmatched or unmonitored ports as down', () => {
    const [unmatched] = applyLinkRuntime({
      links,
      nodes,
      items: [
        {
          instance_id: 'mon-a',
          ifDescr: 'Eth1/1',
          metrics: { interface_ifOperStatus: 2 },
        },
      ],
    });
    expect(unmatched.runtime.status).toBe('unknown');
    expect(unmatched.runtime.source.matchReason).toBe('unmatched');

    const [unmonitored] = applyLinkRuntime({
      links,
      nodes: nodes.map((node) => ({ ...node, monitor_id: '' })),
      items: [],
    });
    expect(unmonitored.runtime.source.matchReason).toBe('unmonitored');
    expect(unmonitored.runtime.status).toBe('unknown');
  });

  it('keeps links unknown when the interface query failed', () => {
    const [link] = applyLinkRuntime({
      links,
      nodes,
      items: [],
      queryFailed: true,
    });
    expect(link.runtime.status).toBe('unknown');
    expect(link.runtime.source.matchReason).toBe('query_failed');
  });

  it('falls back to source_inst_name when source_port is missing', () => {
    const [link] = applyLinkRuntime({
      links: [{
        id: 'l1',
        source: 'a',
        target: 'b',
        source_inst_name: 'Gi0/1',
        target_inst_name: 'Gi0/2',
      }],
      nodes,
      items: [{
        instance_id: 'mon-a',
        ifDescr: 'GigabitEthernet0/1',
        metrics: { interface_ifOperStatus: 1, interface_ifHCInOctets: 4 },
      }],
    });
    expect(link.runtime.source.matchReason).toBe('ok');
    expect(link.runtime.source.inbound).toBe(4);
  });
});
