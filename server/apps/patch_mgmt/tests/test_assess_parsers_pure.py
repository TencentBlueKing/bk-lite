"""评估结果解析器纯函数测试。"""

from apps.patch_mgmt.services import assess_parsers as parsers


APT_SAMPLE = """
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
Calculating upgrade... Done
The following packages will be upgraded:
  gzip perl-base tar
3 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
Inst gzip [1.10-10ubuntu4] (1.10-10ubuntu4.1 Ubuntu:24.04/noble-updates [amd64])
Inst perl-base [5.38.2-3.2build2] (5.38.2-3.2build2.1 Ubuntu:24.04/noble-updates [amd64])
Inst tar [1.35+dfsg-3build1] (1.35+dfsg-3build1.1 Ubuntu:24.04/noble-updates [amd64])
Conf gzip (1.10-10ubuntu4.1 Ubuntu:24.04/noble-updates [amd64])
"""

YUM_SAMPLE = """
Last metadata expiration check: 0:00:01 ago on Fri Jul 10 06:00:00 2026 UTC.
Available Upgrades
gzip.x86_64     1.10-10ubuntu4.1     noble-updates
perl-base.x86_64 5.38.2-3.2build2.1  noble-updates
tar.x86_64      1.35+dfsg-3build1.1  noble-updates
"""

DNF_SAMPLE = """
Last metadata expiration check: 0:00:01 ago.
Available Upgrades
curl.x86_64     7.76.1-26.el9_3.2    baseos
openssl.x86_64  1:3.0.7-25.el9_3     baseos
"""

HOTFIX_SAMPLE = """
HotFixID
KB5034441
KB5034763
KB5035857
"""


def test_parse_apt_upgradable():
    pkgs = parsers.parse_apt_upgradable(APT_SAMPLE)
    assert pkgs == {"gzip", "perl-base", "tar"}


def test_parse_apt_no_upgrades():
    stdout = "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
    assert parsers.parse_apt_upgradable(stdout) == set()


def test_parse_yum_upgradable():
    pkgs = parsers.parse_yum_dnf_upgradable(YUM_SAMPLE)
    assert pkgs == {"gzip", "perl-base", "tar"}


def test_parse_dnf_upgradable():
    pkgs = parsers.parse_yum_dnf_upgradable(DNF_SAMPLE)
    assert pkgs == {"curl", "openssl"}


def test_parse_windows_hotfixes():
    kbs = parsers.parse_windows_hotfixes(HOTFIX_SAMPLE)
    assert kbs == {"KB5034441", "KB5034763", "KB5035857"}


def test_parse_windows_hotfixes_lowercase():
    kbs = parsers.parse_windows_hotfixes("kb123456\nKB999999")
    assert kbs == {"KB123456", "KB999999"}
