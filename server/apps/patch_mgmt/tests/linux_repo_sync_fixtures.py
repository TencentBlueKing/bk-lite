"""Linux repo 同步测试共享 XML 与源夹具。"""

import gzip

from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.services import linux_repo_sync

REPOMD = """<?xml version="1.0" encoding="UTF-8"?>
<repomd xmlns="http://linux.duke.edu/metadata/repo">
  <data type="primary"><location href="repodata/primary.xml.gz"/></data>
  <data type="updateinfo"><location href="repodata/updateinfo.xml.gz"/></data>
</repomd>"""

REPOMD_NO_UPDATEINFO = """<?xml version="1.0" encoding="UTF-8"?>
<repomd xmlns="http://linux.duke.edu/metadata/repo">
  <data type="primary"><location href="repodata/primary.xml.gz"/></data>
</repomd>"""

UPDATEINFO = """<?xml version="1.0"?>
<updates>
  <update from="x" status="final" type="security" version="2">
    <id>RHSA-2024:0001</id>
    <title>Important: openssl security update</title>
    <severity>Important</severity>
    <issued date="2024-01-01 00:00:00"/>
    <references>
      <reference href="h" id="CVE-2024-0001" type="cve" title="CVE-2024-0001"/>
      <reference href="h" id="CVE-2024-0002" type="cve" title="CVE-2024-0002"/>
    </references>
    <pkglist>
      <collection short="s">
        <package name="openssl" version="1.1.1k" release="7.el8" arch="x86_64"/>
        <package name="openssl-libs" version="1.1.1k" release="7.el8" arch="x86_64"/>
        <package name="openssl-libs" version="1.1.1k" release="7.el8" arch="x86_64"/>
        <package name="" version="1.1.1k" release="7.el8" arch="x86_64"/>
      </collection>
    </pkglist>
  </update>
  <update type="bugfix" version="1">
    <id>RHBA-2024:0002</id>
    <title>bash bugfix</title>
    <pkglist><collection><package name="bash" version="5.0" release="1.el8" arch="x86_64"/></collection></pkglist>
  </update>
</updates>"""


def _make_get(mocker, repomd=REPOMD, updateinfo=UPDATEINFO):
    def fake_get(url, **kwargs):
        resp = mocker.Mock()
        resp.raise_for_status = mocker.Mock()
        if url.endswith("repomd.xml"):
            payload = repomd.encode()
        elif "updateinfo" in url:
            payload = gzip.compress(updateinfo.encode())
        else:
            payload = b""
        resp.content = payload

        def iter_content(chunk_size=1):
            size = chunk_size if chunk_size and chunk_size > 0 else 1
            for index in range(0, len(payload), size):
                yield payload[index : index + size]

        resp.iter_content = iter_content
        resp.close = mocker.Mock()
        return resp
    return mocker.patch.object(linux_repo_sync.requests, "get", side_effect=fake_get)


def _source(**kw) -> PatchSource:
    return PatchSource.objects.create(**{
        "name": "centos7",
        "source_type": PatchSourceType.YUM_REPO,
        "url": "https://mirror.example.com/centos/7/os/x86_64",
        "distro_name": "centos",
        "os_version": ">=7",
        "team": [1],
        **kw,
    })
