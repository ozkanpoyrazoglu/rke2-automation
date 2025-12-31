import subprocess
import tempfile
import os
import yaml
from datetime import datetime
from sqlalchemy.orm.attributes import flag_modified
from app.database import SessionLocal
from app.models import Job, JobStatus, Cluster, Node, NodeRole, NodeStatus
from app.services.encryption_service import decrypt_secret
from app.services.cluster_lock_service import release_cluster_lock, update_installation_stage

def prepare_ssh_key(secret: str) -> str:
    """
    Prepare SSH key content for Ansible usage
    - Cleans up whitespace
    - Ensures proper line endings
    - Returns cleaned key content
    """
    # Decrypt and clean up the key
    secret = secret.strip()

    # Ensure key ends with newline
    if not secret.endswith('\n'):
        secret += '\n'

    return secret

def update_cluster_inventory(cluster: Cluster, nodes: list, operation: str):
    """
    Update main cluster inventory file after scaling operations

    Args:
        cluster: Cluster object
        nodes: List of node dicts with hostname, ip, role
        operation: "add" or "remove"
    """
    cluster_dir = f"/ansible/clusters/{cluster.name}"
    inventory_path = f"{cluster_dir}/inventory.ini"

    # Read current inventory from container
    result = subprocess.run([
        "docker", "exec", "rke2-automation-ansible-runner-1",
        "cat", inventory_path
    ], capture_output=True, text=True, check=False)

    if result.returncode != 0:
        # Inventory doesn't exist yet, skip update
        return

    inventory_lines = result.stdout.split('\n')

    # Parse existing inventory
    masters_section = []
    workers_section = []
    other_lines = []
    current_section = None

    for line in inventory_lines:
        if line.strip() == '[masters]':
            current_section = 'masters'
            continue
        elif line.strip() == '[workers]':
            current_section = 'workers'
            continue
        elif line.strip().startswith('['):
            current_section = 'other'

        if current_section == 'masters' and line.strip():
            masters_section.append(line)
        elif current_section == 'workers' and line.strip():
            workers_section.append(line)
        elif current_section == 'other' or current_section is None:
            other_lines.append(line)

    # Update sections based on operation
    if operation == "add":
        for node in nodes:
            node_line = f"{node['hostname']} ansible_host={node['ip']}"
            if node['role'] == 'server':
                if node_line not in masters_section:
                    masters_section.append(node_line)
            else:  # agent
                if node_line not in workers_section:
                    workers_section.append(node_line)

    elif operation == "remove":
        hostnames_to_remove = {node['hostname'] for node in nodes}
        masters_section = [line for line in masters_section
                          if not any(hostname in line for hostname in hostnames_to_remove)]
        workers_section = [line for line in workers_section
                          if not any(hostname in line for hostname in hostnames_to_remove)]

    # Rebuild inventory content
    new_inventory = "[masters]\n"
    new_inventory += "\n".join(masters_section) + "\n\n"
    new_inventory += "[workers]\n"
    new_inventory += "\n".join(workers_section) + "\n"

    # Add other sections (k8s_cluster, etc.)
    if '[k8s_cluster:children]' not in new_inventory:
        new_inventory += "\n[k8s_cluster:children]\nmasters\nworkers\n"

    # Write updated inventory to temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ini', dir='/tmp/ansible') as f:
        f.write(new_inventory)
        temp_inv_path = f.name

    # Copy to ansible container
    subprocess.run([
        "docker", "cp", temp_inv_path,
        f"rke2-automation-ansible-runner-1:{inventory_path}"
    ], check=True)

    os.remove(temp_inv_path)

