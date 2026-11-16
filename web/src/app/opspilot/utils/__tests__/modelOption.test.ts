import { selectableLlmModels } from '@/app/opspilot/utils/modelOption';

describe('selectableLlmModels', () => {
  it('keeps a model only when the model and its vendor are enabled', () => {
    const rows = selectableLlmModels([
      { name: 'keep', enabled: true, vendor_enabled: true },
      { name: 'model-off', enabled: false, vendor_enabled: true },
      { name: 'vendor-off', enabled: true, vendor_enabled: false },
      { name: 'both-off', enabled: false, vendor_enabled: false },
    ]);

    expect(rows.map((row) => row.name)).toEqual(['keep']);
  });
});
