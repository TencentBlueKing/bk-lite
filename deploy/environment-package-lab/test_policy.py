import copy
import unittest
from reconcile import executor_permissions
class PolicyTest(unittest.TestCase):
 def test_existing_is_preserved_and_reconcile_is_idempotent(self):
  original={'publish':{'allow':['existing.download']},'subscribe':{'allow':['_INBOX.>']}}
  snapshot=copy.deepcopy(original);out=executor_permissions(original,['node-c','node-d'])
  self.assertEqual(original,snapshot);self.assertEqual(out,executor_permissions(out,['node-c','node-d']))
  self.assertIn('existing.download',out['publish']['allow'])
 def test_business_permissions_do_not_grant_global_admin_or_other_regions(self):
  out=executor_permissions({'publish':{'allow':[]},'subscribe':{'allow':[]}},['node-c'])
  self.assertIn('apm.traces.2',out['publish']['allow']);self.assertNotIn('apm.traces.1',out['publish']['allow'])
  self.assertNotIn('>',out['publish']['allow']);self.assertNotIn('>',out['subscribe']['allow'])
  self.assertIn('$JS.API.CONSUMER.LIST.BK_ANS_EXEC_TASKS_NODE-C',out['publish']['allow'])
  self.assertIn('ansible.adhoc.node-c',out['subscribe']['allow']);self.assertNotIn('ansible.adhoc.*',out['subscribe']['allow'])
if __name__=='__main__':unittest.main()
