import { expect, it } from 'vitest';
import { applyAlarmLocateParams, buildAlarmDetailTemplateHint, buildAlarmDetailUrl } from '../alarmDetailLink';

it('模板提示用当前站点前缀加上告警 ID 变量', () => {
  expect(buildAlarmDetailTemplateHint('http://localhost:3000/')).toBe(
    'http://localhost:3000/alarm/alarms?alert_id={{ alert.alert_id }}',
  );
});

it('详情链接用当前站点前缀加上告警 ID', () => {
  expect(buildAlarmDetailUrl('https://bklite.example.com/', 'ALERT 018')).toBe(
    'https://bklite.example.com/alarm/alarms?alert_id=ALERT+018',
  );
});

it('按链接定位时不带时间范围和状态筛选', () => {
  expect(applyAlarmLocateParams({
    status: 'pending,processing',
    created_at_after: '2026-01-01T00:00:00.000Z',
    created_at_before: '2026-01-08T00:00:00.000Z',
    activate: 1,
    my_alert: 1,
    level: '',
    page: 1,
  }, 'ALERT-018')).toEqual({
    status: '',
    created_at_after: '',
    created_at_before: '',
    activate: '',
    my_alert: '',
    level: '',
    page: 1,
    alert_id: 'ALERT-018',
  });
});
