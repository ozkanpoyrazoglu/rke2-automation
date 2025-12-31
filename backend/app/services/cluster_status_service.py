import subprocess
import json
import tempfile
import os
import time
from datetime import datetime
from app.models import Cluster

def get_cluster_status(cluster: Cluster) -> dict:
    """
    Get cluster status using kubectl commands and return aggregated LLM-ready format

    Returns deterministic JSON structure suitable for:
    - UI display
    - LLM input
    - Long-term caching
    """
    start_time = time.time()
    collection_errors = []

    if not cluster.kubeconfig and cluster.cluster_type != "registered":
        return {
            "error": "Cluster not yet installed or kubeconfig not available",
            "cluster_metadata": {
                "cluster_id": cluster.id,
                "name": cluster.name,
                "rke2_version": cluster.rke2_version
            }
        }

    # Write kubeconfig to temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as f:
        kubeconfig_path = f.name
        f.write(cluster.kubeconfig if cluster.kubeconfig else "")

    try:
        # Initialize aggregated structure
        aggregated = {
            "cluster_metadata": {
                "cluster_id": cluster.id,
                "name": cluster.name,
                "kubernetes_version": "unknown",
                "rke2_version": cluster.rke2_version,
                "collected_at": datetime.utcnow().isoformat()
            },
            "nodes": {
                "total": 0,
                "ready": 0,
                "not_ready": 0,
                "details": []
            },
            "roles": {
                "control_plane": 0,
                "etcd": 0,
                "worker": 0
            },
            "network": {
                "cni": {
                    "type": "unknown",
                    "status": "unknown"
                }
            },
            "components": {
                "etcd": "unknown",
                "apiserver": "unknown",
                "scheduler": "unknown",
                "controller_manager": "unknown"
            },
            "workloads": {
                "namespaces": 0,
                "namespaces_details": [],
                "pods_total": 0,
                "pods_running": 0
            },
            "api_compatibility": {
                "crd_count": 0,
                "crds": []
            },
            "collection_errors": []
        }

        # Get cluster version
        try:
            result = subprocess.run(
                ["kubectl", "--kubeconfig", kubeconfig_path, "version", "--output=json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_data = json.loads(result.stdout)
                aggregated["cluster_metadata"]["kubernetes_version"] = version_data.get("serverVersion", {}).get("gitVersion", "unknown")
        except Exception as e:
            collection_errors.append(f"kubernetes_version: {str(e)}")

        # Get nodes info
        try:
            node_details = get_node_details(kubeconfig_path)
            aggregated["nodes"]["details"] = node_details
            aggregated["nodes"]["total"] = len(node_details)
            aggregated["nodes"]["ready"] = sum(1 for n in node_details if n.get("status") == "Ready")
            aggregated["nodes"]["not_ready"] = sum(1 for n in node_details if n.get("status") != "Ready")

            # Count roles
            for node in node_details:
                roles = node.get("roles", "")
                if "control-plane" in roles:
                    aggregated["roles"]["control_plane"] += 1
                if "etcd" in roles:
                    aggregated["roles"]["etcd"] += 1
                if "worker" in roles:
                    aggregated["roles"]["worker"] += 1
        except Exception as e:
            collection_errors.append(f"nodes: {str(e)}")

        # Detect CNI
        try:
            cni_info = detect_cni(kubeconfig_path)
            aggregated["network"]["cni"] = cni_info
        except Exception as e:
            collection_errors.append(f"cni: {str(e)}")

        # Get component status
        try:
            components = get_component_status(kubeconfig_path)
            aggregated["components"] = components
        except Exception as e:
            collection_errors.append(f"components: {str(e)}")

        # Get namespaces and pod counts
        try:
            namespaces = get_namespaces_info(kubeconfig_path)
            aggregated["workloads"]["namespaces"] = len(namespaces)
            aggregated["workloads"]["namespaces_details"] = namespaces
            aggregated["workloads"]["pods_total"] = sum(ns.get("total_pods", 0) for ns in namespaces)
            aggregated["workloads"]["pods_running"] = sum(ns.get("running_pods", 0) for ns in namespaces)
        except Exception as e:
            collection_errors.append(f"namespaces: {str(e)}")

        # Get CRDs
        try:
            crds = get_crds_info(kubeconfig_path)
            aggregated["api_compatibility"]["crd_count"] = len(crds)
            aggregated["api_compatibility"]["crds"] = crds
        except Exception as e:
            collection_errors.append(f"crds: {str(e)}")

        # Add collection metadata
        aggregated["collection_errors"] = collection_errors
        aggregated["_collection_duration_seconds"] = int(time.time() - start_time)

        return aggregated

    except Exception as e:
        return {"error": f"Failed to get cluster status: {str(e)}"}
    finally:
        # Clean up kubeconfig file
        if os.path.exists(kubeconfig_path):
            os.remove(kubeconfig_path)

def detect_cni(kubeconfig_path: str) -> dict:
    """Detect CNI type and status"""
    try:
        # Check for canal pods
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", "kube-system",
             "-l", "k8s-app=canal", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout).get("items", [])
            if pods:
                running = sum(1 for p in pods if p.get("status", {}).get("phase") == "Running")
                return {
                    "type": "canal",
                    "status": "healthy" if running == len(pods) else "degraded",
                    "pods": {"total": len(pods), "running": running}
                }

        # Check for cilium pods
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", "kube-system",
             "-l", "k8s-app=cilium", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout).get("items", [])
            if pods:
                running = sum(1 for p in pods if p.get("status", {}).get("phase") == "Running")
                return {
                    "type": "cilium",
                    "status": "healthy" if running == len(pods) else "degraded",
                    "pods": {"total": len(pods), "running": running}
                }

        # Check for calico pods
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", "kube-system",
             "-l", "k8s-app=calico-node", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout).get("items", [])
            if pods:
                running = sum(1 for p in pods if p.get("status", {}).get("phase") == "Running")
                return {
                    "type": "calico",
                    "status": "healthy" if running == len(pods) else "degraded",
                    "pods": {"total": len(pods), "running": running}
                }

        return {"type": "unknown", "status": "unknown"}
    except:
        return {"type": "unknown", "status": "error"}

