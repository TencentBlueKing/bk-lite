export const DEFAULT_K8S_IMAGE_REGISTRY_PREFIX =
  'bk-lite.tencentcloudcr.com/bklite';

const HOST_LABEL_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const IPV4_PATTERN = /^(?:\d{1,3}\.){3}\d{1,3}$/;
const REPOSITORY_COMPONENT_PATTERN = /^[a-z0-9]+(?:[._-][a-z0-9]+)*$/;

export const isValidK8sImageRegistryPrefix = (value: unknown): boolean => {
  if (typeof value !== 'string' || !value || value.length > 255) return false;
  if (value !== value.trim() || /\s|[\u0000-\u001f]/.test(value)) return false;
  if (value.includes('://') || value.endsWith('/')) return false;

  const [hostPort, ...repositoryComponents] = value.split('/');
  if (
    !repositoryComponents.length ||
    !repositoryComponents.every((component) =>
      REPOSITORY_COMPONENT_PATTERN.test(component)
    )
  ) {
    return false;
  }

  let host = hostPort;
  let port: string | undefined;
  if (hostPort.startsWith('[')) {
    const match = hostPort.match(/^\[([0-9a-fA-F:]+)](?::(\d{1,5}))?$/);
    if (!match || !match[1].includes(':')) return false;
    port = match[2];
  } else {
    if ((hostPort.match(/:/g) || []).length > 1) return false;
    [host, port] = hostPort.split(':');
    if (hostPort.includes(':') && !port) return false;
    if (IPV4_PATTERN.test(host)) {
      if (host.split('.').some((part) => Number(part) > 255)) return false;
    } else if (
      !host.split('.').every((label) => HOST_LABEL_PATTERN.test(label))
    ) {
      return false;
    }
  }

  return (
    !port ||
    (/^\d{1,5}$/.test(port) && Number(port) >= 1 && Number(port) <= 65535)
  );
};
