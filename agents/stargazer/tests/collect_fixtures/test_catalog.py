# -*- coding: utf-8 -*-
"""catalog.py 单测"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures.catalog import MODEL_SPECS, Spec, lookup, list_models, validate, validate_spec  # noqa: E402


def _make_spec(**overrides):
    defaults = dict(
        model_id="mysql",
        image="mysql:8.0",
        ports={"3306/tcp": 13306},
        env={"MYSQL_ROOT_PASSWORD": "rootpw"},
        wait_strategy={"type": "tcp", "port": 13306, "timeout": 60},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.mysql.mysql_info",
        entry_class="MysqlInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 13306, "user": "root", "password": "rootpw"},
    )
    defaults.update(overrides)
    return Spec(**defaults)


def test_lookup_returns_spec():
    spec = lookup("mysql")
    assert spec.model_id == "mysql"
    assert spec.image == "mysql:8.0"


def test_lookup_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        lookup("not_exists_xyz")


def test_list_models_returns_sorted_ids():
    models = list_models()
    assert isinstance(models, list)
    assert models == sorted(models)
    assert "mysql" in models


def test_validate_all_specs_have_required_fields():
    errors = validate()
    assert errors == [], f"validate 发现配置错误: {errors}"


def test_spec_dataclass_is_immutable():
    spec = _make_spec()
    with pytest.raises(Exception):
        spec.model_id = "other"  # frozen dataclass


# ---------- Gap-4: validate_spec 单对象校验 ----------

def test_validate_spec_detects_unimportable_python_entry_module():
    """python 入口的 entry_module 不存在时,validate_spec 应明确报错。
    目的:防止路径拼写错误直到 collect 阶段才暴露(那时已经拉起容器)。"""
    spec = _make_spec(
        entry_type="python",
        entry_module="nonexistent.fake.module.xyz_abc_123",
        entry_class="FakeClass",
    )
    errors = validate_spec(spec)
    assert any(
        "nonexistent.fake.module.xyz_abc_123" in e and "import" in e.lower()
        for e in errors
    ), f"应报 entry_module 不可导入,实际 errors: {errors}"


def test_validate_spec_accepts_importable_python_entry_module():
    """python 入口的 entry_module 可导入时,validate_spec 不报 module 类错误。"""
    spec = _make_spec(
        entry_type="python",
        entry_module="json",  # 标准库,一定可导入
        entry_class="JSONDecoder",  # 任意存在属性即可
    )
    errors = validate_spec(spec)
    import_errors = [e for e in errors if "import" in e.lower() and "json" in e]
    assert import_errors == [], f"不应报 json 模块导入错误,实际: {import_errors}"


def test_validate_spec_skips_import_check_for_non_python_entry():
    """shell/ssh 入口不需要 entry_module,validate_spec 不应报 module 类错误。"""
    for entry_type in ("shell", "ssh"):
        spec = _make_spec(
            entry_type=entry_type,
            entry_module="nonexistent.fake.module.xyz",  # 即便填错也不该管
            entry_class=None,
        )
        errors = validate_spec(spec)
        module_errors = [e for e in errors if "import" in e.lower()]
        assert module_errors == [], (
            f"{entry_type} 入口不应做 module import 检查,实际: {module_errors}"
        )


def test_validate_spec_detects_missing_entry_class_attribute():
    """python 入口的 entry_class 在模块里不存在时,validate_spec 应报错。"""
    spec = _make_spec(
        entry_type="python",
        entry_module="json",
        entry_class="TotallyNotExistingClassName_XYZ_123",
    )
    errors = validate_spec(spec)
    assert any(
        "TotallyNotExistingClassName_XYZ_123" in e and "entry_class" in e
        for e in errors
    ), f"应报 entry_class 不存在,实际 errors: {errors}"


def test_validate_spec_skips_class_check_for_non_python_entry():
    """shell/ssh 入口不需要 entry_class,validate_spec 不应报 class 类错误。"""
    for entry_type in ("shell", "ssh"):
        spec = _make_spec(
            entry_type=entry_type,
            entry_module=None,
            entry_class="FakeClass",  # 即便填错也不该管
        )
        errors = validate_spec(spec)
        class_errors = [e for e in errors if "entry_class" in e]
        assert class_errors == [], (
            f"{entry_type} 入口不应做 entry_class 检查,实际: {class_errors}"
        )


def test_validate_spec_detects_missing_entry_method():
    """python 入口的 entry_method 在类里不存在时,validate_spec 应报错。
    目的:list_all_resources 是默认方法,改名后不会立即报错,collect 时才 NPE。"""
    spec = _make_spec(
        entry_type="python",
        entry_module="json",
        entry_class="JSONDecoder",
        entry_method="totally_not_a_method_xyz_123",
    )
    errors = validate_spec(spec)
    assert any(
        "totally_not_a_method_xyz_123" in e and "entry_method" in e
        for e in errors
    ), f"应报 entry_method 不存在,实际 errors: {errors}"


def test_validate_spec_accepts_builtin_entry_method():
    """python 入口的 entry_method 是内置方法时(如 decode),validate_spec 应通过。"""
    spec = _make_spec(
        entry_type="python",
        entry_module="json",
        entry_class="JSONDecoder",
        entry_method="decode",  # JSONDecoder.decode 确实存在
    )
    errors = validate_spec(spec)
    method_errors = [e for e in errors if "entry_method" in e]
    assert method_errors == [], f"不应报 entry_method 错误,实际: {method_errors}"


def test_validate_spec_skips_method_check_for_non_python_entry():
    """shell/ssh 入口不需要 entry_method,validate_spec 不应报 method 类错误。"""
    for entry_type in ("shell", "ssh"):
        spec = _make_spec(
            entry_type=entry_type,
            entry_method="some_method_xyz",
        )
        errors = validate_spec(spec)
        method_errors = [e for e in errors if "entry_method" in e]
        assert method_errors == [], (
            f"{entry_type} 入口不应做 entry_method 检查,实际: {method_errors}"
        )


# ---------- Gap-4 #4: init_script 后缀一致性 ----------

def test_validate_spec_detects_wrong_suffix_for_python_entry():
    """python 入口的 init_script 必须以 .sql 结尾。"""
    spec = _make_spec(
        entry_type="python",
        init_script="redis_default_discover.sh",  # 错配 ssh 脚本
    )
    errors = validate_spec(spec)
    assert any(
        "init_script" in e and ".sql" in e
        for e in errors
    ), f"python 入口配 .sh 应报后缀错误,实际 errors: {errors}"


def test_validate_spec_detects_wrong_suffix_for_shell_entry():
    """shell 入口的 init_script 必须以 .sh 结尾。"""
    spec = _make_spec(
        entry_type="shell",
        init_script="mysql.sql",  # 错配 sql
        entry_module=None,
        entry_class=None,
    )
    errors = validate_spec(spec)
    assert any(
        "init_script" in e and ".sh" in e
        for e in errors
    ), f"shell 入口配 .sql 应报后缀错误,实际 errors: {errors}"


def test_validate_spec_detects_wrong_suffix_for_ssh_entry():
    """ssh 入口的 init_script 必须以 _default_discover.sh 结尾。"""
    spec = _make_spec(
        entry_type="ssh",
        init_script="install.sh",  # 没按约定命名
    )
    errors = validate_spec(spec)
    assert any(
        "init_script" in e and "_default_discover.sh" in e
        for e in errors
    ), f"ssh 入口非 _default_discover.sh 应报后缀错误,实际 errors: {errors}"


def test_validate_spec_accepts_correct_suffix_per_entry_type():
    """三类入口的合法后缀都应通过校验。"""
    cases = [
        ("python", "mysql.sql"),
        ("shell", "redis_default_discover.sh"),
        ("ssh", "nginx_default_discover.sh"),
    ]
    for entry_type, script in cases:
        spec = _make_spec(
            entry_type=entry_type,
            init_script=script,
        )
        errors = validate_spec(spec)
        suffix_errors = [e for e in errors if "init_script" in e and "后缀" in e]
        assert suffix_errors == [], (
            f"{entry_type} + {script} 应通过,但报: {suffix_errors}"
        )


# ---------- Gap-4 #5: wait_strategy 字段组合 ----------

def test_validate_spec_detects_tcp_wait_strategy_without_port():
    """type='tcp' 的 wait_strategy 必须带 port。"""
    spec = _make_spec(
        entry_type="python",
        wait_strategy={"type": "tcp", "timeout": 60},  # 缺 port
    )
    errors = validate_spec(spec)
    assert any(
        "wait_strategy" in e and "tcp" in e and "port" in e
        for e in errors
    ), f"tcp 缺 port 应报错,实际 errors: {errors}"


def test_validate_spec_detects_ssh_wait_strategy_without_timeout():
    """type='ssh' 的 wait_strategy 必须带 timeout。"""
    spec = _make_spec(
        entry_type="ssh",
        wait_strategy={"type": "ssh"},  # 缺 timeout
    )
    errors = validate_spec(spec)
    assert any(
        "wait_strategy" in e and "ssh" in e and "timeout" in e
        for e in errors
    ), f"ssh 缺 timeout 应报错,实际 errors: {errors}"


def test_validate_spec_detects_invalid_wait_strategy_type():
    """wait_strategy.type 必须是合法值(tcp / ssh)。"""
    spec = _make_spec(
        entry_type="python",
        wait_strategy={"type": "udp", "port": 13306},  # 非法 type
    )
    errors = validate_spec(spec)
    assert any(
        "wait_strategy" in e and "type" in e and ("udp" in e or "非法" in e or "不支持" in e)
        for e in errors
    ), f"非法 wait_strategy.type 应报错,实际 errors: {errors}"


def test_validate_spec_accepts_valid_wait_strategies():
    """合法的 tcp / ssh wait_strategy 应通过。"""
    cases = [
        {"type": "tcp", "port": 13306, "timeout": 60},
        {"type": "ssh", "timeout": 60, "interval": 1.0},
    ]
    for ws in cases:
        spec = _make_spec(entry_type="python", wait_strategy=ws)
        errors = validate_spec(spec)
        ws_errors = [e for e in errors if "wait_strategy" in e]
        assert ws_errors == [], (
            f"wait_strategy {ws} 应通过,实际: {ws_errors}"
        )


# ---------- Gap-4 #6: ports key 格式合法 ----------

def test_validate_spec_detects_invalid_port_key_format():
    """ports 的 key 必须形如 '数字/tcp' 或 '数字/udp'。"""
    bad_ports_cases = [
        {"80": 18080},          # 缺协议
        {"80/http": 18080},     # 非法协议
        {"abc/tcp": 18080},     # 非数字
        {"70000/tcp": 18080},   # 端口超范围
        {"-1/tcp": 18080},      # 负端口
    ]
    for ports in bad_ports_cases:
        spec = _make_spec(entry_type="python", ports=ports)
        errors = validate_spec(spec)
        port_errors = [e for e in errors if "ports" in e]
        assert port_errors, (
            f"ports={ports} 应报格式错,实际 errors: {errors}"
        )


def test_validate_spec_accepts_valid_port_keys():
    """合法的 tcp / udp 端口格式都应通过。"""
    for ports in (
        {"22/tcp": 12222, "80/tcp": 18080},
        {"53/udp": 15353},
    ):
        spec = _make_spec(entry_type="python", ports=ports)
        errors = validate_spec(spec)
        port_errors = [e for e in errors if "ports" in e]
        assert port_errors == [], (
            f"ports={ports} 应通过,实际: {port_errors}"
        )


# ---------- Gap-1: 新增对象的 catalog 接入 ----------

def test_elasticsearch_in_model_specs():
    """G1.1: elasticsearch 必须在 MODEL_SPECS 中。"""
    assert "elasticsearch" in list_models(), "elasticsearch 必须注册到 MODEL_SPECS"


def test_elasticsearch_spec_passes_validation():
    """G1.1: elasticsearch Spec 必须通过 validate_spec() 校验。"""
    spec = lookup("elasticsearch")
    errors = validate_spec(spec)
    assert errors == [], f"elasticsearch Spec 校验失败: {errors}"


def test_elasticsearch_spec_uses_ssh_entry_type():
    """G1.1: elasticsearch 走 ssh 入口(与 mongodb/nginx/tomcat/rabbitmq 一致)。"""
    spec = lookup("elasticsearch")
    assert spec.entry_type == "ssh", f"elasticsearch 应为 ssh 入口,实际 {spec.entry_type}"


def test_elasticsearch_spec_has_distinct_host_ports():
    """G1.1: elasticsearch 的 host 端口必须不与现有 7 个对象冲突。"""
    spec = lookup("elasticsearch")
    existing_ports = {
        host_port
        for s in [lookup(m) for m in list_models() if m != "elasticsearch"]
        for host_port in s.ports.values()
    }
    new_ports = set(spec.ports.values())
    overlap = new_ports & existing_ports
    assert not overlap, f"elasticsearch host 端口 {overlap} 与现有对象冲突"


def test_kafka_in_model_specs():
    """G1.2: kafka 必须在 MODEL_SPECS 中。"""
    assert "kafka" in list_models(), "kafka 必须注册到 MODEL_SPECS"


def test_kafka_spec_passes_validation():
    """G1.2: kafka Spec 必须通过 validate_spec() 校验。"""
    spec = lookup("kafka")
    errors = validate_spec(spec)
    assert errors == [], f"kafka Spec 校验失败: {errors}"


def test_activemq_in_model_specs():
    """G1.3: activemq 必须在 MODEL_SPECS 中。"""
    assert "activemq" in list_models(), "activemq 必须注册到 MODEL_SPECS"


def test_activemq_spec_passes_validation():
    """G1.3: activemq Spec 必须通过 validate_spec() 校验。"""
    spec = lookup("activemq")
    errors = validate_spec(spec)
    assert errors == [], f"activemq Spec 校验失败: {errors}"


def test_mssql_in_model_specs():
    """G1.4: mssql 必须在 MODEL_SPECS 中。"""
    assert "mssql" in list_models(), "mssql 必须注册到 MODEL_SPECS"


def test_mssql_spec_passes_validation():
    """G1.4: mssql Spec 必须通过 validate_spec() 校验。"""
    spec = lookup("mssql")
    errors = validate_spec(spec)
    assert errors == [], f"mssql Spec 校验失败: {errors}"


def test_mssql_spec_uses_ssh_entry_with_sqlcmd():
    """G1.4: mssql 走 ssh 入口(sqlcmd 采集,绕开本机 pyodbc native lib 依赖)。"""
    spec = lookup("mssql")
    assert spec.entry_type == "ssh"
    assert spec.init_script == "mssql_default_discover.sh"
    assert spec.vm_ssh_password == "testpw"


# ---------- G2.1: redis_sentinel(商业版首批) ----------

def test_redis_sentinel_in_model_specs():
    """G2.1: redis_sentinel 必须在 MODEL_SPECS 中(11 → 12)。"""
    assert "redis_sentinel" in list_models(), "redis_sentinel 必须注册到 MODEL_SPECS"


def test_redis_sentinel_spec_passes_validation():
    """G2.1: redis_sentinel Spec 必须通过 validate_spec() 校验。"""
    spec = lookup("redis_sentinel")
    errors = validate_spec(spec)
    assert errors == [], f"redis_sentinel Spec 校验失败: {errors}"


def test_redis_sentinel_uses_shell_entry_with_two_ports():
    """G2.1: redis_sentinel 走 shell 入口(复用 redis 镜像 + 双端口探测)。"""
    spec = lookup("redis_sentinel")
    assert spec.entry_type == "shell", f"redis_sentinel 应为 shell 入口,实际 {spec.entry_type}"
    # 双端口:redis 6379 → 16380 + sentinel 26379 → 26380(避开 redis Spec 已用的 16379)
    assert spec.ports == {"6379/tcp": 16380, "26379/tcp": 26380}, (
        f"redis_sentinel 应有 redis+sentinel 双端口,实际 {spec.ports}"
    )


def test_redis_sentinel_container_cmd_starts_both_processes():
    """G2.1: container_cmd 必须包含 redis-server 后台 + redis-sentinel 前台。"""
    spec = lookup("redis_sentinel")
    assert spec.container_cmd is not None, "redis_sentinel 必须有 container_cmd 启动双进程"
    cmd = spec.container_cmd
    assert "redis-server" in cmd and "--daemonize" in cmd, "container_cmd 必须后台起 redis-server"
    assert "redis-sentinel" in cmd, "container_cmd 必须前台起 redis-sentinel"
    assert "/etc/sentinel.conf" in cmd, "container_cmd 必须写 sentinel.conf 再启 sentinel"
    # sentinel 配置必须指向 redis-server 的端口(同容器内 127.0.0.1:6379)
    assert "sentinel monitor mymaster 127.0.0.1 6379 2" in cmd, (
        "sentinel monitor 必须指向 127.0.0.1:6379(同容器内的 redis-server)"
    )


def test_redis_sentinel_collector_kwargs_ports_list():
    """G2.1: collector_kwargs.ports 必须是 list(走 _build_shell_env 的多端口分支)。
    端口语义:容器内端口(脚本在容器内通过 127.0.0.1:容器内端口 连接)。"""
    spec = lookup("redis_sentinel")
    assert "ports" in spec.collector_kwargs, "redis_sentinel collector_kwargs 必须有 ports 字段"
    ports = spec.collector_kwargs["ports"]
    assert isinstance(ports, (list, tuple)), f"ports 必须是 list/tuple,实际 {type(ports)}"
    # 容器内端口:redis-server 6379 + redis-sentinel 26379(对应 host 端口 16380/26380)
    assert 6379 in ports and 26379 in ports, (
        f"ports 必须包含容器内 redis(6379) + sentinel(26379)端口,实际 {ports}"
    )


def test_redis_sentinel_init_script_mirror_exists():
    """G2.1: init/redis_sentinel_default_discover.sh 必须存在(sentinel 镜像副本)。"""
    spec = lookup("redis_sentinel")
    init_dir = Path(__file__).parent / "init"
    script_path = init_dir / spec.init_script
    assert script_path.exists(), f"init 脚本不存在: {script_path}"
    # 内容应包含 sentinel 探测逻辑(从 redis_default_discover.sh 镜像)
    content = script_path.read_text(encoding="utf-8")
    assert "SENTINEL" in content, "init 脚本必须含 SENTINEL 采集逻辑"
    assert "redis-sentinel 采集" in content or "Redis SENTINEL" in content, (
        "init 脚本头部应有 sentinel 镜像注释"
    )


def test_redis_sentinel_has_distinct_host_ports():
    """G2.1: redis_sentinel 的 host 端口必须不与现有对象冲突(沿用 G1.1 模式)。"""
    spec = lookup("redis_sentinel")
    existing_ports = {
        host_port
        for m in list_models() if m != "redis_sentinel"
        for host_port in lookup(m).ports.values()
    }
    new_ports = set(spec.ports.values())
    overlap = new_ports & existing_ports
    assert not overlap, f"redis_sentinel host 端口 {overlap} 与现有对象冲突"


# ---------- G2.3: dameng(商业版首批,降级路径 — license 不可达) ----------

def test_dameng_in_model_specs():
    """G2.3: dameng 必须在 MODEL_SPECS 中(12 → 13)。"""
    assert "dameng" in list_models(), "dameng 必须注册到 MODEL_SPECS"


def test_dameng_spec_passes_validation():
    """G2.3: dameng Spec 必须通过 validate_spec() 校验(install 故意 exit 1 仍通过 schema 校验)。"""
    spec = lookup("dameng")
    errors = validate_spec(spec)
    assert errors == [], f"dameng Spec 校验失败: {errors}"


def test_dameng_uses_ssh_entry_for_apt_install_path():
    """G2.3: dameng 走 ssh 入口(ubuntu:22.04 + apt 装 sshd/ssh 跑复用脚本)。"""
    spec = lookup("dameng")
    assert spec.entry_type == "ssh", f"dameng 应为 ssh 入口,实际 {spec.entry_type}"
    assert spec.init_script == "dameng_default_discover.sh"
    assert spec.vm_ssh_password == "testpw"
    # DM 默认端口 5236
    assert "5236/tcp" in spec.ports, "dameng 必须暴露 DM 默认端口 5236/tcp"


def test_dameng_install_commands_contains_license_block_marker():
    """G2.3: install_commands 末尾必须含 license 阻塞标记(防止误以为已实现)。"""
    spec = lookup("dameng")
    assert spec.install_commands, "dameng install_commands 必填"
    # 最后一行必须是 exit 1
    assert "exit 1" in spec.install_commands[-1], (
        "dameng install_commands 最后一行必须含 exit 1(降级标识)"
    )
    # 倒数第二行应注释阻塞原因(license / G2.3 关键字)
    pre_last = spec.install_commands[-2]
    assert "license" in pre_last.lower() or "G2.3" in pre_last, (
        f"exit 1 前应注释 license 阻塞原因,实际: {pre_last!r}"
    )


def test_dameng_init_script_mirror_exists():
    """G2.3: init/dameng_default_discover.sh 必须存在(plugins/inputs/dameng/ 的镜像副本)。"""
    spec = lookup("dameng")
    init_dir = Path(__file__).parent / "init"
    script_path = init_dir / spec.init_script
    assert script_path.exists(), f"init 脚本不存在: {script_path}"
    content = script_path.read_text(encoding="utf-8")
    assert "dmap" in content, "init 脚本必须含 dmap 进程扫描逻辑(达梦特征)"


def test_dameng_has_distinct_host_ports():
    """G2.3: dameng 的 host 端口必须不与现有对象冲突。"""
    spec = lookup("dameng")
    existing_ports = {
        host_port
        for m in list_models() if m != "dameng"
        for host_port in lookup(m).ports.values()
    }
    new_ports = set(spec.ports.values())
    overlap = new_ports & existing_ports
    assert not overlap, f"dameng host 端口 {overlap} 与现有对象冲突"


# ---------- G2.2: ibmmq(商业版首批,选 B — license 不可达) ----------

def test_ibmmq_in_model_specs():
    """G2.2: ibmmq 必须在 MODEL_SPECS 中(13 → 14)。"""
    assert "ibmmq" in list_models(), "ibmmq 必须注册到 MODEL_SPECS"


def test_ibmmq_spec_passes_validation():
    """G2.2: ibmmq Spec 必须通过 validate_spec() 校验(选 B 占位,install 故意 exit 1)。"""
    spec = lookup("ibmmq")
    errors = validate_spec(spec)
    assert errors == [], f"ibmmq Spec 校验失败: {errors}"


def test_ibmmq_uses_ssh_entry_with_mq_port():
    """G2.2: ibmmq 走 ssh 入口(ubuntu + sshd + 复杂 install),暴露 MQ 默认端口 1414。"""
    spec = lookup("ibmmq")
    assert spec.entry_type == "ssh", f"ibmmq 应为 ssh 入口,实际 {spec.entry_type}"
    assert "1414/tcp" in spec.ports, "ibmmq 必须暴露 MQ 默认端口 1414/tcp"
    assert "9443/tcp" in spec.ports, "ibmmq 必须暴露 web console 端口 9443/tcp"


def test_ibmmq_install_commands_contains_license_block_marker():
    """G2.2: install_commands 末尾必须含 license 阻塞标记。"""
    spec = lookup("ibmmq")
    assert "exit 1" in spec.install_commands[-1], (
        "ibmmq install_commands 最后一行必须含 exit 1(降级标识)"
    )
    pre_last = spec.install_commands[-2]
    assert "license" in pre_last.lower() or "G2.2" in pre_last, (
        f"exit 1 前应注释 license 阻塞原因,实际: {pre_last!r}"
    )


def test_ibmmq_init_script_placeholder_exists():
    """G2.2: init/ibmmq_default_discover.sh 占位脚本存在(license 就位后替换为真实脚本)。"""
    spec = lookup("ibmmq")
    init_dir = Path(__file__).parent / "init"
    script_path = init_dir / spec.init_script
    assert script_path.exists(), f"占位 init 脚本不存在: {script_path}"
    content = script_path.read_text(encoding="utf-8")
    assert "placeholder" in content.lower(), "占位脚本应明确标注 placeholder"


def test_ibmmq_has_distinct_host_ports():
    """G2.2: ibmmq 的 host 端口必须不与现有对象冲突。"""
    spec = lookup("ibmmq")
    existing_ports = {
        host_port
        for m in list_models() if m != "ibmmq"
        for host_port in lookup(m).ports.values()
    }
    new_ports = set(spec.ports.values())
    overlap = new_ports & existing_ports
    assert not overlap, f"ibmmq host 端口 {overlap} 与现有对象冲突"


# ---------- G2.1 改造:_build_shell_env 支持 ports list ----------

def test_build_shell_env_with_ports_list():
    """G2.1: collector_kwargs.ports 是 list 时,REDIS_TARGET_PORTS 应是逗号分隔。"""
    from tests.collect_fixtures.run_collector import _build_shell_env

    spec = _make_spec(
        entry_type="shell",
        collector_kwargs={"host": "127.0.0.1", "ports": [16380, 26380], "password": "testpass"},
    )
    env = _build_shell_env(spec)
    assert env["REDIS_TARGET_PORTS"] == "16380,26380", (
        f"ports list 应被序列化为逗号分隔,实际: {env.get('REDIS_TARGET_PORTS')!r}"
    )
    assert env["REDISCLI_AUTH"] == "testpass"
    assert env["REDIS_TARGET_HOST"] == "127.0.0.1"


def test_build_shell_env_with_single_port_unchanged():
    """G2.1 backward-compat: 仍传 port(标量)时,行为不变(redis Spec 不回归)。"""
    from tests.collect_fixtures.run_collector import _build_shell_env

    spec = _make_spec(
        entry_type="shell",
        collector_kwargs={"host": "127.0.0.1", "port": 16379, "password": ""},
    )
    env = _build_shell_env(spec)
    assert env["REDIS_TARGET_PORTS"] == "16379", (
        f"单 port 应直接字符串化,实际: {env.get('REDIS_TARGET_PORTS')!r}"
    )


def test_build_shell_env_ports_list_takes_precedence_over_spec_env():
    """G2.1: collector_kwargs.ports 应覆盖 spec.env['REDIS_TARGET_PORTS']。"""
    from tests.collect_fixtures.run_collector import _build_shell_env

    spec = _make_spec(
        entry_type="shell",
        env={"REDIS_TARGET_PORTS": "old-value-from-spec-env"},
        collector_kwargs={"host": "127.0.0.1", "ports": [16380, 26380]},
    )
    env = _build_shell_env(spec)
    assert env["REDIS_TARGET_PORTS"] == "16380,26380", (
        "kwargs.ports 应在 spec.env 之后写入并覆盖"
    )


# ---------- Gap-4 #7: ssh 入口 install/start_commands 必填 ----------

def test_validate_spec_detects_ssh_entry_with_empty_install_commands():
    """ssh 入口的 install_commands 必须非空。"""
    spec = _make_spec(
        entry_type="ssh",
        install_commands=(),
    )
    errors = validate_spec(spec)
    assert any(
        "install_commands" in e and "ssh" in e
        for e in errors
    ), f"ssh 缺 install_commands 应报错,实际 errors: {errors}"


def test_validate_spec_detects_ssh_entry_with_empty_start_commands():
    """ssh 入口的 start_commands 必须非空。"""
    spec = _make_spec(
        entry_type="ssh",
        install_commands=("echo placeholder",),  # 这个不空
        start_commands=(),
    )
    errors = validate_spec(spec)
    assert any(
        "start_commands" in e and "ssh" in e
        for e in errors
    ), f"ssh 缺 start_commands 应报错,实际 errors: {errors}"


def test_validate_spec_skips_install_check_for_non_ssh_entry():
    """python / shell 入口不需要 install_commands,validate_spec 不应报错。"""
    for entry_type in ("python", "shell"):
        spec = _make_spec(
            entry_type=entry_type,
            install_commands=(),
            start_commands=(),
        )
        errors = validate_spec(spec)
        cmd_errors = [
            e for e in errors
            if "install_commands" in e or "start_commands" in e
        ]
        assert cmd_errors == [], (
            f"{entry_type} 入口不应检查 install/start_commands,实际: {cmd_errors}"
        )


def test_validate_spec_accepts_ssh_entry_with_both_commands_filled():
    """ssh 入口 install + start 都填了应通过。"""
    spec = _make_spec(
        entry_type="ssh",
        install_commands=("apt-get install -y nginx",),
        start_commands=("nginx -g 'daemon on;'",),
    )
    errors = validate_spec(spec)
    cmd_errors = [
        e for e in errors
        if "install_commands" in e or "start_commands" in e
    ]
    assert cmd_errors == [], (
        f"ssh 入口 install + start 都填应通过,实际: {cmd_errors}"
    )


# ============================================================
# Phase 3 G3.1-G3.7 社区版扩展(roadmap §3.1 高优先级 7 个对象)
# 2026-07-08 落地:每个对象验证 Spec 存在 + validate 通过 + 关键字段(image/ports/entry_type)
# ============================================================

@pytest.mark.parametrize("model_id,expected_image_substr,expected_business_port", [
    # G3.1 minio — wget 装 minio binary,9000 API
    ("minio", "ubuntu:22.04", 19000),
    # G3.2 zookeeper — apt 装 zookeeperd,2181 client
    ("zookeeper", "ubuntu:22.04", 12181),
    # G3.3 consul — apt 装 consul,8500 http
    ("consul", "ubuntu:22.04", 18500),
    # G3.4 etcd — apt 装 etcd-server,2379 client
    ("etcd", "ubuntu:22.04", 12379),
    # G3.5 memcached — apt 装 memcached,11211
    ("memcached", "ubuntu:22.04", 11211),
    # G3.6 openresty — 2026-07-08 装包失败降级,placeholder 落盘(同 dameng/ibmmq 模式)
    ("openresty", "ubuntu:22.04", 18081),
    # G3.7 haproxy — apt 装 haproxy,80
    ("haproxy", "ubuntu:22.04", 18082),
])
def test_phase3_object_in_model_specs(model_id, expected_image_substr, expected_business_port):
    """Phase 3 新增 7 个对象都在 catalog 中,镜像 + 端口正确。"""
    spec = lookup(model_id)
    assert spec.model_id == model_id
    assert expected_image_substr in spec.image, (
        f"{model_id} 镜像应为 ubuntu 路径(Phase 3 镜像策略统一),实际 {spec.image!r}"
    )
    assert expected_business_port in spec.ports.values(), (
        f"{model_id} 应暴露业务端口 {expected_business_port},实际 ports {spec.ports!r}"
    )
    assert spec.entry_type == "ssh", f"{model_id} 应走 ssh 入口"
    assert spec.init_script and spec.init_script.endswith("_default_discover.sh"), (
        f"{model_id} 应配 init_script(ssh 入口),实际 {spec.init_script!r}"
    )


@pytest.mark.parametrize("model_id", [
    "minio", "zookeeper", "consul", "etcd", "memcached", "openresty", "haproxy",
])
def test_phase3_object_spec_passes_validation(model_id):
    """Phase 3 新增 7 个对象单独跑 validate_spec 都通过。"""
    spec = lookup(model_id)
    errors = validate_spec(spec)
    assert errors == [], f"{model_id} validate_spec 应通过,实际: {errors}"


@pytest.mark.parametrize("model_id,key_package", [
    ("minio", "minio"),  # wget 下 binary
    ("zookeeper", "zookeeperd"),
    ("consul", "consul"),
    ("etcd", "etcd-server"),
    ("memcached", "memcached"),
    ("openresty", "openresty"),
    ("haproxy", "haproxy"),
])
def test_phase3_object_install_contains_key_package(model_id, key_package):
    """Phase 3 新增 7 个对象 install_commands 含关键包(防 Spec 改坏)。
    注:openresty 在 2026-07-08 装包多次失败后降级(同 dameng/ibmmq 模式),
    install_commands 故意 exit 1,只验证 Spec 仍可注册在 MODEL_SPECS 中。
    """
    spec = lookup(model_id)
    assert spec.install_commands, f"{model_id} 应填 install_commands"
    install_text = " ".join(spec.install_commands)
    # openresty 降级:install 故意 exit 1,只验证占位消息存在
    if model_id == "openresty":
        assert "exit 1" in install_text or "blocked" in install_text.lower(), (
            f"{model_id} 降级路径 install_commands 应含 blocked/exit 1,实际: {spec.install_commands!r}"
        )
    elif model_id == "minio":
        # minio 用 wget 下 binary,不是 apt 装
        assert "wget" in install_text and "minio" in install_text, (
            f"{model_id} 应 wget 下载 minio binary,实际: {spec.install_commands!r}"
        )
    else:
        assert key_package in install_text, (
            f"{model_id} install_commands 应含 {key_package!r},实际: {spec.install_commands!r}"
        )


def test_phase3_objects_total_count_is_7():
    """Phase 3 新增 7 个对象都在 MODEL_SPECS(roadmap §3.1 锁定 7 个)。
    2026-07-08 Phase 4 升级:21 → 31,改为校验对象数 ≥ 21。
    """
    phase3_ids = {"minio", "zookeeper", "consul", "etcd", "memcached", "openresty", "haproxy"}
    for mid in phase3_ids:
        assert mid in MODEL_SPECS, f"Phase 3 对象 {mid} 应在 MODEL_SPECS 中"
    # Phase 4 升级:21 → 31
    assert len(MODEL_SPECS) >= 21, f"MODEL_SPECS 数量应 ≥ 21(Phase 3 完成线),实际 {len(MODEL_SPECS)}"


# ============================================================
# Phase 4 G4.1-G4.10 中等优先级 10 对象(roadmap §3.2 有 plugin 的 10 个)
# 2026-07-08 落地:每个对象验证 Spec 存在 + validate 通过 + 关键字段
# 实际跑通:apache/squid 2 个真实采集;
# 降级 8 个:jboss/jetty/tongweb/keepalived/rocketmq(国内镜像/wget 阻塞)+
#           weblogic/websphere/tuxedo(license 不可达)
# ============================================================

@pytest.mark.parametrize("model_id,expected_image_substr,expected_business_port", [
    # G4.1 jboss/wildfly(降级,镜像不可达)
    ("jboss", "ubuntu:22.04", 18090),
    # G4.2 jetty(降级,ubuntu 22.04 apt 无 jetty9)
    ("jetty", "ubuntu:22.04", 18091),
    # G4.3 tongweb(降级,东方通 tarball 国内镜像不可达)
    ("tongweb", "ubuntu:22.04", 18092),
    # G4.4 weblogic(license 降级)
    ("weblogic", "ubuntu:22.04", 18093),
    # G4.5 websphere(license 降级)
    ("websphere", "ubuntu:22.04", 18095),
    # G4.6 apache(✅ 真实跑通)
    ("apache", "ubuntu:22.04", 18097),
    # G4.7 squid(✅ 真实跑通)
    ("squid", "ubuntu:22.04", 18098),
    # G4.8 keepalived(降级,容器内 VRRP multicast 受限)
    ("keepalived", "ubuntu:22.04", None),  # keepalived 无 host 端口
    # G4.9 rocketmq(降级,JVM 启动慢 + 32MB wget 阻塞)
    ("rocketmq", "ubuntu:22.04", 19876),
    # G4.10 tuxedo(license 降级)
    ("tuxedo", "ubuntu:22.04", 19860),
])
def test_phase4_object_in_model_specs(model_id, expected_image_substr, expected_business_port):
    """Phase 4 新增 10 个对象都在 catalog 中,镜像 + 端口正确。"""
    spec = lookup(model_id)
    assert spec.model_id == model_id
    assert expected_image_substr in spec.image, (
        f"{model_id} 镜像应为 ubuntu 路径(Phase 4 镜像策略统一),实际 {spec.image!r}"
    )
    if expected_business_port is not None:
        assert expected_business_port in spec.ports.values(), (
            f"{model_id} 应暴露业务端口 {expected_business_port},实际 ports {spec.ports!r}"
        )
    assert spec.entry_type == "ssh", f"{model_id} 应走 ssh 入口"
    assert spec.init_script and spec.init_script.endswith("_default_discover.sh"), (
        f"{model_id} 应配 init_script(ssh 入口),实际 {spec.init_script!r}"
    )


@pytest.mark.parametrize("model_id", [
    "jboss", "jetty", "tongweb", "weblogic", "websphere",
    "apache", "squid", "keepalived", "rocketmq", "tuxedo",
])
def test_phase4_object_spec_passes_validation(model_id):
    """Phase 4 新增 10 个对象单独跑 validate_spec 都通过。"""
    spec = lookup(model_id)
    errors = validate_spec(spec)
    assert errors == [], f"{model_id} validate_spec 应通过,实际: {errors}"


@pytest.mark.parametrize("model_id,key_package", [
    # JMX 类 — 全部降级(2026-07-08 装包失败)
    ("jboss", "exit 1"),
    ("jetty", "exit 1"),
    ("tongweb", "exit 1"),
    # license 类 — 占位占位
    ("weblogic", "exit 1"),
    ("websphere", "exit 1"),
    # apt 装类 — 真实跑通
    ("apache", "apache2"),
    ("squid", "squid"),
    # 降级
    ("keepalived", "exit 1"),
    ("rocketmq", "exit 1"),
    ("tuxedo", "exit 1"),
])
def test_phase4_object_install_contains_key_marker(model_id, key_package):
    """Phase 4 新增 10 个对象 install_commands 含关键包/降级 marker。"""
    spec = lookup(model_id)
    assert spec.install_commands, f"{model_id} 应填 install_commands"
    install_text = " ".join(spec.install_commands)
    if key_package == "exit 1":
        # 降级对象:install 应故意 exit 1
        assert "exit 1" in install_text, (
            f"{model_id} 降级对象 install 应含 'exit 1',实际: {spec.install_commands!r}"
        )
    else:
        assert key_package in install_text, (
            f"{model_id} install_commands 应含 {key_package!r},实际: {spec.install_commands!r}"
        )


def test_phase4_objects_total_count_is_10():
    """Phase 4 新增 10 个对象都在 MODEL_SPECS(roadmap §3.2 锁定 10 个有 plugin 的)。"""
    phase4_ids = {
        "jboss", "jetty", "tongweb", "weblogic", "websphere",
        "apache", "squid", "keepalived", "rocketmq", "tuxedo",
    }
    for mid in phase4_ids:
        assert mid in MODEL_SPECS, f"Phase 4 对象 {mid} 应在 MODEL_SPECS 中"
    # 验证总数:21(Phase 1/2/3) + 10(Phase 4) + 12(Phase 5.1 国产化 JOB) + 11(Phase 5.2 protocol) + 3(Phase 5.3 集群降级) = 57
    assert len(MODEL_SPECS) == 57, f"MODEL_SPECS 数量应为 57,实际 {len(MODEL_SPECS)}"