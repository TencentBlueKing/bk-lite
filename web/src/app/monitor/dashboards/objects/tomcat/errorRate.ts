export const TOMCAT_ERROR_RATE_MIN_REQUEST_RATE = 1e-6;

export function tomcatErrorRatePct(errorRate: number, requestRate: number): number {
  return (100 * errorRate) / Math.max(requestRate, TOMCAT_ERROR_RATE_MIN_REQUEST_RATE);
}
