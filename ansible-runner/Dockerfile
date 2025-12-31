FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    openssh-client \
    sshpass \
    git \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# Install Ansible and ansible-runner
RUN pip install --no-cache-dir \
    ansible==9.1.0 \
    ansible-runner==2.3.6 \
    jinja2==3.1.3

# Create working directory
WORKDIR /ansible

# Set proper SSH config
RUN mkdir -p /root/.ssh && \
    chmod 700 /root/.ssh && \
    ssh-keyscan github.com >> /root/.ssh/known_hosts

# Disable host key checking for dynamic hosts (internal networks)
RUN echo "Host *\n\
    StrictHostKeyChecking no\n\
    UserKnownHostsFile=/dev/null\n\
    LogLevel ERROR" > /root/.ssh/config

CMD ["/bin/bash"]
