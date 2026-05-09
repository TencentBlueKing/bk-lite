Feature: Local SCP transfer execution
  The local executor should preserve successful SCP output and failure diagnostics
  from an operator's point of view.

  Background:
    Given a local SCP executor instance
    And shell is "sh"

  Scenario: Happy path SCP transfer returns merged stdout and stderr
    Given scp command is "printf 'copied'; printf ' stderr-note' 1>&2 # scp"
    And transfer log context is "upload root@10.0.0.1:22 /tmp/a -> /tmp/b [auth=password kind=file size=6B name=a]"
    And execute timeout is 3 seconds
    When the command is executed locally
    Then the execution succeeds
    And combined output contains "copied"
    And combined output contains "stderr-note"

  Scenario: Corner case transfer timeout surfaces timeout code
    Given scp command is "sleep 2 # scp"
    And transfer log context is "upload timeout"
    And execute timeout is 1 seconds
    When the command is executed locally
    Then the execution fails with code "timeout"
    And error contains "timed out"

  Scenario: Corner case host key verification failure keeps diagnostic output
    Given scp command is "printf 'Host key verification failed'; exit 1 # scp"
    And transfer log context is "download host-key"
    And execute timeout is 3 seconds
    When the command is executed locally
    Then the execution fails with code "execution_failure"
    And combined output contains "Host key verification failed"
    And error contains "exit code 1"

  Scenario: Corner case auth failure keeps permission denied output
    Given scp command is "printf 'Permission denied'; exit 1 # scp"
    And transfer log context is "download auth-failure"
    And execute timeout is 3 seconds
    When the command is executed locally
    Then the execution fails with code "execution_failure"
    And combined output contains "Permission denied"
    And error contains "exit code 1"

  Scenario: Corner case missing sshpass is preserved for operator diagnosis
    Given scp command is "printf 'sshpass: command not found'; exit 127 # scp"
    And transfer log context is "download missing-sshpass"
    And execute timeout is 3 seconds
    When the command is executed locally
    Then the execution fails with code "execution_failure"
    And combined output contains "sshpass: command not found"
    And error contains "exit code 127"

  Scenario: Corner case path not found keeps remote path hint
    Given scp command is "printf 'No such file or directory'; exit 1 # scp"
    And transfer log context is "download missing-path"
    And execute timeout is 3 seconds
    When the command is executed locally
    Then the execution fails with code "execution_failure"
    And combined output contains "No such file or directory"
    And error contains "exit code 1"
