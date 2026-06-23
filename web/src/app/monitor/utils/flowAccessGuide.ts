export interface FlowListenerEndpoint {
  protocol: string;
  protocol_name: string;
  endpoint: string;
  port: number;
}

interface BuildFlowEndpointGuideStepParams {
  endpoint: string;
  listenerEndpoints?: FlowListenerEndpoint[];
  t: (key: string, fallback?: unknown, values?: Record<string, unknown>) => string;
}

export const shouldShowSingleFlowEndpoint = (listenerEndpoints?: FlowListenerEndpoint[]) => (
  !listenerEndpoints || listenerEndpoints.length <= 1
);

export const buildFlowEndpointGuideStep = ({
  endpoint,
  listenerEndpoints = [],
  t,
}: BuildFlowEndpointGuideStepParams) => {
  if (listenerEndpoints.length > 1) {
    const endpoints = listenerEndpoints
      .map((item) => `${item.protocol_name}：${item.endpoint}`)
      .join('；');
    return t('monitor.integrations.flow.guideStepSetVersionEndpoints', undefined, { endpoints });
  }

  return t('monitor.integrations.flow.guideStepSetEndpoint', undefined, { endpoint });
};
