from pathlib import Path
import json,re
from playwright.sync_api import sync_playwright,expect
root=Path('/test');out=root/'evidence/query-alert-20261115';out.mkdir(exist_ok=True)
login=json.loads((root/'config/ui-login.json').read_text());url='http://10.10.248.31:18300'
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage']);c=b.new_context(timezone_id='Asia/Shanghai',viewport={'width':1440,'height':1000});page=c.new_page()
 page.goto(url+'/auth/signin',wait_until='networkidle');page.locator('input[autocomplete="username"]').fill(login['username']);page.locator('input[autocomplete="current-password"]').fill(login['password']);page.locator('button[type="submit"]').click();page.wait_for_url(lambda u:'/auth/signin' not in u,timeout=60000);page.wait_for_load_state('networkidle');page.wait_for_timeout(2000)

 page.goto(url+'/log/event/alert',wait_until='networkidle');page.wait_for_timeout(1000)
 for ip in ['192.168.122.4','192.168.122.209']:
  row=page.get_by_role('row').filter(has_text=ip+' C/D日志错误')
  expect(row).to_have_count(1)
  row.get_by_role('button',name='详情',exact=True).click();page.wait_for_timeout(1000)
  print('LOG_DETAIL',ip,page.locator('body').inner_text()[-6500:],flush=True)
  page.screenshot(path=str(out/('log-detail-'+ip+'.png')),full_page=True)
  page.goto(url+'/log/event/alert',wait_until='networkidle');page.wait_for_timeout(800)
  row=page.get_by_role('row').filter(has_text=ip+' C/D日志错误')
  row.get_by_role('button',name='关闭',exact=True).click()
  page.locator('.ant-popconfirm').get_by_role('button',name=re.compile(r'确\s*认')).click()
  expect(page.get_by_role('row').filter(has_text=ip+' C/D日志错误')).to_have_count(0,timeout=15000)
 page.screenshot(path=str(out/'log-alerts-after-close.png'),full_page=True)
 print('__LOG_ALERTS_CLOSED_VIA_UI__');b.close()