def execute_install_playbook(job_id: int):
    """
    Execute RKE2 installation playbook via ansible-runner container
    """
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()

    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        cluster = job.cluster
        cluster_dir = f"/ansible/clusters/{cluster.name}"
        playbook_path = "/ansible/playbooks/install_rke2.yml"

        # Prepare credential
        key_path = None
        if cluster.credential:
            secret = decrypt_secret(cluster.credential.encrypted_secret)
            secret = prepare_ssh_key(secret)
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem', dir='/tmp/ansible') as key_file:
                key_path = key_file.name
                key_file.write(secret)
            os.chmod(key_path, 0o600)

        # Execute playbook via docker exec
        cmd = [
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "ansible-playbook",
            playbook_path,
            "-i", f"{cluster_dir}/inventory.ini",
            "-e", f"cluster_name={cluster.name}",
            "-e", f"rke2_config={cluster_dir}/rke2-config.yaml"
        ]

        if key_path:
            cmd.extend(["--private-key", key_path])

        # Use Popen for real-time output streaming
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Store process PID for potential termination
        job.process_id = process.pid
        db.commit()

        # Stream output in real-time
        output_buffer = []
        for line in process.stdout:
            output_buffer.append(line)
            # Update job output periodically
            job.output = "".join(output_buffer)
            db.commit()

        # Wait for process to complete
        process.wait()

        # Final update
        job.output = "".join(output_buffer)
        job.status = JobStatus.SUCCESS if process.returncode == 0 else JobStatus.FAILED
        job.completed_at = datetime.utcnow()

        # Store paths
        job.playbook_path = playbook_path
        job.inventory_path = f"{cluster_dir}/inventory.ini"

        db.commit()

        # Update installation stage opportunistically if successful
        if job.status == JobStatus.SUCCESS:
            update_installation_stage(db, cluster.id)

    except Exception as e:
        job.status = JobStatus.FAILED
        job.output = f"Execution failed: {str(e)}"
        job.completed_at = datetime.utcnow()
        db.commit()

    finally:
        # Release cluster lock
        release_cluster_lock(db, cluster.id)

        # Securely delete credential file
        if key_path and os.path.exists(key_path):
            os.remove(key_path)
        db.close()

def execute_uninstall_playbook(job_id: int):
    """
    Execute RKE2 uninstallation playbook to remove RKE2 from all nodes
    """
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()

    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        cluster = job.cluster
        cluster_dir = f"/ansible/clusters/{cluster.name}"
        playbook_path = "/ansible/playbooks/uninstall_rke2.yml"

        # Prepare credential
        key_path = None
        if cluster.credential:
            secret = decrypt_secret(cluster.credential.encrypted_secret)
            secret = prepare_ssh_key(secret)
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem', dir='/tmp/ansible') as key_file:
                key_path = key_file.name
                key_file.write(secret)
            os.chmod(key_path, 0o600)

        # Execute playbook via docker exec
        cmd = [
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "ansible-playbook",
            playbook_path,
            "-i", f"{cluster_dir}/inventory.ini",
            "-e", f"rke2_data_dir={cluster.rke2_data_dir}"
        ]

        if key_path:
            cmd.extend(["--private-key", key_path])

        # Use Popen for real-time output streaming
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Store process PID for potential termination
        job.process_id = process.pid
        db.commit()

        # Stream output in real-time
        output_buffer = []
        for line in process.stdout:
            output_buffer.append(line)
            # Update job output periodically
            job.output = "".join(output_buffer)
            db.commit()

        # Wait for process to complete
        process.wait()

        # Final update
        job.output = "".join(output_buffer)
        job.status = JobStatus.SUCCESS if process.returncode == 0 else JobStatus.FAILED
        job.completed_at = datetime.utcnow()

        # Store paths
        job.playbook_path = playbook_path
        job.inventory_path = f"{cluster_dir}/inventory.ini"

        db.commit()

    except Exception as e:
        job.status = JobStatus.FAILED
        job.output = f"Uninstall failed: {str(e)}"
        job.completed_at = datetime.utcnow()
        db.commit()

    finally:
        # Release cluster lock
        release_cluster_lock(db, cluster.id)

        # Securely delete credential file
        if key_path and os.path.exists(key_path):
            os.remove(key_path)
        db.close()

