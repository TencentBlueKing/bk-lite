export interface ChannelColorChoice {
  token: string;
  swatch: string;
  usageKey: string;
  snippet: string;
}

export interface ChannelColorGuide {
  introKey: string;
  choices: ChannelColorChoice[];
}

const EMAIL_GUIDE: ChannelColorGuide = {
  introKey: 'settings.notificationTemplate.colorTipEmail',
  choices: [
    {
      token: '{{ alert.level_color }}',
      swatch: '',
      usageKey: 'settings.notificationTemplate.colorTipEmailFollow',
      snippet: '<strong style="color:{{ alert.level_color }};">{{ alert.level }}</strong>',
    },
    {
      token: '#F43B2C',
      swatch: '#F43B2C',
      usageKey: 'settings.notificationTemplate.colorTipCritical',
      snippet: '<strong style="color:#F43B2C;">{{ alert.level }}</strong>',
    },
    {
      token: '#D97007',
      swatch: '#D97007',
      usageKey: 'settings.notificationTemplate.colorTipError',
      snippet: '<strong style="color:#D97007;">{{ alert.level }}</strong>',
    },
    {
      token: '#FFAD42',
      swatch: '#FFAD42',
      usageKey: 'settings.notificationTemplate.colorTipWarning',
      snippet: '<strong style="color:#FFAD42;">{{ alert.level }}</strong>',
    },
  ],
};

const WECOM_GUIDE: ChannelColorGuide = {
  introKey: 'settings.notificationTemplate.colorTipWecom',
  choices: [
    {
      token: 'warning',
      swatch: '#ed6a0c',
      usageKey: 'settings.notificationTemplate.colorTipWecomWarning',
      snippet: '<font color="warning">{{ alert.level }}</font>',
    },
    {
      token: 'comment',
      swatch: '#8c8c8c',
      usageKey: 'settings.notificationTemplate.colorTipWecomComment',
      snippet: '<font color="comment">{{ alert.level }}</font>',
    },
    {
      token: 'info',
      swatch: '#1aad19',
      usageKey: 'settings.notificationTemplate.colorTipWecomInfo',
      snippet: '<font color="info">{{ alert.level }}</font>',
    },
  ],
};

const FEISHU_GUIDE: ChannelColorGuide = {
  introKey: 'settings.notificationTemplate.colorTipFeishu',
  choices: [
    {
      token: 'red',
      swatch: '#f54a45',
      usageKey: 'settings.notificationTemplate.colorTipCritical',
      snippet: "<font color='red'>{{ alert.level }}</font>",
    },
    {
      token: 'orange',
      swatch: '#ff8800',
      usageKey: 'settings.notificationTemplate.colorTipError',
      snippet: "<font color='orange'>{{ alert.level }}</font>",
    },
    {
      token: 'yellow',
      swatch: '#c48a00',
      usageKey: 'settings.notificationTemplate.colorTipWarning',
      snippet: "<font color='yellow'>{{ alert.level }}</font>",
    },
    {
      token: 'green',
      swatch: '#34c724',
      usageKey: 'settings.notificationTemplate.colorTipFeishuGreen',
      snippet: "<font color='green'>{{ alert.level }}</font>",
    },
  ],
};

const UNSUPPORTED_GUIDE: ChannelColorGuide = {
  introKey: 'settings.notificationTemplate.colorTipUnsupported',
  choices: [],
};

const GUIDES: Record<string, ChannelColorGuide> = {
  email: EMAIL_GUIDE,
  enterprise_wechat_bot: WECOM_GUIDE,
  feishu_bot: FEISHU_GUIDE,
};

export const getChannelColorGuide = (channelType: string): ChannelColorGuide => GUIDES[channelType] || UNSUPPORTED_GUIDE;
