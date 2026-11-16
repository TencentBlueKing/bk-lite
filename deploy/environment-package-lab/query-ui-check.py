from pathlib import Path
import json,re
from query_run import log_query_route
from playwright.sync_api import sync_playwright,expect
root=Path('/test');out=root/'evidence/query-alert-20261115';out.mkdir(exist_ok=True)
login=json.loads((root/'config/ui-login.json').read_text());url='http://10.10.248.31:18300'
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage']);c=b.new_context(timezone_id='Asia/Shanghai',viewport={'width':1440,'height':1000});page=c.new_page()
 page.goto(url+'/auth/signin',wait_until='networkidle');page.locator('input[autocomplete="username"]').fill(login['username']);page.locator('input[autocomplete="current-password"]').fill(login['password']);page.locator('button[type="submit"]').click();page.wait_for_url(lambda u:'/auth/signin' not in u,timeout=60000);page.wait_for_load_state('networkidle');page.wait_for_timeout(2000)

 traffic=json.loads((out/'alarm-traffic.json').read_text())
 checks=[]
 for route,required,label in [(log_query_route(out),[x['marker'] for x in traffic],'log-query'),('/apm/explore/traces',['cd-c','cd-d','GET /cd-validation'],'apm-query'),*[(('/apm/explore/traces/'+x['trace_ids'][0]),[x['service'],'GET /cd-validation'],'trace-'+x['service']) for x in traffic],('/apm/events/alerts',['C/D 延迟验证 cd-c','C/D 延迟验证 cd-d'],'apm-alerts'),('/log/event/alert',['C/D日志错误'],'log-alerts')]:
  page.goto(url+route,wait_until='networkidle');page.wait_for_timeout(1200)
  for value in required:
   expect(page.locator('body')).to_contain_text(value,timeout=60000)
  body=page.locator('body').inner_text()
  checks.append({'route':route,'checks':{v:v in body for v in required}})
  print(label,body[:6000],flush=True)
  page.screenshot(path=str(out/(label+'.png')),full_page=True)
 (out/'ui-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
 print(json.dumps(checks,ensure_ascii=False));b.close()
 assert all(all(x['checks'].values()) for x in checks),'UI content assertion failed'
 print('__CD_QUERY_AND_ALERT_UI_ASSERTIONS_PASSED__')