def execute_add_nodes(job_id: int, cluster_id: int, nodes: list):
    """
    Execute add_node.yml playbook to add new nodes to existing cluster

    Args:
        job_id: Job ID for tracking
        cluster_id: Cluster ID
        nodes: List of node dicts with hostname, ip, role
    """
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        cluster_dir = f"/ansible/clusters/{cluster.name}"
        playbook_path = "/ansible/playbooks/add_node.yml"

        # Ensure cluster directory exists in ansible container
        subprocess.run([
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "mkdir", "-p", cluster_dir
        ], check=True)

        # Create temporary inventory for new nodes
        inventory_content = "[new_nodes]\n"
        new_servers = []
        new_agents = []

        for node in nodes:
            rke2_type = "server" if node['role'] == 'server' else "agent"
            inventory_content += f"{node['hostname']} ansible_host={node['ip']} rke2_type={rke2_type}\n"
            if node['role'] == 'server':
                new_servers.append(node['hostname'])
            else:
                new_agents.append(node['hostname'])

        inventory_content += "\n[new_servers]\n"
        for hostname in new_servers:
            inventory_content += f"{hostname}\n"

        inventory_content += "\n[new_agents]\n"
        for hostname in new_agents:
            inventory_content += f"{hostname}\n"

        # Write temporary inventory
        temp_inventory_path = f"{cluster_dir}/add_nodes_inventory.ini"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ini', dir='/tmp/ansible') as inv_file:
            inv_file.write(inventory_content)
            temp_inv_local = inv_file.name

        # Copy to ansible container
        subprocess.run([
            "docker", "cp", temp_inv_local,
            f"rke2-automation-ansible-runner-1:{temp_inventory_path}"
        ], check=True)
        os.remove(temp_inv_local)

        # Create host_vars directory if it doesn't exist
        subprocess.run([
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "mkdir", "-p", f"{cluster_dir}/host_vars"
        ], check=True)

        # Create host_vars for new nodes with role-specific config templates
        # Count existing masters to determine if new servers are joining or initial
        existing_masters = db.query(Node).filter(
            Node.cluster_id == cluster_id,
            Node.role.in_([NodeRole.INITIAL_MASTER, NodeRole.MASTER]),
            Node.status != NodeStatus.REMOVED
        ).count()

        for node in nodes:
            host_vars = {}

            if node['role'] == 'server':
                # If there are already masters, new servers are joining masters
                if existing_masters > 0:
                    host_vars['node_role'] = 'MASTER'
                    host_vars['config_template'] = 'config_joining_master.yaml.j2'
                else:
                    # This is the first master (initial master)
                    host_vars['node_role'] = 'INITIAL_MASTER'
                    host_vars['config_template'] = 'config_initial_master.yaml.j2'
                    existing_masters += 1  # Increment for next iteration
            else:
                host_vars['node_role'] = 'WORKER'
                host_vars['config_template'] = 'config_worker.yaml.j2'

            # Write host_vars file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml', dir='/tmp/ansible') as hv_file:
                yaml.dump(host_vars, hv_file, default_flow_style=False)
                temp_hv_local = hv_file.name

            # Copy to ansible container
            subprocess.run([
                "docker", "cp", temp_hv_local,
                f"rke2-automation-ansible-runner-1:{cluster_dir}/host_vars/{node['hostname']}.yaml"
            ], check=True)
            os.remove(temp_hv_local)

        # Prepare credential
        key_path = None
        if cluster.credential:
            secret = decrypt_secret(cluster.credential.encrypted_secret)
            secret = prepare_ssh_key(secret)
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem', dir='/tmp/ansible') as key_file:
                key_path = key_file.name
                key_file.write(secret)
            os.chmod(key_path, 0o600)

        # Build ansible-playbook command
        import json
        additional_sans = cluster.rke2_additional_sans if cluster.rke2_additional_sans else []
        registry_address = cluster.registry_address if cluster.registry_address else []

        cmd = [
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "ansible-playbook",
            playbook_path,
            "-i", temp_inventory_path,
            "-e", f"rke2_version={cluster.rke2_version}",
            "-e", f"rke2_data_dir={cluster.rke2_data_dir}",
            "-e", f"rke2_api_ip={cluster.rke2_api_ip}",
            "-e", f"rke2_token={cluster.rke2_token}",
            "-e", f"cni={cluster.cni or 'canal'}",
            "-e", f"rke2_additional_sans={json.dumps(additional_sans)}",
            "-e", f"custom_registry={cluster.custom_registry or 'deactive'}",
            "-e", f"custom_mirror={cluster.custom_mirror or 'deactive'}",
            "-e", f"registry_address={json.dumps(registry_address)}",
            "-e", f"registry_user={cluster.registry_user or ''}",
            "-e", f"registry_password={cluster.registry_password or ''}",
            "-e", f"ansible_user={cluster.credential.username}"
        ]

        # Add custom container images if defined
        if cluster.kube_apiserver_image:
            cmd.extend(["-e", f"kube_apiserver_image={cluster.kube_apiserver_image}"])
        if cluster.kube_controller_manager_image:
            cmd.extend(["-e", f"kube_controller_manager_image={cluster.kube_controller_manager_image}"])
        if cluster.kube_proxy_image:
            cmd.extend(["-e", f"kube_proxy_image={cluster.kube_proxy_image}"])
        if cluster.kube_scheduler_image:
            cmd.extend(["-e", f"kube_scheduler_image={cluster.kube_scheduler_image}"])
        if cluster.pause_image:
            cmd.extend(["-e", f"pause_image={cluster.pause_image}"])
        if cluster.runtime_image:
            cmd.extend(["-e", f"runtime_image={cluster.runtime_image}"])
        if cluster.etcd_image:
            cmd.extend(["-e", f"etcd_image={cluster.etcd_image}"])

        if key_path:
            cmd.extend(["--private-key", key_path])

        # Use Popen for real-time output streaming
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Store process PID
        job.process_id = process.pid
        db.commit()

        # Stream output
        output_buffer = []
        for line in process.stdout:
            output_buffer.append(line)
            job.output = "".join(output_buffer)
            db.commit()

        process.wait()

        # Update main inventory file if successful
        if process.returncode == 0:
            try:
                update_cluster_inventory(cluster, nodes, operation="add")
            except Exception as e:
                job.output += f"\n\nWarning: Failed to update main inventory: {str(e)}"

        # Final update
        job.output = "".join(output_buffer)
        job.status = JobStatus.SUCCESS if process.returncode == 0 else JobStatus.FAILED
        job.completed_at = datetime.utcnow()
        job.playbook_path = playbook_path
        job.inventory_path = temp_inventory_path
        db.commit()

    except Exception as e:
        job.status = JobStatus.FAILED
        job.output = f"Add nodes failed: {str(e)}"
        job.completed_at = datetime.utcnow()
        db.commit()

    finally:
        # Release cluster lock
        release_cluster_lock(db, cluster_id)

        # Update installation stage opportunistically
        if job.status == JobStatus.SUCCESS:
            update_installation_stage(db, cluster_id)

        if key_path and os.path.exists(key_path):
            os.remove(key_path)
        db.close()

