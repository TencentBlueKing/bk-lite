# -*- coding: utf-8 -*-
"""
命令行入口:python -m agents.stargazer.tests.collect_fixtures.cli <model>|--all|--list

完整流水线:start → wait → exec_init → collect_once → dump → remove（try/finally）。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

# 让 import 能找到 stargazer 根目录模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures.catalog import lookup, list_models  # noqa: E402
from tests.collect_fixtures.docker_lifecycle import (  # noqa: E402
    bootstrap_sshd_in_container,
    exec_init,
    install_services,
    remove,
    start_container,
    start_services,
    wait_ready,
    wait_service_ready,
    wait_ssh_ready,
)
from tests.collect_fixtures.dump import dump  # noqa: E402
from tests.collect_fixtures.run_collector import collect_once  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m agents.stargazer.tests.collect_fixtures.cli",
        description="CMDB 数据库/中间件采集执行层真实环境 Mock 数据采集工具",
    )
    p.add_argument("model", nargs="?", help="model_id（如 mysql）")
    p.add_argument("--list", action="store_true", help="列出所有可用 model_id")
    p.add_argument("--all", action="store_true", help="逐个跑所有 model_id")
    p.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="并发 worker 数(仅 --all 时生效,默认 1 串行)。建议 2-4,过高会增加 docker daemon 压力",
    )
    p.add_argument(
        "--keep-container",
        action="store_true",
        help="采集完成后不销毁容器（debug 用）",
    )
    return p


def _dispatch_one(model_id: str, keep_container: bool = False) -> int:
    """处理一个 model,返回 0=成功 / 非0=失败。"""
    try:
        spec = lookup(model_id)
    except KeyError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    print(f"==> [{model_id}] 启动容器 ({spec.image})")
    handle = None
    try:
        privileged = bool(spec.vm_privileged)  # 从 spec 读
        handle = start_container(spec, privileged=privileged)
        print(f"    container_id = {handle.container.short_id}")

        if spec.entry_type == "ssh":
            # ssh 入口：bootstrap sshd (docker exec) → wait ssh → install 服务 → start → wait ready
            print(f"==> [{model_id}] bootstrap sshd (docker exec)")
            bootstrap_sshd_in_container(handle, spec)

            print(f"==> [{model_id}] 等待 SSH 就绪")
            wait_ssh_ready(handle, spec, spec.vm_ssh_password)

            if spec.install_commands:
                print(f"==> [{model_id}] 安装服务")
                install_services(handle, spec, spec.vm_ssh_password)

            if spec.start_commands:
                print(f"==> [{model_id}] 启动服务")
                start_services(handle, spec, spec.vm_ssh_password)

            if spec.ready_check:
                print(f"==> [{model_id}] 等待服务就绪")
                wait_service_ready(handle, spec, spec.vm_ssh_password)
        else:
            print(f"==> [{model_id}] 等待端口就绪")
            wait_ready(handle, spec)
            # 给服务额外时间初始化(尤其 mysql 还要 30-60s 才接受连接)
            if model_id == "mysql":
                time.sleep(45)
            elif model_id == "postgresql":
                time.sleep(5)

            if spec.init_script and spec.entry_type != "shell":
                print(f"==> [{model_id}] 执行 init 脚本")
                exec_init(handle, spec)

        print(f"==> [{model_id}] 调 collector")
        if spec.entry_type in ("shell", "ssh"):
            raw = collect_once(spec, handle=handle)
        else:
            raw = collect_once(spec)

        print(f"==> [{model_id}] 落盘")
        out = dump(
            model_id=spec.model_id,
            raw_stdout=raw,
            container_meta={
                "container_id": handle.container.short_id,
                "image": spec.image,
            },
            params=spec.collector_kwargs,
        )
        print(f"    ✅ {out}")
        return 0
    except Exception as e:
        print(f"❌ [{model_id}] 失败: {e}", file=sys.stderr)
        return 1
    finally:
        if handle is not None and not keep_container:
            print(f"==> [{model_id}] 销毁容器")
            remove(handle)


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list:
        print("可用 model_id（已排序）:")
        for m in list_models():
            print(m)
        return 0

    if not args.model and not args.all:
        _build_parser().print_help()
        return 2

    if args.all:
        if args.parallel <= 1:
            # 串行(原行为)
            rc = 0
            for m in list_models():
                sub_rc = _dispatch_one(m, keep_container=args.keep_container)
                rc = rc or sub_rc
            return rc

        # 并发(Phase 2 G2 副产物:14 对象 fixture 采集耗时从 30+ 分钟降到 10-15 分钟)
        # 用 ThreadPoolExecutor(每个 _dispatch_one 是 IO 密集型:起容器 + 等端口 + ssh + 装包)
        # 每个 model_id 独立容器 + 独立 host port(已在 catalog 隔离),无共享状态冲突
        from concurrent.futures import ThreadPoolExecutor, as_completed

        parallel = args.parallel
        models = list_models()
        print(f"==> 并发模式: {parallel} workers,共 {len(models)} 个对象")
        rc = 0
        results = {}  # model_id -> rc
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            futures = {
                ex.submit(_dispatch_one, m, keep_container=args.keep_container): m
                for m in models
            }
            for fut in as_completed(futures):
                m = futures[fut]
                try:
                    sub_rc = fut.result()
                except Exception as e:
                    print(f"❌ [{m}] 异常: {e}", file=sys.stderr)
                    sub_rc = 1
                results[m] = sub_rc
                rc = rc or sub_rc

        # 按 model_id 排序打印汇总(便于 review)
        print("\n==> 汇总(按 model_id 字母序):")
        for m in sorted(results.keys()):
            mark = "✅" if results[m] == 0 else "❌"
            print(f"    {mark} {m}")
        return rc

    return _dispatch_one(args.model, keep_container=args.keep_container)


if __name__ == "__main__":
    sys.exit(main())