def get_component_status(kubeconfig_path: str) -> dict:
    """Get Kubernetes component health status"""
    components = {
        "etcd": "unknown",
        "apiserver": "unknown",
        "scheduler": "unknown",
        "controller_manager": "unknown"
    }

    try:
        # Check etcd pods
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", "kube-system",
             "-l", "component=etcd", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout).get("items", [])
            if pods:
                running = all(p.get("status", {}).get("phase") == "Running" for p in pods)
                components["etcd"] = "healthy" if running else "degraded"

        # Check kube-apiserver
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", "kube-system",
             "-l", "component=kube-apiserver", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout).get("items", [])
            if pods:
                running = all(p.get("status", {}).get("phase") == "Running" for p in pods)
                components["apiserver"] = "healthy" if running else "degraded"

        # Check kube-scheduler
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", "kube-system",
             "-l", "component=kube-scheduler", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout).get("items", [])
            if pods:
                running = all(p.get("status", {}).get("phase") == "Running" for p in pods)
                components["scheduler"] = "healthy" if running else "degraded"

        # Check kube-controller-manager
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", "kube-system",
             "-l", "component=kube-controller-manager", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pods = json.loads(result.stdout).get("items", [])
            if pods:
                running = all(p.get("status", {}).get("phase") == "Running" for p in pods)
                components["controller_manager"] = "healthy" if running else "degraded"

    except:
        pass

    return components

def get_node_details(kubeconfig_path: str) -> list:
    """Get detailed node information including OS and kernel version"""
    node_details = []

    try:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "nodes", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            nodes_data = json.loads(result.stdout)
            nodes = nodes_data.get("items", [])

            for node in nodes:
                metadata = node.get("metadata", {})
                status = node.get("status", {})
                node_info = status.get("nodeInfo", {})

                # Get roles
                labels = metadata.get("labels", {})
                roles = []
                if "node-role.kubernetes.io/control-plane" in labels or "node-role.kubernetes.io/master" in labels:
                    roles.append("control-plane")
                if "node-role.kubernetes.io/etcd" in labels:
                    roles.append("etcd")
                if not roles:
                    roles.append("worker")

                # Check ready status
                ready_status = "NotReady"
                conditions = status.get("conditions", [])
                for condition in conditions:
                    if condition.get("type") == "Ready":
                        ready_status = "Ready" if condition.get("status") == "True" else "NotReady"
                        break

                # Get IP addresses
                internal_ip = None
                external_ip = None
                addresses = status.get("addresses", [])
                for addr in addresses:
                    if addr.get("type") == "InternalIP":
                        internal_ip = addr.get("address")
                    elif addr.get("type") == "ExternalIP":
                        external_ip = addr.get("address")

                node_details.append({
                    "name": metadata.get("name", "unknown"),
                    "roles": ", ".join(roles),
                    "status": ready_status,
                    "internal_ip": internal_ip,
                    "external_ip": external_ip,
                    "os_image": node_info.get("osImage", "unknown"),
                    "kernel": node_info.get("kernelVersion", "unknown"),
                    "container_runtime": node_info.get("containerRuntimeVersion", "unknown"),
                    "version": node_info.get("kubeletVersion", "unknown")
                })
    except:
        pass

    return node_details

def get_namespaces_info(kubeconfig_path: str) -> list:
    """Get namespaces and pod counts"""
    namespaces = []

    try:
        # Get all namespaces
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "namespaces", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            ns_data = json.loads(result.stdout)
            ns_list = ns_data.get("items", [])

            for ns in ns_list:
                ns_name = ns.get("metadata", {}).get("name", "")

                # Get pod count for this namespace
                pod_result = subprocess.run(
                    ["kubectl", "--kubeconfig", kubeconfig_path, "get", "pods", "-n", ns_name, "-o", "json"],
                    capture_output=True, text=True, timeout=10
                )

                pod_count = 0
                running_count = 0
                if pod_result.returncode == 0:
                    pod_data = json.loads(pod_result.stdout)
                    pods = pod_data.get("items", [])
                    pod_count = len(pods)
                    running_count = sum(1 for p in pods if p.get("status", {}).get("phase") == "Running")

                namespaces.append({
                    "name": ns_name,
                    "total_pods": pod_count,
                    "running_pods": running_count,
                    "status": ns.get("status", {}).get("phase", "Active")
                })
    except:
        pass

    return namespaces

def get_crds_info(kubeconfig_path: str) -> list:
    """Get Custom Resource Definitions"""
    crds = []

    try:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig_path, "get", "crds", "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            crd_data = json.loads(result.stdout)
            crd_items = crd_data.get("items", [])

            for crd in crd_items:
                metadata = crd.get("metadata", {})
                spec = crd.get("spec", {})

                # Get API versions
                versions = spec.get("versions", [])
                api_versions = [v.get("name") for v in versions if v.get("served", False)]

                crds.append({
                    "name": metadata.get("name", "unknown"),
                    "group": spec.get("group", ""),
                    "scope": spec.get("scope", ""),
                    "kind": spec.get("names", {}).get("kind", ""),
                    "versions": api_versions
                })
    except:
        pass

    return crds
