# 启动作业 Celery worker。只消费 job 队列。
# 和 API、Beat 使用同一套数据库与 Broker。本环境只运行一个 Beat。
$ErrorActionPreference = "Stop"
$ServerDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ServerDir

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv 未安装。请先在本机安装并加入 PATH。"
}

$concurrency = if ($env:JOB_CELERY_CONCURRENCY) { $env:JOB_CELERY_CONCURRENCY } else { "2" }
$maxTasks = if ($env:CELERY_MAX_TASKS_PER_CHILD) { $env:CELERY_MAX_TASKS_PER_CHILD } else { "200" }
$maxMemory = if ($env:CELERY_MAX_MEMORY_PER_CHILD) { $env:CELERY_MAX_MEMORY_PER_CHILD } else { "512000" }

uv run celery -A apps.core.celery worker `
    --loglevel=info `
    --pool prefork `
    --concurrency=$concurrency `
    --max-tasks-per-child=$maxTasks `
    --max-memory-per-child=$maxMemory `
    -Q job `
    -n "job@%h"
