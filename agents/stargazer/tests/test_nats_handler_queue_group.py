"""锁定 NATS handler 的队列组契约。

多 Sanic worker 下每个 worker 进程都会订阅同一 subject。NATS 对没有队列组的
订阅是广播语义：同一请求会被每个 worker 各执行一遍（debug_snmp / debug_ipmi
会因此对目标设备重复探测），而发起方只取第一个响应，故障不可见。
"""

import ast
import pathlib

import pytest

NATS_SERVER_PATH = pathlib.Path(__file__).resolve().parents[1] / "service" / "nats_server.py"


def _register_handler_calls():
    tree = ast.parse(NATS_SERVER_PATH.read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "register_handler":
                calls.append((node.name, decorator))
    return calls


def test_register_handler_calls_are_discovered():
    # 守住解析本身：handler 全被改名或装饰器换写法时，下面的断言不能静默通过。
    assert len(_register_handler_calls()) >= 6


@pytest.mark.parametrize("handler_name,decorator", _register_handler_calls())
def test_every_handler_declares_queue_group(handler_name, decorator):
    queue_keywords = [kw for kw in decorator.keywords if kw.arg == "queue"]
    assert queue_keywords, f"handler {handler_name} 缺少 queue 队列组，多 worker 下会被广播重复执行"


def test_queue_group_matches_its_own_subject():
    """用 _handler_queue() 时，传入的必须是本 handler 自己的 subject。

    直接写字面量队列组名同样合法：NATS 的队列组按 (subject, queue) 二元组划分，
    subject 不同的 handler 即使队列组重名也各自成组，不会互相抢消息。因此这里
    只校验辅助函数的用法，"是否声明了 queue"由上面的用例统一覆盖。
    """
    for handler_name, decorator in _register_handler_calls():
        subject_arg = decorator.args[0]
        queue_arg = next(kw.value for kw in decorator.keywords if kw.arg == "queue")
        if not isinstance(subject_arg, ast.Constant) or not isinstance(queue_arg, ast.Call):
            continue  # subject 用模块常量、或 queue 是字面量/自带辅助函数时无法静态比对
        if getattr(queue_arg.func, "id", None) != "_handler_queue":
            continue  # 其它辅助函数自行保证命名
        assert queue_arg.args[0].value == subject_arg.value, f"{handler_name} 的队列组名与自身 subject 不一致"


def test_handler_queue_uses_full_subject():
    """队列组名沿用完整 subject，与 host_remote.callback 的既有惯例一致。"""
    import os

    from core.collection.host_remote import callback

    service_name = callback.get_stargazer_service_name()
    assert service_name == f"{os.getenv('NATS_INSTANCE_ID', 'default')}_stargazer"
    # host_remote.callback 的 queue 即完整 subject，新 handler 必须遵循同一格式
    assert callback.get_host_remote_callback_queue() == callback.get_host_remote_callback_subject()
