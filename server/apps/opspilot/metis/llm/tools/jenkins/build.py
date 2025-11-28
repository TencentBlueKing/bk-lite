from typing import Optional

import jenkins

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


def get_client(config: RunnableConfig):
    client = jenkins.Jenkins(config['configurable']['jenkins_url'],
                             username=config['configurable']['jenkins_username'],
                             password=config['configurable']['jenkins_password'])
    return client


@tool()
def list_jenkins_jobs(config: RunnableConfig):
    """
    列出Jenkins构建任务，这个工具用户帮助用户获取Jenkins构建任务列表，当用户构建目标不明确的时候，
    直接使用此工具给用户提出建议
    """
    client = get_client(config)
    return client.get_jobs()


@tool(parse_docstring=True)
def trigger_jenkins_build(job_name: str, parameters: Optional[dict], config: RunnableConfig):
    """
    这个工具用于触发Jenkins构建任务.
        要求:
            1. 当构建目标不明确的时候，不要执行任务，告诉与这个任务名字相似的任务
            2. 不允许构建已禁用的任务

    Args:
        job_name: Name of the job to build
        parameters: Optional build parameters as a dictionary (e.g. {"param1": "value1"})

    Returns:
        Dictionary containing build information including the build number
    """
    if not isinstance(job_name, str):
        raise ValueError(f"job_name must be a string, got {type(job_name)}")
    if parameters is not None and not isinstance(parameters, dict):
        raise ValueError(
            f"parameters must be a dictionary or None, got {type(parameters)}"
        )

    client = get_client(config)

    try:
        job_info = client.get_job_info(job_name)
        if not job_info:
            raise ValueError(f"Job {job_name} not found")
    except Exception as e:
        raise ValueError(f"Error checking job {job_name}: {str(e)}")

    try:
        # Get the next build number before triggering
        next_build_number = job_info['nextBuildNumber']

        # Trigger the build
        queue_id = client.build_job(job_name, parameters=parameters)

        return {
            "status": "triggered",
            "job_name": job_name,
            "queue_id": queue_id,
            "build_number": next_build_number,
            "job_url": job_info["url"],
            "build_url": f"{job_info['url']}{next_build_number}/"
        }
    except Exception as e:
        raise ValueError(f"Error triggering build for {job_name}: {str(e)}")
