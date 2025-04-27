import os

from loguru import logger

from src.tools.jenkins_tools import list_jenkins_jobs


def test_list_jenkins_job():
    result = list_jenkins_jobs.run("", config={
        "configurable": {
            "jenkins_url": os.environ['TEST_JENKINS_URL'],
            "jenkins_username": os.environ['TEST_JENKINS_USERNAME'],
            "jenkins_password": os.environ['TEST_JENKINS_PASSWORD'],
        }
    })
    logger.info(result)