def execute_remove_nodes(job_id: int, cluster_id: int, nodes: list):
    """
    Execute remove_node.yml playbook to remove nodes from cluster

    Args:
        job_id: Job ID for tracking
        cluster_id: Cluster ID
        nodes: List of node dicts with hostname, ip, role
    """
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    key_path = None  # Initialize before try block

    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        cluster_dir = f"/ansible/clusters/{cluster.name}"
        playbook_path = "/ansible/playbooks/remove_node.yml"

        # Ensure cluster directory exists in ansible container
        subprocess.run([
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "mkdir", "-p", cluster_dir
        ], check=True)

        # Write kubeconfig to temp file for kubectl operations
        kubeconfig_path = f"{cluster_dir}/kubeconfig_temp.yaml"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml', dir='/tmp/ansible') as kube_file:
            kube_file.write(cluster.kubeconfig)
            temp_kube_local = kube_file.name

        # Copy to ansible container
        subprocess.run([
            "docker", "cp", temp_kube_local,
            f"rke2-automation-ansible-runner-1:{kubeconfig_path}"
        ], check=True)
        os.remove(temp_kube_local)

        # Create inventory for nodes to remove
        inventory_content = "[removed_servers]\n"
        removed_servers = []
        removed_agents = []
        node_names = []

        for node in nodes:
            if node['role'] == 'server':
                removed_servers.append(node)
                inventory_content += f"{node['hostname']} ansible_host={node['ip']}\n"
            else:
                removed_agents.append(node)
            node_names.append(node['hostname'])

        inventory_content += "\n[removed_agents]\n"
        for node in removed_agents:
            inventory_content += f"{node['hostname']} ansible_host={node['ip']}\n"

        # Write inventory
        temp_inventory_path = f"{cluster_dir}/remove_nodes_inventory.ini"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ini', dir='/tmp/ansible') as inv_file:
            inv_file.write(inventory_content)
            temp_inv_local = inv_file.name

        subprocess.run([
            "docker", "cp", temp_inv_local,
            f"rke2-automation-ansible-runner-1:{temp_inventory_path}"
        ], check=True)
        os.remove(temp_inv_local)

        # Prepare credential
        if cluster.credential:
            secret = decrypt_secret(cluster.credential.encrypted_secret)
            secret = prepare_ssh_key(secret)
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem', dir='/tmp/ansible') as key_file:
                key_path = key_file.name
                key_file.write(secret)
            os.chmod(key_path, 0o600)

        # Build ansible-playbook command
        import json
        cmd = [
            "docker", "exec", "rke2-automation-ansible-runner-1",
            "ansible-playbook",
            playbook_path,
            "-i", temp_inventory_path,
            "-e", f"kubeconfig_path={kubeconfig_path}",
            "-e", f"nodes_to_remove={json.dumps(node_names)}",
            "-e", f"rke2_data_dir={cluster.rke2_data_dir}",
            "-e", f"ansible_user={cluster.credential.username}"
        ]

        if key_path:
            cmd.extend(["--private-key", key_path])

        # Use Popen for real-time output streaming
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Store process PID
        job.process_id = process.pid
        db.commit()

        # Stream output
        output_buffer = []
        for line in process.stdout:
            output_buffer.append(line)
            job.output = "".join(output_buffer)
            db.commit()

        process.wait()

        # Update main inventory file if successful
        if process.returncode == 0:
            try:
                update_cluster_inventory(cluster, nodes, operation="remove")
            except Exception as e:
                job.output += f"\n\nWarning: Failed to update main inventory: {str(e)}"

        # Final update
        job.output = "".join(output_buffer)
        job.status = JobStatus.SUCCESS if process.returncode == 0 else JobStatus.FAILED
        job.completed_at = datetime.utcnow()
        job.playbook_path = playbook_path
        job.inventory_path = temp_inventory_path
        db.commit()

    except Exception as e:
        job.status = JobStatus.FAILED
        job.output = f"Remove nodes failed: {str(e)}"
        job.completed_at = datetime.utcnow()
        db.commit()

    finally:
        # Release cluster lock
        release_cluster_lock(db, cluster_id)

        # Update installation stage opportunistically
        if job.status == JobStatus.SUCCESS:
            update_installation_stage(db, cluster_id)

        if key_path and os.path.exists(key_path):
            os.remove(key_path)
        db.close()
