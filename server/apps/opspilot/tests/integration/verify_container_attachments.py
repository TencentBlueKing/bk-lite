"""Real Docker + temporary MinIO + SQLite vertical verification (no LLM/storage mocks).

Run from server: PYTHONPATH=. .venv/bin/python apps/opspilot/tests/integration/verify_container_attachments.py
Requires the production sandbox image, Docker, and the minio binary on PATH.
Only an isolated temporary bucket/database are used. Credentials are ephemeral.
"""
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import boto3
import requests


def main():
    with tempfile.TemporaryDirectory(prefix="opspilot-minio-test-") as directory:
        with socket.socket() as listener:
            listener.bind(("0.0.0.0", 0))
            port = listener.getsockname()[1]
        # An address reachable both by the server and the execution container.
        host = os.getenv("OPSPILOT_TEST_STORAGE_HOST") or socket.gethostbyname(socket.gethostname())
        endpoint = f"{host}:{port}"
        access = "test" + secrets.token_hex(8)
        secret = secrets.token_hex(24)
        process = subprocess.Popen(
            ["minio", "server", directory, "--address", f"0.0.0.0:{port}"],
            env=dict(os.environ, MINIO_ROOT_USER=access, MINIO_ROOT_PASSWORD=secret),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                try:
                    if requests.get(f"http://{endpoint}/minio/health/ready", timeout=0.2).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("temporary MinIO did not become ready")
            boto3.client(
                "s3", endpoint_url=f"http://{endpoint}", aws_access_key_id=access, aws_secret_access_key=secret, region_name="us-east-1"
            ).create_bucket(Bucket="munchkin-private")
            os.environ.update(
                DB_ENGINE="sqlite",
                DB_NAME=str(Path(directory) / "verification.sqlite3"),
                SECRET_KEY=secrets.token_hex(32),
                ENABLE_CELERY="true",
                DJANGO_SETTINGS_MODULE="settings",
                MINIO_ENDPOINT=endpoint,
                MINIO_USE_HTTPS="0",
                MINIO_ACCESS_KEY=access,
                MINIO_SECRET_KEY=secret,
            )
            verify()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def verify():
    import django

    django.setup()
    from django.core import signing
    from django.core.files.base import ContentFile
    from django.db import connection

    from apps.opspilot.metis.llm.chain.skill_sandbox import SkillSandboxMixin
    from apps.opspilot.metis.llm.tools.attachment.generate_attachment import generate_attachment_file
    from apps.opspilot.models import ChatAttachment, LLMSkill, SkillConversation, SkillConversationMessage, WorkflowAttachmentAsset
    from apps.opspilot.services.python_sandbox.attachments import issue_attachment_grant, resolve_attachment_grant
    from apps.opspilot.services.python_sandbox.runtime import PythonSandbox
    from apps.opspilot.services.workflow_attachment_service import resolve_signed_attachment_token

    # Build only the model tables used by this isolated verification. This avoids
    # unrelated application migrations and still exercises actual ORM/storage.
    created = set()

    def create(model, editor):
        if model in created:
            return
        created.add(model)
        for field in model._meta.local_fields:
            if field.is_relation and field.related_model:
                create(field.related_model, editor)
        editor.create_model(model)

    with connection.schema_editor() as editor:
        for model in (ChatAttachment, WorkflowAttachmentAsset):
            create(model, editor)

    skill = LLMSkill(name="sandbox verification")
    LLMSkill.objects.bulk_create([skill])
    conversation = SkillConversation.objects.create(session_id="session-a", skill=skill, external_user_id="alice")
    other = SkillConversation.objects.create(session_id="session-b", skill=skill, external_user_id="alice")
    source = b"item,value\nalpha,2\nbeta,5\n"

    def upload(owner="alice", team="team-a", conv=conversation):
        return ChatAttachment.objects.create(
            file=ContentFile(source, name="source.csv"),
            original_name="source.csv",
            mime_type="text/csv",
            size=len(source),
            status="ready",
            owner_key=owner,
            team_id=team,
            conversation=conv,
        )

    allowed = upload()
    denied = [upload(owner="bob"), upload(team="team-b"), upload(conv=other)]
    token = issue_attachment_grant(owner_key="alice", team_id="team-a", conversation=conversation)
    entries = resolve_attachment_grant(token)
    assert [item["id"] for item in entries] == [f"upload-{allowed.pk}"]
    try:
        resolve_attachment_grant(token + "-invalid")
    except signing.BadSignature:
        pass
    else:
        raise AssertionError("forged grant accepted")
    assert requests.put(entries[0]["url"], data=b"overwrite", timeout=5).status_code == 403
    print("PASS: conversation/owner/team isolation, forged grant rejected, object is GET-only")

    runtime = PythonSandbox(attachments=entries)
    container_id = None
    try:
        package = {
            "name": "modify-csv",
            "scripts": {
                "modify.py": (
                    "import csv, pathlib, sys\n"
                    "rows=list(csv.DictReader(open(sys.argv[1])))\n"
                    'pathlib.Path("/workspace/report.html").write_text("<html><meta charset=\\"utf-8\\"><body>合计："'
                    '+str(sum(int(r["value"]) for r in rows))+"</body></html>")\n'
                )
            },
        }
        backend, sources, _ = SkillSandboxMixin()._build_skill_backend_and_sources(
            SimpleNamespace(extra_config={}),
            packages=[package],
            sandbox=runtime,
        )
        container_id = runtime._container.id
        assert sources == ["/workspace/skills/"]
        assert runtime.execute("import pathlib; pathlib.Path('/workspace/attachments/downloads').exists()") == "False"
        for item in denied:
            assert backend.execute(f"python /workspace/attachments/read.py upload-{item.pk}").exit_code != 0
        import asyncio
        import json
        import shlex

        from deepagents.middleware.filesystem import FilesystemMiddleware
        from langchain.agents import create_agent
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        from apps.opspilot.metis.llm.tools.python.executor import python_execute_direct
        from apps.opspilot.metis.llm.tools.shell.shell_tools import shell_execute

        class ScriptedModel(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

        path = f"/workspace/attachments/downloads/upload-{allowed.pk}/source.csv"
        url_code = "import json; print(json.load(open('/workspace/attachments/index.json'))[0]['url'])"
        calls = [
            (
                "shell_execute",
                {
                    "commands": [
                        "url=$(python -c " + shlex.quote(url_code) + ")",
                        'curl -fsS "$url" -o /workspace/curl-source.csv',
                        f"python /workspace/attachments/read.py upload-{allowed.pk}",
                    ]
                },
            ),
            ("execute", {"command": "python /skills/modify-csv/scripts/modify.py " + shlex.quote(path)}),
            ("python_execute_direct", {"code": "open('/workspace/report.html').read()"}),
            ("generate_attachment_file", {"filename": "report.html", "file_type": "html", "sandbox_path": "/workspace/report.html"}),
        ]
        responses = [
            AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(index)}]) for index, (name, args) in enumerate(calls)
        ] + [AIMessage(content="完成")]
        agent = create_agent(
            model=ScriptedModel(responses=responses),
            tools=[shell_execute, python_execute_direct, generate_attachment_file],
            middleware=[FilesystemMiddleware(backend=backend)],
        )
        state = asyncio.run(
            agent.ainvoke(
                {"messages": [HumanMessage(content="读取会话附件，制作 HTML 文档并保存")]},
                config={"configurable": {"execution_id": "sandbox-test", "python_sandbox": runtime}},
            )
        )
        outputs = [message for message in state["messages"] if isinstance(message, ToolMessage)]
        assert len(outputs) == 4 and all(message.status != "error" for message in outputs)
        assert runtime.read_workspace_file("/workspace/curl-source.csv") == source
        assert "合计：7" in outputs[2].content
        result = json.loads(outputs[3].content)
        saved = WorkflowAttachmentAsset.objects.get(pk=result["attachment_asset_id"])
        expected = runtime.read_workspace_file("/workspace/report.html")
        with saved.file.open("rb") as stream:
            assert stream.read() == expected
        download_token = result["file_url"].rstrip("/").rsplit("/", 1)[-1]
        assert resolve_signed_attachment_token(download_token).pk == saved.pk
        with allowed.file.open("rb") as stream:
            assert stream.read() == source
        import json

        from apps.opspilot.services.skill_channel_chat_service import assemble_assistant_persist_content

        persisted = assemble_assistant_persist_content(
            [
                {"type": "TOOL_CALL_START", "toolCallId": "attachment", "toolCallName": "generate_attachment_file"},
                {"type": "TOOL_CALL_RESULT", "toolCallId": "attachment", "content": json.dumps(result)},
            ]
        )
        SkillConversationMessage.objects.create(conversation=conversation, role="assistant", content=persisted)
        print("PASS: shell_execute curl/authorized MinIO read -> skill execute modification -> Python read -> real attachment storage/download")
    finally:
        runtime.close()
    import docker

    try:
        docker.from_env().containers.get(container_id)
    except docker.errors.NotFound:
        pass
    else:
        raise AssertionError("run container leaked")

    entries = resolve_attachment_grant(issue_attachment_grant(owner_key="alice", team_id="team-a", conversation=conversation))
    generated = next(item for item in entries if item["id"] == f"generated-{saved.pk}")
    assert not resolve_attachment_grant(issue_attachment_grant(owner_key="alice", team_id="team-a", conversation=other))[0]["id"].startswith(
        "generated-"
    )
    second = PythonSandbox(attachments=entries)
    try:
        fetched = second.execute_command("python /workspace/attachments/read.py " + generated["id"])
        assert fetched.exit_code == 0
        script = (
            "from pathlib import Path; p=Path("
            + repr(fetched.output)
            + '); Path("/workspace/report.html").write_text(p.read_text().replace("合计", "总计"))'
        )
        second.execute(script)
        result2 = generate_attachment_file.invoke(
            {"filename": "report.html", "file_type": "html", "sandbox_path": "/workspace/report.html"},
            config={
                "configurable": {
                    "execution_id": "sandbox-test-2",
                    "python_sandbox": second,
                    "attachment_versioning": True,
                    "prior_attachment_filenames": [saved.filename],
                }
            },
        )
        revised = WorkflowAttachmentAsset.objects.get(pk=result2["attachment_asset_id"])
        assert revised.pk != saved.pk
        with revised.file.open("rb") as stream:
            assert "总计：7" in stream.read().decode()
        with saved.file.open("rb") as stream:
            assert stream.read() == expected
        print("PASS: next conversation turn -> authorized generated attachment -> second modification -> new stored version; originals preserved")
    finally:
        second.close()
    print("PASS: containers removed after both runs")


if __name__ == "__main__":
    main()
