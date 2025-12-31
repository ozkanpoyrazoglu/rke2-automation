import subprocess
import json
import tempfile
import os
from typing import List
from app.models import Credential, CredentialType
from app.schemas import HostInput, AccessCheckResponse, HostCheckResult
from app.services.encryption_service import decrypt_secret

async def run_access_check(credential: Credential, hosts: List[HostInput]) -> AccessCheckResponse:
    """
    Run access check playbook to validate SSH connectivity and permissions
    """
    # Decrypt credential
    secret = decrypt_secret(credential.encrypted_secret)

    # Use shared volume paths that both backend and ansible-runner can access
    import uuid
    check_id = str(uuid.uuid4())[:8]
    key_path = f"/tmp/ansible/check_{check_id}.key"
    inv_path = f"/tmp/ansible/check_{check_id}.ini"

    try:
        # Write credential file
        if credential.credential_type == CredentialType.SSH_KEY:
            with open(key_path, 'w') as f:
                f.write(secret)
            os.chmod(key_path, 0o600)

        # Write inventory file
        inventory_content = generate_inventory(hosts, credential.username)
        with open(inv_path, 'w') as f:
            f.write(inventory_content)

        # Execute check_access playbook via ansible-runner container
        cmd = [
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "ansible-playbook",
            "/ansible/playbooks/check_access.yml",
            "-i", inv_path,
            "--private-key", key_path,
            "-e", f"ansible_user={credential.username}"
        ]

        if credential.credential_type == CredentialType.SSH_PASSWORD:
            # Use sshpass for password auth
            cmd.extend(["--extra-vars", f"ansible_password={secret}"])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        # Parse results from playbook output
        results = parse_access_check_output(result.stdout, result.stderr, result.returncode, hosts)

        overall_status = "success" if all(r.status == "ok" for r in results) else "failed"

        return AccessCheckResponse(
            overall_status=overall_status,
            results=results
        )

    except Exception as e:
        # Return error results for all hosts
        error_results = [
            HostCheckResult(
                hostname=host.hostname,
                ip=host.ip,
                status="failed",
                ssh_reachable=False,
                sudo_available=False,
                os_compatible=False,
                error=f"Check failed: {str(e)}"
            )
            for host in hosts
        ]
        return AccessCheckResponse(
            overall_status="failed",
            results=error_results
        )

    finally:
        # Securely delete temporary files
        if os.path.exists(key_path):
            os.remove(key_path)
        if os.path.exists(inv_path):
            os.remove(inv_path)

def generate_inventory(hosts: List[HostInput], username: str) -> str:
    """
    Generate Ansible inventory from host list
    """
    lines = ["[check_hosts]"]
    for host in hosts:
        lines.append(f"{host.hostname} ansible_host={host.ip} ansible_user={username}")
    return "\n".join(lines)

def parse_access_check_output(stdout: str, stderr: str, returncode: int, hosts: List[HostInput]) -> List[HostCheckResult]:
    """
    Parse Ansible playbook output to extract check results
    """
    results = []
    output = stdout + "\n" + stderr

    for host in hosts:
        # Default to failed
        ssh_reachable = False
        sudo_available = False
        os_compatible = False
        error_msg = None

        # Check if host is in output (means Ansible tried to connect)
        if host.hostname in output or host.ip in output:
            # Check for unreachable
            if "unreachable=" in output and "unreachable=0" not in output:
                error_msg = "Host unreachable - check network connectivity"
            elif "UNREACHABLE!" in output:
                error_msg = "SSH connection failed - verify host is up and SSH is running"
            elif "Authentication failed" in output or "Permission denied" in output:
                error_msg = "SSH authentication failed - verify credentials"
            else:
                # Host was reachable
                ssh_reachable = True

                # Check for sudo (look for whoami task returning root)
                if "whoami" in output and ("root" in output or "ok=" in output):
                    sudo_available = True
                elif "FAILED" in output and "become" in output.lower():
                    error_msg = "Sudo not available or password required"

                # Check for OS compatibility
                if "compatible" in output.lower():
                    if "success" in output.lower() or "ok" in output.lower():
                        os_compatible = True
                    else:
                        error_msg = "OS not compatible"
                else:
                    # Assume OS is compatible if no explicit check failed
                    os_compatible = True
        else:
            # Host not in output at all
            error_msg = "Host not processed by Ansible"

        # Determine overall status
        if ssh_reachable and sudo_available and os_compatible:
            status = "ok"
            error_msg = None
        else:
            status = "failed"
            if not error_msg:
                error_msg = f"Checks: SSH={ssh_reachable}, Sudo={sudo_available}, OS={os_compatible}"

        result = HostCheckResult(
            hostname=host.hostname,
            ip=host.ip,
            status=status,
            ssh_reachable=ssh_reachable,
            sudo_available=sudo_available,
            os_compatible=os_compatible,
            error=error_msg
        )
        results.append(result)

    # If no results and there was an error, add generic failure
    if not results and returncode != 0:
        for host in hosts:
            results.append(HostCheckResult(
                hostname=host.hostname,
                ip=host.ip,
                status="failed",
                ssh_reachable=False,
                sudo_available=False,
                os_compatible=False,
                error=f"Playbook execution failed (exit code {returncode})"
            ))

    return results
