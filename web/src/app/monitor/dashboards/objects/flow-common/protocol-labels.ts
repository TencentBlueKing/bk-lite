/** IANA IP protocol numbers commonly seen in NetFlow/sFlow metrics. */
const PROTOCOL_NUMBERS: Record<string, string> = {
  '0': 'HOPOPT',
  '1': 'ICMP',
  '2': 'IGMP',
  '4': 'IPv4',
  '6': 'TCP',
  '8': 'EGP',
  '17': 'UDP',
  '27': 'RDP',
  '41': 'IPv6',
  '47': 'GRE',
  '50': 'ESP',
  '51': 'AH',
  '58': 'ICMPv6',
  '88': 'EIGRP',
  '89': 'OSPF',
  '103': 'PIM',
  '115': 'L2TP',
  '118': 'STP',
  '132': 'SCTP',
  '136': 'UDPLite',
};

const normalizeProtocolToken = (value: string) => String(value || '').trim();

export const resolveProtocolName = (value: string): string => {
  const normalized = normalizeProtocolToken(value);
  if (!normalized) return '--';

  const byNumber = PROTOCOL_NUMBERS[normalized];
  if (byNumber) return byNumber;

  const upper = normalized.toUpperCase();
  if (/^[A-Z][A-Z0-9-]*$/.test(upper) && !/^\d+$/.test(normalized)) {
    return upper;
  }

  if (/^\d+$/.test(normalized)) {
    return `Proto-${normalized}`;
  }

  return upper;
};

/** Full label for tooltips / detail; keeps protocol number when mapped from IANA id. */
export const formatProtocolLabel = (value: string): string => {
  const normalized = normalizeProtocolToken(value);
  if (!normalized) return '--';

  const name = PROTOCOL_NUMBERS[normalized];
  if (name) return `${name} (${normalized})`;

  return resolveProtocolName(normalized);
};

/** Short name for badges and table cells. */
export const formatProtocolShortName = (value: string): string => {
  const label = formatProtocolLabel(value);
  return label.split(' ')[0] || label || '--';
};
