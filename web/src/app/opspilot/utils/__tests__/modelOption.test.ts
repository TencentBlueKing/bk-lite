import { selectableLlmModels, withBoundUnavailableModels } from '@/app/opspilot/utils/modelOption';

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

describe('withBoundUnavailableModels', () => {
  const models = [{ id: 1, name: 'keep', vendor_name: 'OpenAI' }];

  it('appends the current value when it is missing and marks it disabled', () => {
    const choices = withBoundUnavailableModels(models, 9, [{ id: 9, name: 'retired', vendor_name: 'Off' }]);

    expect(choices).toEqual([
      { model: models[0], disabled: false },
      { model: { id: 9, name: 'retired', vendor_name: 'Off' }, disabled: true },
    ]);
  });

  it('does not duplicate a current value that is already selectable', () => {
    const choices = withBoundUnavailableModels(models, 1, [{ id: 1, name: 'other-name' }]);

    expect(choices).toEqual([{ model: models[0], disabled: false }]);
  });
});
