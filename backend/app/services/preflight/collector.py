"""
Pre-flight Check Collector
Gathers upgrade-readiness data from RKE2 cluster nodes
"""

import json
import subprocess
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from .schema import (
    PreflightReport, ClusterMetadata, NodeInfo, CheckResult,
    EtcdHealth, CertificateInfo, KubernetesHealth, NetworkHealth, StorageHealth
)


class PreflightCollector:
    """Collects pre-flight check data from RKE2 cluster"""

    def __init__(self, cluster_id: int, cluster_name: str, kubeconfig: str, target_version: Optional[str] = None):
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self.kubeconfig = kubeconfig
        self.target_version = target_version  # Target RKE2 version for upgrade compatibility checks
        self.checks: List[CheckResult] = []
    
    def _run_kubectl(self, args: List[str]) -> Tuple[str, str, int]:
        """Execute kubectl command with cluster's kubeconfig"""
        cmd = ["kubectl", "--kubeconfig", "-"] + args
        try:
            result = subprocess.run(
                cmd,
                input=self.kubeconfig.encode(),
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout, result.stderr, result.returncode
        except Exception as e:
            return "", str(e), 1
    
    def _run_ssh_command(self, node_ip: str, ssh_user: str, ssh_key: Optional[str] = None,
                         command: str = "", ssh_password: Optional[str] = None) -> Tuple[str, str, int]:
        """Execute command on remote node via SSH

        Args:
            node_ip: IP address of the node
            ssh_user: SSH username
            ssh_key: SSH private key (optional if using password)
            command: Command to execute
            ssh_password: SSH password (optional if using key)
        """
        import tempfile
        import os

        key_path = None

        try:
            if ssh_key:
                # SSH key authentication
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem') as f:
                    f.write(ssh_key)
                    key_path = f.name
                os.chmod(key_path, 0o600)

                cmd = [
                    "ssh",
                    "-i", key_path,
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "ConnectTimeout=10",
                    f"{ssh_user}@{node_ip}",
                    command
                ]
            elif ssh_password:
                # SSH password authentication using sshpass
                cmd = [
                    "sshpass", "-p", ssh_password,
                    "ssh",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "ConnectTimeout=10",
                    f"{ssh_user}@{node_ip}",
                    command
                ]
            else:
                return "", "Neither SSH key nor password provided", 1

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout, result.stderr, result.returncode
        except Exception as e:
            return "", str(e), 1
        finally:
            if key_path and os.path.exists(key_path):
                os.remove(key_path)
    
    def _add_check(self, check_id: str, category: str, severity: str, 
                   message: str, raw_data: Dict = None, node_name: str = None):
        """Add a check result"""
        self.checks.append(CheckResult(
            check_id=check_id,
            category=category,
            severity=severity,
            message=message,
            raw_data=raw_data or {},
            node_name=node_name
        ))
    
    def collect_node_info(self, node_name: str, node_ip: str, node_role: str,
                          ssh_user: str, ssh_key: Optional[str] = None,
                          ssh_password: Optional[str] = None) -> NodeInfo:
        """Collect OS and node-level health data"""

        # Helper function to simplify SSH calls for this node
        def run_ssh(command: str) -> Tuple[str, str, int]:
            return self._run_ssh_command(node_ip, ssh_user, ssh_key=ssh_key,
                                        command=command, ssh_password=ssh_password)

        # OS version with fallback chain
        # Try 1: lsb_release -d
        stdout, _, rc = run_ssh("lsb_release -d 2>/dev/null")
        os_version = stdout.strip().replace("Description:", "").strip() if rc == 0 and stdout else ""

        # Try 2: cat /etc/os-release (PRETTY_NAME)
        if not os_version or os_version == "unknown":
            stdout, _, rc = run_ssh("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'")
            os_version = stdout.strip() if rc == 0 and stdout else ""

        # Try 3: uname -a (full system info as last resort)
        if not os_version or os_version == "unknown":
            stdout, _, rc = run_ssh("uname -a")
            os_version = stdout.strip() if rc == 0 and stdout else "Unknown"

        # Fallback to "Unknown" if all methods failed
        if not os_version:
            os_version = "Unknown"

        # Kernel version with fallback
        stdout, _, rc = run_ssh("uname -r")
        kernel_version = stdout.strip() if rc == 0 and stdout else "unknown"
        
        # Disk usage
        disk_usage = {}
        for path in ["/var/lib/rancher", "/var/lib/kubelet", "/var/lib/etcd"]:
            stdout, _, rc = run_ssh(
                f"df -h {path} | tail -1 | awk '{{print $5, $4}}'; df -i {path} | tail -1 | awk '{{print $5}}'"
            )
            if rc == 0 and stdout:
                lines = stdout.strip().split('\n')
                if lines:
                    parts = lines[0].split()
                    used_pct = int(parts[0].rstrip('%')) if len(parts) > 0 else 0
                    free_gb = parts[1] if len(parts) > 1 else "0G"
                    inode_used_pct = int(lines[1].rstrip('%')) if len(lines) > 1 else 0
                    
                    disk_usage[path] = {
                        "used_pct": used_pct,
                        "free_pct": 100 - used_pct,
                        "free": free_gb,
                        "inodes_used_pct": inode_used_pct
                    }
                    
                    # Add check
                    if 100 - used_pct < 20:
                        self._add_check(
                            f"disk_space_{path.replace('/', '_')}",
                            "os",
                            "CRITICAL" if 100 - used_pct < 10 else "WARN",
                            f"Low disk space on {node_name}: {path} only {100-used_pct}% free",
                            {"path": path, "free_pct": 100 - used_pct},
                            node_name
                        )
        
        # Swap check
        stdout, _, _ = run_ssh("swapon --show")
        swap_enabled = bool(stdout.strip())
        if swap_enabled:
            self._add_check(
                "swap_enabled",
                "os",
                "WARN",
                f"Swap is enabled on {node_name} (Kubernetes best practice: disable swap)",
                {"swap_output": stdout.strip()},
                node_name
            )
        
        # Memory
        stdout, _, _ = run_ssh(
            "free -m | grep Mem: | awk '{print $2, $3}'; dmesg -T | grep -i 'Out of memory' | tail -1"
        )
        memory = {"total_mb": 0, "used_mb": 0, "oom_events_1h": 0}
        if stdout:
            lines = stdout.strip().split('\n')
            if lines[0]:
                parts = lines[0].split()
                if len(parts) >= 2:
                    memory["total_mb"] = int(parts[0])
                    memory["used_mb"] = int(parts[1])
            # OOM check (simplified)
            memory["oom_events_1h"] = 1 if len(lines) > 1 and lines[1] else 0
        
        # NTP/Time sync
        stdout, _, rc = run_ssh("chronyc tracking 2>/dev/null || ntpq -p 2>/dev/null")
        time_drift_ms = None
        ntp_status = "unknown"
        if rc == 0 and stdout:
            # Parse chrony output
            match = re.search(r'System time\s*:\s*([\d.]+)\s*seconds', stdout)
            if match:
                time_drift_ms = int(float(match.group(1)) * 1000)
                ntp_status = "synced" if abs(time_drift_ms) < 500 else "unsynced"
            elif "synchronized" in stdout.lower():
                ntp_status = "synced"
        
        if time_drift_ms and abs(time_drift_ms) > 500:
            self._add_check(
                "time_drift",
                "os",
                "WARN",
                f"Time drift on {node_name}: {time_drift_ms}ms (should be <500ms)",
                {"drift_ms": time_drift_ms},
                node_name
            )
        
        # Firewall
        stdout, _, _ = run_ssh("ufw status | head -1 || iptables -L -n | wc -l")
        firewall_status = "enabled" if "active" in stdout.lower() or (stdout.strip().isdigit() and int(stdout.strip()) > 0) else "disabled"
        
        # Port reachability (from this node)
        ports_reachable = {}
        for port in [9345, 6443, 10250]:
            stdout, _, rc = run_ssh(
                f"timeout 2 bash -c 'echo > /dev/tcp/127.0.0.1/{port}' 2>&1"
            )
            ports_reachable[port] = (rc == 0)
        
        # RKE2 service status - dynamic service selection based on role
        # Master nodes run rke2-server, worker nodes run rke2-agent
        # Handle case-insensitive role matching
        role_lower = str(node_role).lower()
        service_name = "rke2-server" if "master" in role_lower else "rke2-agent"
        stdout, _, _ = run_ssh(f"systemctl is-active {service_name}")
        rke2_service_status = stdout.strip() if stdout else "unknown"

        if rke2_service_status != "active":
            self._add_check(
                "rke2_service_status",
                "rke2",
                "CRITICAL",
                f"RKE2 service ({service_name}) not active on {node_name}: {rke2_service_status}",
                {"service": service_name, "status": rke2_service_status, "role": node_role},
                node_name
            )

        # Internet connectivity check - test reachability to RKE2 artifact server
        stdout, _, rc = run_ssh("curl -sI --connect-timeout 5 https://get.rke2.io 2>&1 | head -1")
        internet_connected = (rc == 0 and stdout and ("200" in stdout or "301" in stdout or "302" in stdout))

        if not internet_connected:
            self._add_check(
                "internet_connectivity",
                "os",
                "WARN",
                f"Node {node_name} cannot reach get.rke2.io (may require airgap installation)",
                {"url": "https://get.rke2.io", "connected": False},
                node_name
            )

        return NodeInfo(
            name=node_name,
            role=node_role,
            ip=node_ip,
            os_version=os_version,
            kernel_version=kernel_version,
            disk_usage=disk_usage,
            swap_enabled=swap_enabled,
            memory=memory,
            time_drift_ms=time_drift_ms,
            ntp_status=ntp_status,
            firewall_status=firewall_status,
            ports_reachable=ports_reachable,
            rke2_service_status=rke2_service_status,
            internet_connected=internet_connected
        )

    def collect_disk_details(self, node_name: str, node_ip: str, ssh_user: str,
                             ssh_key: Optional[str] = None, ssh_password: Optional[str] = None):
        """
        Collect detailed disk usage for critical RKE2 paths.
        Checks: /var/lib/rancher/rke2, /var/log, and overall root partition.
        """
        try:
            # Check specific paths
            paths = ["/var/lib/rancher/rke2", "/var/log", "/"]

            for path in paths:
                stdout, _, rc = self._run_ssh_command(
                    node_ip, ssh_user,
                    ssh_key=ssh_key,
                    ssh_password=ssh_password,
                    command=f"df -h {path} | tail -n 1"
                )

                if rc == 0 and stdout:
                    parts = stdout.split()
                    if len(parts) >= 5:
                        used_percent = int(parts[4].rstrip('%'))
                        available = parts[3]

                        if used_percent > 80:
                            self._add_check(
                                f"disk_usage_{path.replace('/', '_')}",
                                "os",
                                "CRITICAL" if used_percent > 90 else "WARN",
                                f"High disk usage on {path}: {used_percent}% used (available: {available})",
                                {"path": path, "used_percent": used_percent, "available": available},
                                node_name
                            )
                        else:
                            self._add_check(
                                f"disk_usage_{path.replace('/', '_')}",
                                "os",
                                "OK",
                                f"Disk usage on {path}: {used_percent}% (available: {available})",
                                {"path": path, "used_percent": used_percent, "available": available},
                                node_name
                            )

        except Exception as e:
            self._add_check(
                "disk_usage_details",
                "os",
                "WARN",
                f"Failed to collect detailed disk usage: {str(e)}",
                None,
                node_name
            )

    def collect_system_metrics(self, node_name: str, node_ip: str, ssh_user: str,
                               ssh_key: Optional[str] = None, ssh_password: Optional[str] = None):
        """
        Collect system performance metrics: load average, memory pressure, OOM events.
        """
        try:
            # 1. Load Average
            stdout, _, rc = self._run_ssh_command(
                node_ip, ssh_user,
                ssh_key=ssh_key,
                ssh_password=ssh_password,
                command="uptime"
            )

            if rc == 0 and stdout and "load average:" in stdout:
                load_str = stdout.split("load average:")[1].strip()
                loads = [float(x.strip()) for x in load_str.split(',')]
                load_1min, load_5min, load_15min = loads[0], loads[1], loads[2]

                # Get CPU count
                stdout_cpu, _, rc_cpu = self._run_ssh_command(
                    node_ip, ssh_user,
                    ssh_key=ssh_key,
                    ssh_password=ssh_password,
                    command="nproc"
                )
                cpu_count = int(stdout_cpu.strip()) if rc_cpu == 0 and stdout_cpu else 1

                # High load = load_1min > cpu_count * 2
                if load_1min > cpu_count * 2:
                    self._add_check(
                        "system_load",
                        "os",
                        "WARN",
                        f"High system load: {load_1min:.2f} (1min) on {cpu_count} CPUs",
                        {"load_1min": load_1min, "load_5min": load_5min, "load_15min": load_15min, "cpu_count": cpu_count},
                        node_name
                    )
                else:
                    self._add_check(
                        "system_load",
                        "os",
                        "OK",
                        f"System load normal: {load_1min:.2f} (1min) on {cpu_count} CPUs",
                        {"load_1min": load_1min, "load_5min": load_5min, "load_15min": load_15min, "cpu_count": cpu_count},
                        node_name
                    )

            # 2. Memory Pressure
            stdout, _, rc = self._run_ssh_command(
                node_ip, ssh_user,
                ssh_key=ssh_key,
                ssh_password=ssh_password,
                command="free -m | grep Mem:"
            )

            if rc == 0 and stdout:
                parts = stdout.split()
                if len(parts) >= 7:
                    total_mem = int(parts[1])
                    available_mem = int(parts[6])  # "available" column
                    used_percent = ((total_mem - available_mem) / total_mem) * 100

                    if used_percent > 90:
                        self._add_check(
                            "memory_pressure",
                            "os",
                            "CRITICAL",
                            f"Critical memory pressure: {used_percent:.1f}% used (available: {available_mem}MB / {total_mem}MB)",
                            {"total_mb": total_mem, "available_mb": available_mem, "used_percent": used_percent},
                            node_name
                        )
                    elif used_percent > 80:
                        self._add_check(
                            "memory_pressure",
                            "os",
                            "WARN",
                            f"High memory usage: {used_percent:.1f}% used",
                            {"total_mb": total_mem, "available_mb": available_mem, "used_percent": used_percent},
                            node_name
                        )

            # 3. OOM Events (scan dmesg for Out of Memory killer)
            stdout, _, rc = self._run_ssh_command(
                node_ip, ssh_user,
                ssh_key=ssh_key,
                ssh_password=ssh_password,
                command="sudo dmesg | grep -i 'out of memory' | tail -n 5"
            )

            if rc == 0 and stdout and stdout.strip():
                self._add_check(
                    "oom_events",
                    "os",
                    "WARN",
                    f"Recent OOM events detected on node",
                    {"oom_lines": stdout.strip().split('\n')},
                    node_name
                )

        except Exception as e:
            self._add_check(
                "system_metrics",
                "os",
                "WARN",
                f"Failed to collect system metrics: {str(e)}",
                None,
                node_name
            )

    def collect_os_info(self, node_name: str, node_ip: str, ssh_user: str,
                        ssh_key: Optional[str] = None, ssh_password: Optional[str] = None):
        """
        Collect OS and kernel information for compatibility analysis with target RKE2 version.
        """
        try:
            # Get OS release info
            stdout, _, rc = self._run_ssh_command(
                node_ip, ssh_user,
                ssh_key=ssh_key,
                ssh_password=ssh_password,
                command="cat /etc/os-release"
            )

            # Parse OS info
            os_info = {}
            if rc == 0 and stdout:
                for line in stdout.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os_info[key] = value.strip('"')

            # Get kernel version
            stdout_kernel, _, rc_kernel = self._run_ssh_command(
                node_ip, ssh_user,
                ssh_key=ssh_key,
                ssh_password=ssh_password,
                command="uname -r"
            )

            kernel_version = stdout_kernel.strip() if rc_kernel == 0 and stdout_kernel else "unknown"

            self._add_check(
                "os_kernel_info",
                "os",
                "OK",
                f"OS: {os_info.get('NAME', 'Unknown')} {os_info.get('VERSION', '')}, Kernel: {kernel_version}",
                {
                    "os_name": os_info.get('NAME'),
                    "os_version": os_info.get('VERSION'),
                    "os_id": os_info.get('ID'),
                    "kernel_version": kernel_version
                },
                node_name
            )

        except Exception as e:
            self._add_check(
                "os_kernel_info",
                "os",
                "WARN",
                f"Failed to collect OS/kernel info: {str(e)}",
                None,
                node_name
            )

    def collect_etcd_health(self, master_node_ip: str, ssh_user: str,
                            ssh_key: Optional[str] = None,
                            ssh_password: Optional[str] = None) -> Optional[EtcdHealth]:
        """Collect etcd cluster health"""
        # Check etcd endpoint health
        stdout, _, rc = self._run_ssh_command(
            master_node_ip, ssh_user,
            ssh_key=ssh_key,
            ssh_password=ssh_password,
            command="ETCDCTL_API=3 etcdctl --cacert=/var/lib/rancher/rke2/server/tls/etcd/server-ca.crt "
                    "--cert=/var/lib/rancher/rke2/server/tls/etcd/server-client.crt "
                    "--key=/var/lib/rancher/rke2/server/tls/etcd/server-client.key "
                    "endpoint health --cluster 2>/dev/null"
        )
        
        endpoint_health = {}
        if rc == 0 and stdout:
            for line in stdout.strip().split('\n'):
                if "is healthy" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        endpoint_health[parts[0]] = "healthy"
                elif "unhealthy" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        endpoint_health[parts[0]] = "unhealthy"
        
        # Check leader
        stdout, _, _ = self._run_ssh_command(
            master_node_ip, ssh_user,
            ssh_key=ssh_key,
            ssh_password=ssh_password,
            command="ETCDCTL_API=3 etcdctl --cacert=/var/lib/rancher/rke2/server/tls/etcd/server-ca.crt "
                    "--cert=/var/lib/rancher/rke2/server/tls/etcd/server-client.crt "
                    "--key=/var/lib/rancher/rke2/server/tls/etcd/server-client.key "
                    "endpoint status --cluster -w json 2>/dev/null"
        )
        
        leader_present = False
        member_count = 0
        db_size_mb = 0.0
        max_raft_lag = 0

        if stdout:
            try:
                status_list = json.loads(stdout)
                member_count = len(status_list)
                for item in status_list:
                    status = item.get("Status", {})
                    if status.get("leader"):
                        leader_present = True
                    db_size_mb += status.get("dbSize", 0) / 1024 / 1024

                    # NEW: Check raft index lag
                    raft_index = status.get("raftIndex", 0)
                    raft_applied = status.get("raftAppliedIndex", 0)
                    lag = raft_index - raft_applied
                    if lag > max_raft_lag:
                        max_raft_lag = lag
            except:
                pass

        # Defrag check (if DB > 2GB, recommend defrag)
        defrag_recommended = db_size_mb > 2048

        if not leader_present:
            self._add_check(
                "etcd_leader",
                "rke2",
                "CRITICAL",
                "Etcd cluster has no leader",
                {"endpoint_health": endpoint_health},
                None
            )

        if defrag_recommended:
            self._add_check(
                "etcd_defrag",
                "rke2",
                "WARN",
                f"Etcd DB size is {db_size_mb:.1f}MB, defrag recommended",
                {"db_size_mb": db_size_mb},
                None
            )

        # NEW: Check raft lag (indicates slow disk I/O or network issues)
        if max_raft_lag > 1000:
            self._add_check(
                "etcd_raft_lag",
                "etcd",
                "WARN",
                f"High raft index lag detected: {max_raft_lag} (may indicate slow disk I/O)",
                {"max_raft_lag": max_raft_lag},
                None
            )
        
        return EtcdHealth(
            endpoint_health=endpoint_health,
            leader_present=leader_present,
            db_size_mb=db_size_mb,
            defrag_recommended=defrag_recommended,
            member_count=member_count
        ) if endpoint_health else None
    
    def collect_certificates(self, master_node_ip: str, ssh_user: str,
                             ssh_key: Optional[str] = None,
                             ssh_password: Optional[str] = None) -> List[CertificateInfo]:
        """Collect TLS certificate expiration info"""
        stdout, _, rc = self._run_ssh_command(
            master_node_ip, ssh_user,
            ssh_key=ssh_key,
            ssh_password=ssh_password,
            command="find /var/lib/rancher/rke2/server/tls -name '*.crt' -type f | head -10"
        )
        
        certificates = []
        if rc == 0 and stdout:
            cert_paths = [p.strip() for p in stdout.split('\n') if p.strip()]
            
            for cert_path in cert_paths[:10]:  # Limit to 10 certs
                stdout, _, rc = self._run_ssh_command(
                    master_node_ip, ssh_user,
                    ssh_key=ssh_key,
                    ssh_password=ssh_password,
                    command=f"openssl x509 -in {cert_path} -noout -subject -enddate 2>/dev/null"
                )
                
                if rc == 0 and stdout:
                    subject = ""
                    expiry_date = ""
                    for line in stdout.split('\n'):
                        if line.startswith("subject="):
                            subject = line.replace("subject=", "").strip()
                        elif line.startswith("notAfter="):
                            expiry_date = line.replace("notAfter=", "").strip()
                    
                    if expiry_date:
                        try:
                            from dateutil import parser
                            exp_dt = parser.parse(expiry_date)
                            days_until = (exp_dt - datetime.now()).days
                            
                            certificates.append(CertificateInfo(
                                path=cert_path,
                                subject=subject,
                                expiry_date=exp_dt.isoformat(),
                                days_until_expiry=days_until,
                                expired=days_until < 0
                            ))
                            
                            if days_until < 30:
                                self._add_check(
                                    f"cert_expiry_{cert_path.split('/')[-1]}",
                                    "rke2",
                                    "CRITICAL" if days_until < 7 else "WARN",
                                    f"Certificate {cert_path.split('/')[-1]} expires in {days_until} days",
                                    {"path": cert_path, "days_until": days_until},
                                    None
                                )
                        except:
                            pass

        return certificates

    def collect_deprecated_apis(self):
        """
        Detect Kubernetes resources using deprecated APIs.
        Uses kubectl to find resources with deprecated apiVersions.
        """
        try:
            # Define deprecated APIs by Kubernetes version
            deprecated_apis = {
                "1.25": [
                    ("batch/v1beta1", "CronJob"),
                    ("policy/v1beta1", "PodSecurityPolicy"),
                    ("policy/v1beta1", "PodDisruptionBudget")
                ],
                "1.26": [
                    ("flowcontrol.apiserver.k8s.io/v1beta1", "FlowSchema"),
                    ("flowcontrol.apiserver.k8s.io/v1beta1", "PriorityLevelConfiguration"),
                    ("autoscaling/v2beta2", "HorizontalPodAutoscaler")
                ],
                "1.27": [
                    ("storage.k8s.io/v1beta1", "CSIStorageCapacity")
                ],
                "1.29": [
                    ("flowcontrol.apiserver.k8s.io/v1beta2", "FlowSchema"),
                    ("flowcontrol.apiserver.k8s.io/v1beta2", "PriorityLevelConfiguration")
                ],
                "1.30": [
                    ("flowcontrol.apiserver.k8s.io/v1beta3", "FlowSchema"),
                    ("flowcontrol.apiserver.k8s.io/v1beta3", "PriorityLevelConfiguration")
                ]
            }

            # Determine target Kubernetes version
            target_k8s_version = None
            if self.target_version:
                # Extract K8s version from RKE2 version (e.g., v1.30.2+rke2r1 -> 1.30)
                match = re.search(r'v?(\d+\.\d+)', self.target_version)
                if match:
                    target_k8s_version = match.group(1)

            if not target_k8s_version:
                # Fall back to current cluster version
                stdout, _, _ = self._run_kubectl(["version", "--short"])
                if stdout:
                    match = re.search(r'Server Version: v?(\d+\.\d+)', stdout)
                    if match:
                        target_k8s_version = match.group(1)

            if not target_k8s_version:
                self._add_check(
                    "deprecated_apis",
                    "kubernetes",
                    "WARN",
                    "Could not determine Kubernetes version for deprecated API check",
                    None,
                    None
                )
                return

            # Get list of deprecated APIs for this version and earlier
            apis_to_check = []
            for version, apis in deprecated_apis.items():
                if version <= target_k8s_version:
                    apis_to_check.extend(apis)

            # Check for each deprecated API
            found_deprecated = []
            for api_version, kind in apis_to_check:
                try:
                    stdout, _, rc = self._run_kubectl(["get", kind, "-A", "-o", "json"])
                    if rc == 0 and stdout and "items" in stdout:
                        data = json.loads(stdout)
                        for item in data.get("items", []):
                            if item.get("apiVersion") == api_version:
                                found_deprecated.append({
                                    "kind": kind,
                                    "name": item["metadata"]["name"],
                                    "namespace": item["metadata"].get("namespace", "cluster-scoped"),
                                    "apiVersion": api_version
                                })
                except Exception:
                    pass  # Ignore errors for resources that don't exist

            if found_deprecated:
                self._add_check(
                    "deprecated_apis",
                    "kubernetes",
                    "CRITICAL",
                    f"Found {len(found_deprecated)} resources using deprecated APIs (target: K8s {target_k8s_version})",
                    {"deprecated_resources": found_deprecated, "target_version": target_k8s_version},
                    None
                )
            else:
                self._add_check(
                    "deprecated_apis",
                    "kubernetes",
                    "OK",
                    f"No deprecated APIs detected for K8s {target_k8s_version}",
                    {"target_version": target_k8s_version},
                    None
                )

        except Exception as e:
            self._add_check(
                "deprecated_apis",
                "kubernetes",
                "WARN",
                f"Failed to check deprecated APIs: {str(e)}",
                None,
                None
            )

    def collect_pod_disruption_budgets(self):
        """
        Check for PodDisruptionBudgets that might block node drains during upgrade.
        Warns about PDBs with minAvailable=100% or maxUnavailable=0 on critical workloads.
        """
        try:
            stdout, _, rc = self._run_kubectl(["get", "pdb", "-A", "-o", "json"])
            if rc != 0 or not stdout:
                self._add_check(
                    "pod_disruption_budgets",
                    "kubernetes",
                    "OK",
                    "No PodDisruptionBudgets found",
                    None,
                    None
                )
                return

            data = json.loads(stdout)
            risky_pdbs = []

            for pdb in data.get("items", []):
                name = pdb["metadata"]["name"]
                namespace = pdb["metadata"]["namespace"]
                spec = pdb.get("spec", {})

                # Check for overly restrictive PDBs
                min_available = spec.get("minAvailable")
                max_unavailable = spec.get("maxUnavailable")

                is_risky = False
                reason = ""

                if max_unavailable == 0:
                    is_risky = True
                    reason = "maxUnavailable=0 (no pods can be unavailable)"
                elif isinstance(min_available, str) and min_available == "100%":
                    is_risky = True
                    reason = "minAvailable=100% (all pods must be available)"
                elif isinstance(min_available, int) and min_available > 0:
                    reason = f"minAvailable={min_available} (may block drain if replicas are low)"
                    is_risky = True

                if is_risky:
                    risky_pdbs.append({
                        "name": name,
                        "namespace": namespace,
                        "minAvailable": min_available,
                        "maxUnavailable": max_unavailable,
                        "reason": reason
                    })

            if risky_pdbs:
                self._add_check(
                    "pod_disruption_budgets",
                    "kubernetes",
                    "WARN",
                    f"Found {len(risky_pdbs)} restrictive PodDisruptionBudgets that may block node drains",
                    {"risky_pdbs": risky_pdbs},
                    None
                )
            else:
                self._add_check(
                    "pod_disruption_budgets",
                    "kubernetes",
                    "OK",
                    "PodDisruptionBudgets appear safe for upgrade",
                    None,
                    None
                )

        except Exception as e:
            self._add_check(
                "pod_disruption_budgets",
                "kubernetes",
                "WARN",
                f"Failed to check PodDisruptionBudgets: {str(e)}",
                None,
                None
            )

    def collect_log_patterns(self, node_name: str, node_ip: str, ssh_user: str,
                            ssh_key: Optional[str] = None, ssh_password: Optional[str] = None):
        """
        Scan recent RKE2 service logs for error patterns with contextual lines.
        Looks for: Error, Critical, CrashLoop, OOMKilled, failed to start, panic
        For each match, captures 2 lines before and 2 lines after for AI analysis context.
        """
        try:
            # Determine service name based on node role
            services = ["rke2-server", "rke2-agent"]
            error_patterns = ["Error", "Critical", "CrashLoop", "OOMKilled", "failed to start", "panic"]
            found_errors = []

            for service in services:
                for pattern in error_patterns:
                    # Use grep with context lines: -B2 (2 before) -A2 (2 after)
                    # This gives us 5 total lines of context per match
                    stdout, _, rc = self._run_ssh_command(
                        node_ip, ssh_user,
                        ssh_key=ssh_key,
                        ssh_password=ssh_password,
                        command=f"sudo journalctl -u {service} --since '1 hour ago' --no-pager | grep -i -B2 -A2 '{pattern}' | tail -n 15"
                    )

                    if rc == 0 and stdout and stdout.strip():
                        # Split into groups (grep adds -- between matches)
                        log_groups = stdout.strip().split('--')

                        # Take only the first match group to avoid overwhelming the AI
                        if log_groups and log_groups[0].strip():
                            found_errors.append({
                                "service": service,
                                "pattern": pattern,
                                "context_lines": log_groups[0].strip().split('\n'),  # 5 lines with context
                                "match_count": len(log_groups)
                            })

            if found_errors:
                # Deduplicate by service and pattern
                unique_errors = {}
                for err in found_errors:
                    key = f"{err['service']}:{err['pattern']}"
                    if key not in unique_errors:
                        unique_errors[key] = err

                self._add_check(
                    "log_patterns",
                    "rke2",
                    "WARN",
                    f"Found {len(unique_errors)} error patterns in RKE2 logs (with context for AI analysis)",
                    {"errors": list(unique_errors.values())},
                    node_name
                )
            else:
                self._add_check(
                    "log_patterns",
                    "rke2",
                    "OK",
                    "No critical error patterns in recent RKE2 logs",
                    None,
                    node_name
                )

        except Exception as e:
            self._add_check(
                "log_patterns",
                "rke2",
                "WARN",
                f"Failed to scan logs: {str(e)}",
                None,
                node_name
            )

    def collect_network_component_versions(self):
        """
        Collect CNI (Canal/Cilium) and Ingress controller (Traefik/Nginx) versions.
        Uses both exact name matching and label-based fuzzy matching for better detection.
        """
        try:
            cni_found = False

            # Strategy 1: Try exact daemonset names
            cni_checks = [
                ("canal", "Canal"),
                ("cilium", "Cilium"),
                ("calico-node", "Calico"),
                ("kube-flannel-ds", "Flannel")
            ]

            for ds_name, cni_display_name in cni_checks:
                stdout, _, rc = self._run_kubectl([
                    "get", "daemonset", "-n", "kube-system", ds_name,
                    "-o", "jsonpath={.spec.template.spec.containers[0].image}"
                ])

                if rc == 0 and stdout and stdout != '':
                    self._add_check(
                        "cni_version",
                        "network",
                        "OK",
                        f"CNI: {cni_display_name} {stdout}",
                        {"cni": cni_display_name.lower(), "image": stdout},
                        None
                    )
                    cni_found = True
                    break

            # Strategy 2: Label-based fuzzy search if exact name failed
            if not cni_found:
                # Search for CNI-related pods by common labels
                label_searches = [
                    ("app.kubernetes.io/name=canal", "Canal"),
                    ("app.kubernetes.io/name=cilium", "Cilium"),
                    ("app.kubernetes.io/name=calico", "Calico"),
                    ("k8s-app=canal", "Canal"),
                    ("k8s-app=cilium", "Cilium"),
                    ("k8s-app=calico-node", "Calico")
                ]

                for label, cni_display_name in label_searches:
                    stdout, _, rc = self._run_kubectl([
                        "get", "daemonset", "-n", "kube-system",
                        "-l", label,
                        "-o", "jsonpath={.items[0].spec.template.spec.containers[0].image}"
                    ])

                    if rc == 0 and stdout and stdout != '':
                        self._add_check(
                            "cni_version",
                            "network",
                            "OK",
                            f"CNI: {cni_display_name} {stdout} (detected via labels)",
                            {"cni": cni_display_name.lower(), "image": stdout, "detection": "label-based"},
                            None
                        )
                        cni_found = True
                        break

            if not cni_found:
                self._add_check(
                    "cni_version",
                    "network",
                    "WARN",
                    "CNI plugin not detected (Canal/Cilium/Calico not found)",
                    None,
                    None
                )

            # Check Ingress controller with fuzzy matching
            ingress_found = False

            # Strategy 1: Try exact deployment names
            ingress_checks = [
                ("traefik", "kube-system", "Traefik"),
                ("ingress-nginx-controller", "ingress-nginx", "Nginx"),
                ("nginx-ingress-controller", "ingress-nginx", "Nginx")
            ]

            for deploy_name, namespace, ingress_display_name in ingress_checks:
                stdout, _, rc = self._run_kubectl([
                    "get", "deployment", "-n", namespace, deploy_name,
                    "-o", "jsonpath={.spec.template.spec.containers[0].image}"
                ])

                if rc == 0 and stdout and stdout != '':
                    self._add_check(
                        "ingress_version",
                        "network",
                        "OK",
                        f"Ingress: {ingress_display_name} {stdout}",
                        {"ingress": ingress_display_name.lower(), "image": stdout},
                        None
                    )
                    ingress_found = True
                    break

            # Strategy 2: Label-based fuzzy search if exact name failed
            if not ingress_found:
                label_searches = [
                    ("app.kubernetes.io/name=traefik", "kube-system", "Traefik"),
                    ("app.kubernetes.io/name=ingress-nginx", "ingress-nginx", "Nginx"),
                    ("app=traefik", "kube-system", "Traefik")
                ]

                for label, namespace, ingress_display_name in label_searches:
                    stdout, _, rc = self._run_kubectl([
                        "get", "deployment", "-n", namespace,
                        "-l", label,
                        "-o", "jsonpath={.items[0].spec.template.spec.containers[0].image}"
                    ])

                    if rc == 0 and stdout and stdout != '':
                        self._add_check(
                            "ingress_version",
                            "network",
                            "OK",
                            f"Ingress: {ingress_display_name} {stdout} (detected via labels)",
                            {"ingress": ingress_display_name.lower(), "image": stdout, "detection": "label-based"},
                            None
                        )
                        ingress_found = True
                        break

            if not ingress_found:
                self._add_check(
                    "ingress_version",
                    "network",
                    "OK",
                    "No ingress controller detected (optional)",
                    None,
                    None
                )

        except Exception as e:
            self._add_check(
                "network_components",
                "network",
                "WARN",
                f"Failed to check network component versions: {str(e)}",
                None,
                None
            )

    def collect_workload_safety(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Collect workload safety information for upgrade readiness:
        1. HostPath volumes (risky for node drains - data loss risk)
        2. StatefulSet inventory with PV types (local vs shared storage)

        Returns:
            Tuple of (hostpath_workloads, statefulsets)
        """
        hostpath_workloads = []
        statefulsets = []

        try:
            # 1. Scan for HostPath volumes in Deployments and Pods
            stdout, _, rc = self._run_kubectl(["get", "deployments,daemonsets,pods", "-A", "-o", "json"])

            if rc == 0 and stdout:
                data = json.loads(stdout)

                for item in data.get("items", []):
                    kind = item.get("kind")
                    name = item["metadata"]["name"]
                    namespace = item["metadata"].get("namespace", "default")

                    # Check pod template spec for hostPath volumes
                    spec = item.get("spec", {})
                    template_spec = spec.get("template", {}).get("spec", {}) if kind in ["Deployment", "DaemonSet"] else spec

                    volumes = template_spec.get("volumes", [])

                    for volume in volumes:
                        if "hostPath" in volume:
                            hostpath_workloads.append({
                                "kind": kind,
                                "name": name,
                                "namespace": namespace,
                                "volume_name": volume.get("name"),
                                "host_path": volume["hostPath"].get("path")
                            })

            if hostpath_workloads:
                self._add_check(
                    "hostpath_volumes",
                    "kubernetes",
                    "WARN",
                    f"Found {len(hostpath_workloads)} workloads using hostPath volumes (data loss risk during node drain)",
                    {"hostpath_workloads": hostpath_workloads[:10]},  # Limit to first 10 for brevity
                    None
                )

            # 2. Scan StatefulSets and analyze PV types
            stdout, _, rc = self._run_kubectl(["get", "statefulsets", "-A", "-o", "json"])

            if rc == 0 and stdout:
                sts_data = json.loads(stdout)

                for sts in sts_data.get("items", []):
                    name = sts["metadata"]["name"]
                    namespace = sts["metadata"]["namespace"]
                    replicas = sts["spec"].get("replicas", 0)

                    # Get VolumeClaimTemplates
                    volume_claim_templates = sts["spec"].get("volumeClaimTemplates", [])

                    pv_types = []
                    for vct in volume_claim_templates:
                        storage_class = vct["spec"].get("storageClassName")

                        # Try to determine if it's local or shared storage
                        if storage_class:
                            # Get StorageClass to check provisioner
                            sc_stdout, _, sc_rc = self._run_kubectl(["get", "storageclass", storage_class, "-o", "jsonpath={.provisioner}"])

                            if sc_rc == 0 and sc_stdout:
                                provisioner = sc_stdout.strip()

                                # Classify as local vs shared
                                if "local" in provisioner.lower() or "hostpath" in provisioner.lower():
                                    pv_type = "local"
                                else:
                                    pv_type = "shared"

                                pv_types.append({
                                    "storage_class": storage_class,
                                    "provisioner": provisioner,
                                    "type": pv_type
                                })

                    statefulsets.append({
                        "name": name,
                        "namespace": namespace,
                        "replicas": replicas,
                        "pv_types": pv_types
                    })

            if statefulsets:
                # Check for local PVs (risky for upgrades)
                local_pv_count = sum(1 for sts in statefulsets for pv in sts["pv_types"] if pv.get("type") == "local")

                if local_pv_count > 0:
                    self._add_check(
                        "statefulset_local_pvs",
                        "kubernetes",
                        "WARN",
                        f"Found {local_pv_count} StatefulSet(s) using local PVs (data loss risk during node replacement)",
                        {"statefulsets_with_local_pvs": [sts for sts in statefulsets if any(pv.get("type") == "local" for pv in sts["pv_types"])]},
                        None
                    )

        except Exception as e:
            self._add_check(
                "workload_safety",
                "kubernetes",
                "WARN",
                f"Failed to collect workload safety information: {str(e)}",
                None,
                None
            )

        return hostpath_workloads, statefulsets

    def collect_kubernetes_health(self) -> KubernetesHealth:
        """Collect Kubernetes layer health"""
        # Node status
        stdout, _, _ = self._run_kubectl(["get", "nodes", "-o", "json"])
        node_ready = 0
        node_not_ready = 0
        cordoned = []
        
        if stdout:
            try:
                nodes_data = json.loads(stdout)
                for node in nodes_data.get("items", []):
                    name = node["metadata"]["name"]
                    spec = node.get("spec", {})
                    status = node.get("status", {})
                    
                    # Check if cordoned
                    if spec.get("unschedulable"):
                        cordoned.append(name)
                    
                    # Check ready status
                    conditions = status.get("conditions", [])
                    for cond in conditions:
                        if cond.get("type") == "Ready":
                            if cond.get("status") == "True":
                                node_ready += 1
                            else:
                                node_not_ready += 1
                            break
            except:
                pass
        
        if node_not_ready > 0:
            self._add_check(
                "nodes_not_ready",
                "kubernetes",
                "CRITICAL",
                f"{node_not_ready} node(s) not ready",
                {"count": node_not_ready},
                None
            )
        
        # kube-system pod restarts
        stdout, _, _ = self._run_kubectl(["get", "pods", "-n", "kube-system", "-o", "json"])
        kube_system_restarts = {}
        crash_loop_pods = []
        image_pull_backoff_pods = []
        
        if stdout:
            try:
                pods_data = json.loads(stdout)
                for pod in pods_data.get("items", []):
                    pod_name = pod["metadata"]["name"]
                    status = pod.get("status", {})
                    
                    # Restart count
                    restart_count = 0
                    for container_status in status.get("containerStatuses", []):
                        restart_count += container_status.get("restartCount", 0)
                    
                    if restart_count > 0:
                        kube_system_restarts[pod_name] = restart_count
                        
                        if restart_count > 50:
                            self._add_check(
                                f"pod_restarts_{pod_name}",
                                "kubernetes",
                                "WARN",
                                f"Pod {pod_name} has {restart_count} restarts",
                                {"pod": pod_name, "restarts": restart_count},
                                None
                            )
                    
                    # Check for CrashLoopBackOff / ImagePullBackOff
                    phase = status.get("phase")
                    for container_status in status.get("containerStatuses", []):
                        waiting = container_status.get("state", {}).get("waiting", {})
                        reason = waiting.get("reason", "")
                        
                        if reason == "CrashLoopBackOff":
                            crash_loop_pods.append(f"{pod_name}/{container_status.get('name')}")
                        elif reason == "ImagePullBackOff" or reason == "ErrImagePull":
                            image_pull_backoff_pods.append(f"{pod_name}/{container_status.get('name')}")
            except:
                pass
        
        if crash_loop_pods:
            self._add_check(
                "crash_loop_pods",
                "kubernetes",
                "CRITICAL",
                f"{len(crash_loop_pods)} pod(s) in CrashLoopBackOff",
                {"pods": crash_loop_pods},
                None
            )
        
        # Deprecated API usage (simplified - would need pluto/kubent logic)
        deprecated_apis = []  # TODO: Implement kubent-style scanning
        
        # Admission webhooks
        stdout, _, _ = self._run_kubectl(["get", "validatingwebhookconfigurations,mutatingwebhookconfigurations", "-o", "json"])
        admission_webhooks = []
        
        if stdout:
            try:
                webhooks_data = json.loads(stdout)
                for wh in webhooks_data.get("items", []):
                    kind = wh.get("kind")
                    name = wh["metadata"]["name"]
                    webhooks = wh.get("webhooks", [])
                    
                    for webhook in webhooks:
                        admission_webhooks.append({
                            "name": name,
                            "type": "validating" if kind == "ValidatingWebhookConfiguration" else "mutating",
                            "failurePolicy": webhook.get("failurePolicy", "Fail")
                        })
                        
                        if webhook.get("failurePolicy") == "Fail":
                            self._add_check(
                                f"webhook_fail_policy_{name}",
                                "kubernetes",
                                "WARN",
                                f"Webhook {name} has failurePolicy=Fail (may block upgrades)",
                                {"webhook": name, "policy": "Fail"},
                                None
                            )
            except:
                pass
        
        # Collect workload safety information
        hostpath_workloads, statefulsets = self.collect_workload_safety()

        return KubernetesHealth(
            node_ready_count=node_ready,
            node_not_ready_count=node_not_ready,
            cordoned_nodes=cordoned,
            kube_system_pod_restarts=kube_system_restarts,
            crash_loop_pods=crash_loop_pods,
            image_pull_backoff_pods=image_pull_backoff_pods,
            deprecated_apis=deprecated_apis,
            admission_webhooks=admission_webhooks,
            hostpath_workloads=hostpath_workloads,
            statefulsets=statefulsets
        )
    
    def collect_network_health(self) -> NetworkHealth:
        """Collect network layer health"""
        # Detect CNI type
        stdout, _, _ = self._run_kubectl(["get", "pods", "-n", "kube-system", "-o", "json"])
        cni_type = "unknown"
        cni_pods_running = 0
        cni_pods_not_running = 0
        
        if stdout:
            try:
                pods_data = json.loads(stdout)
                for pod in pods_data.get("items", []):
                    pod_name = pod["metadata"]["name"]
                    phase = pod.get("status", {}).get("phase", "")
                    
                    if "canal" in pod_name:
                        cni_type = "canal"
                    elif "cilium" in pod_name:
                        cni_type = "cilium"
                    elif "calico" in pod_name:
                        cni_type = "calico"
                    
                    if any(x in pod_name for x in ["canal", "cilium", "calico", "flannel"]):
                        if phase == "Running":
                            cni_pods_running += 1
                        else:
                            cni_pods_not_running += 1
            except:
                pass
        
        # Pod CIDR
        stdout, _, _ = self._run_kubectl(["cluster-info", "dump", "--output=json"])
        pod_cidr = "unknown"
        # Simplified - would need to parse cluster config
        
        # Ingress controller
        stdout, _, _ = self._run_kubectl(["get", "ingressclass", "-o", "json"])
        ingress_controller = None
        ingress_version = None
        
        if stdout:
            try:
                data = json.loads(stdout)
                if data.get("items"):
                    ingress_controller = data["items"][0]["spec"].get("controller", "unknown")
            except:
                pass
        
        return NetworkHealth(
            cni_type=cni_type,
            cni_pods_running=cni_pods_running,
            cni_pods_not_running=cni_pods_not_running,
            pod_cidr=pod_cidr,
            pod_cidr_usage_pct=None,
            ingress_controller=ingress_controller,
            ingress_version=ingress_version
        )
    
    def collect_storage_health(self) -> StorageHealth:
        """Collect storage layer health"""
        # Default StorageClass
        stdout, _, _ = self._run_kubectl(["get", "storageclass", "-o", "json"])
        default_sc = None
        provisioner_type = None
        
        if stdout:
            try:
                data = json.loads(stdout)
                for sc in data.get("items", []):
                    annotations = sc.get("metadata", {}).get("annotations", {})
                    if annotations.get("storageclass.kubernetes.io/is-default-class") == "true":
                        default_sc = sc["metadata"]["name"]
                        provisioner_type = sc.get("provisioner", "unknown")
                        break
            except:
                pass
        
        # Check provisioner pods (Longhorn example)
        stdout, _, _ = self._run_kubectl(["get", "pods", "-n", "longhorn-system", "-o", "json"])
        provisioner_healthy = False
        
        if stdout:
            try:
                pods_data = json.loads(stdout)
                running_count = 0
                total_count = len(pods_data.get("items", []))
                
                for pod in pods_data.get("items", []):
                    if pod.get("status", {}).get("phase") == "Running":
                        running_count += 1
                
                provisioner_healthy = (running_count == total_count and total_count > 0)
            except:
                pass
        
        # PVC pending count
        stdout, _, _ = self._run_kubectl(["get", "pvc", "--all-namespaces", "-o", "json"])
        pvc_pending = 0
        
        if stdout:
            try:
                data = json.loads(stdout)
                for pvc in data.get("items", []):
                    if pvc.get("status", {}).get("phase") == "Pending":
                        pvc_pending += 1
            except:
                pass
        
        return StorageHealth(
            default_storageclass=default_sc,
            provisioner_type=provisioner_type,
            provisioner_pods_healthy=provisioner_healthy,
            pvc_pending_count=pvc_pending
        )
    
    def generate_report(self, nodes_data: List[Dict]) -> PreflightReport:
        """Generate complete pre-flight report

        Args:
            nodes_data: List of dicts with keys: hostname, ip, role, ssh_user, ssh_key (or ssh_password)
        """
        # Collect cluster metadata
        stdout, _, _ = self._run_kubectl(["version", "-o", "json"])
        k8s_version = "unknown"
        rke2_version = "unknown"
        
        if stdout:
            try:
                version_data = json.loads(stdout)
                k8s_version = version_data.get("serverVersion", {}).get("gitVersion", "unknown")
                # RKE2 version is usually in server version
                rke2_version = k8s_version
            except:
                pass
        
        metadata = ClusterMetadata(
            cluster_id=self.cluster_id,
            cluster_name=self.cluster_name,
            rke2_version=rke2_version,
            kubernetes_version=k8s_version,
            node_count=len(nodes_data),
            collected_at=datetime.utcnow().isoformat() + "Z",
            target_version=self.target_version  # NEW: Include target version for AI analysis
        )
        
        # Collect node-level data
        nodes = []
        master_node_ip = None
        master_ssh_user = None
        master_ssh_key = None
        master_ssh_password = None

        for node_data in nodes_data:
            node_info = self.collect_node_info(
                node_data["hostname"],
                node_data["ip"],
                node_data["role"],
                node_data["ssh_user"],
                ssh_key=node_data.get("ssh_key"),
                ssh_password=node_data.get("ssh_password")
            )
            nodes.append(node_info)

            # NEW: Call advanced node-level checks (Phase 3 & 4)
            self.collect_disk_details(
                node_data["hostname"],
                node_data["ip"],
                node_data["ssh_user"],
                ssh_key=node_data.get("ssh_key"),
                ssh_password=node_data.get("ssh_password")
            )

            self.collect_system_metrics(
                node_data["hostname"],
                node_data["ip"],
                node_data["ssh_user"],
                ssh_key=node_data.get("ssh_key"),
                ssh_password=node_data.get("ssh_password")
            )

            self.collect_os_info(
                node_data["hostname"],
                node_data["ip"],
                node_data["ssh_user"],
                ssh_key=node_data.get("ssh_key"),
                ssh_password=node_data.get("ssh_password")
            )

            self.collect_log_patterns(
                node_data["hostname"],
                node_data["ip"],
                node_data["ssh_user"],
                ssh_key=node_data.get("ssh_key"),
                ssh_password=node_data.get("ssh_password")
            )

            # Save master node for etcd/cert checks
            if "master" in node_data["role"] and not master_node_ip:
                master_node_ip = node_data["ip"]
                master_ssh_user = node_data["ssh_user"]
                master_ssh_key = node_data.get("ssh_key")
                master_ssh_password = node_data.get("ssh_password")

        # Collect cluster-level data
        etcd = None
        certificates = []
        if master_node_ip:
            etcd = self.collect_etcd_health(master_node_ip, master_ssh_user,
                                           ssh_key=master_ssh_key,
                                           ssh_password=master_ssh_password)
            certificates = self.collect_certificates(master_node_ip, master_ssh_user,
                                                    ssh_key=master_ssh_key,
                                                    ssh_password=master_ssh_password)

        kubernetes = self.collect_kubernetes_health()
        network = self.collect_network_health()
        storage = self.collect_storage_health()

        # NEW: Call cluster-wide advanced checks (Phase 4 & 5)
        self.collect_deprecated_apis()
        self.collect_pod_disruption_budgets()
        self.collect_network_component_versions()
        
        return PreflightReport(
            cluster_metadata=metadata,
            nodes=nodes,
            checks=self.checks,
            etcd=etcd,
            certificates=certificates,
            kubernetes=kubernetes,
            network=network,
            storage=storage
        )
