function loadStudioRetirementNoticePolicy(): boolean {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const policy = require('@/app/opspilot/(enterprise)/extensions/studioRetirementNotice');
    return policy.showStudioRetirementNotice !== false;
  } catch {
    return true;
  }
}

export const showStudioRetirementNotice = loadStudioRetirementNoticePolicy();
