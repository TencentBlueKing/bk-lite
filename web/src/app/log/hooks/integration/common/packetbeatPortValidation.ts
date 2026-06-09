const isValidPacketbeatPort = (port: unknown) => {
  const value = String(port).trim();
  if (!/^\d+$/.test(value)) return false;
  const portNumber = Number(value);
  return portNumber >= 1 && portNumber <= 65535;
};

const hasPacketbeatPorts = (ports: unknown) => {
  if (Array.isArray(ports)) return ports.length > 0;
  return Boolean(ports);
};

const arePacketbeatPortsValid = (ports: unknown) => {
  if (Array.isArray(ports)) return ports.every(isValidPacketbeatPort);
  if (typeof ports === 'string') {
    return ports
      .split(',')
      .map((port) => port.trim())
      .filter(Boolean)
      .every(isValidPacketbeatPort);
  }
  return false;
};

export {
  arePacketbeatPortsValid,
  hasPacketbeatPorts,
  isValidPacketbeatPort
};
