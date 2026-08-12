export type ProxyForwardingMode = 'strip' | 'trusted_upstream' | 'legacy';

export function buildProxyRequestHeaders(
  source: Headers,
  forwardedHost: string,
  forwardedProto: string,
  configuredMode = process.env.OTP_WEB_XFF_MODE,
): Headers {
  const headers = new Headers(source);
  const mode = (configuredMode || 'strip').trim().toLowerCase() as ProxyForwardingMode;

  headers.set('X-Forwarded-Host', forwardedHost);
  headers.set('X-Forwarded-Proto', forwardedProto);
  if (mode !== 'trusted_upstream' && mode !== 'legacy') {
    headers.delete('X-Forwarded-For');
  }
  return headers;
}
