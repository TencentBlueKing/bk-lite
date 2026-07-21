import base64
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from core.task_queue_cleanup import (
    CleanupRestoreError,
    _payload_digest,
    backup_and_apply_cleanup,
    build_cleanup_plan,
    restore_cleanup_backup,
)
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError


@pytest.fixture
def real_redis(tmp_path):
    redis_server = shutil.which("redis-server")
    if redis_server is None:
        pytest.skip("redis-server is not installed")

    socket_path = Path("/tmp") / (
        f"stargazer-redis-{secrets.token_hex(6)}.sock"
    )
    process = subprocess.Popen(
        [
            redis_server,
            "--save",
            "",
            "--appendonly",
            "no",
            "--port",
            "0",
            "--unixsocket",
            str(socket_path),
            "--unixsocketperm",
            "700",
            "--dir",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = Redis(
        unix_socket_path=str(socket_path), db=15, decode_responses=False,
    )
    try:
        for _attempt in range(100):
            try:
                if client.ping():
                    break
            except (RedisConnectionError, OSError):
                time.sleep(0.01)
        else:
            pytest.fail("temporary redis-server did not start")
        yield client
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=5)
        socket_path.unlink(missing_ok=True)


def test_real_redis_cleanup_backup_and_restore_round_trip(
    real_redis, tmp_path,
):
    job_id = b"real-job"
    marker_key = b"task:running:real-task"
    job_key = b"arq:job:real-job"
    retry_key = b"arq:retry:real-job"
    real_redis.zadd(b"arq:queue", {job_id: 1234.5})
    real_redis.set(marker_key, job_id, px=90_000)
    real_redis.set(job_key, b"serialized-real-job", px=80_000)
    real_redis.set(retry_key, b"2", px=70_000)

    plan = build_cleanup_plan(
        real_redis, all_pending=False, include_in_progress=False
    )
    backup_path, cleanup_result = backup_and_apply_cleanup(
        real_redis, plan, backup_dir=tmp_path / "backups", redis_db=15,
    )

    assert cleanup_result.deleted_job_count == 1
    assert real_redis.zscore(b"arq:queue", job_id) is None
    assert real_redis.mget(marker_key, job_key, retry_key) == [None] * 3

    restore_result = restore_cleanup_backup(
        real_redis, backup_path=backup_path, redis_db=15
    )

    assert restore_result.restored_key_count == 3
    assert restore_result.restored_queue_job_count == 1
    assert real_redis.zscore(b"arq:queue", job_id) == 1234.5
    assert real_redis.mget(marker_key, job_key, retry_key) == [
        job_id,
        b"serialized-real-job",
        b"2",
    ]
    assert 0 < real_redis.pttl(marker_key) <= 90_000
    assert 0 < real_redis.pttl(job_key) <= 80_000
    assert 0 < real_redis.pttl(retry_key) <= 70_000


def test_damaged_dump_leaves_target_namespace_untouched(
    real_redis, tmp_path,
):
    job_id = b"damaged-job"
    marker_key = b"task:running:damaged-task"
    job_key = b"arq:job:damaged-job"
    real_redis.zadd(b"arq:queue", {job_id: 5678.0})
    real_redis.set(marker_key, job_id, px=90_000)
    real_redis.set(job_key, b"serialized-damaged-job", px=80_000)
    plan = build_cleanup_plan(
        real_redis, all_pending=False, include_in_progress=False
    )
    backup_path, _result = backup_and_apply_cleanup(
        real_redis, plan, backup_dir=tmp_path / "backups", redis_db=15,
    )
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    payload["keys"][marker_key.decode()]["dump"] = base64.b64encode(
        b"not-a-valid-redis-dump"
    ).decode()
    payload["content_sha256"] = _payload_digest(payload)
    backup_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CleanupRestoreError):
        restore_cleanup_backup(
            real_redis, backup_path=backup_path, redis_db=15
        )

    assert real_redis.zscore(b"arq:queue", job_id) is None
    assert real_redis.mget(marker_key, job_key) == [None, None]
    assert (
        list(real_redis.scan_iter(match=b"stargazer:task-queue-restore:tmp:*"))
        == []
    )
