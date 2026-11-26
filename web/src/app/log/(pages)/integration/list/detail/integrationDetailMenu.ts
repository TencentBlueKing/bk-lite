import { MenuItem } from '@/types/index';

export function buildPassiveIntegrationDetailMenu(input: {
  configurationTitle: string;
  extractorTitle: string;
  introductionTitle: string;
}): MenuItem[] {
  return [
    {
      title: input.configurationTitle,
      icon: 'settings-fill',
      url: '/log/integration/list/detail/configure',
      name: 'integration_configure',
      operation: []
    },
    {
      title: input.extractorTitle,
      icon: 'shujumoxingguanli',
      url: '/log/integration/list/detail/extractor',
      name: 'integration_extractor',
      operation: []
    },
    {
      title: input.introductionTitle,
      icon: 'mulu',
      url: '/log/integration/list/detail/output',
      name: 'integration_output',
      operation: []
    }
  ];
}
