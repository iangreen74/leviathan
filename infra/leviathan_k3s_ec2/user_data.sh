#!/bin/bash
set -e

# Set hostname
hostnamectl set-hostname ${hostname}

# Update system
apt-get update
apt-get upgrade -y

# Install basic utilities
apt-get install -y \
  curl \
  wget \
  git \
  jq \
  unzip \
  ca-certificates

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip

# Create leviathan user
useradd -m -s /bin/bash leviathan
usermod -aG sudo leviathan

# Configure SSH for leviathan user
mkdir -p /home/leviathan/.ssh
cp /home/ubuntu/.ssh/authorized_keys /home/leviathan/.ssh/authorized_keys
chown -R leviathan:leviathan /home/leviathan/.ssh
chmod 700 /home/leviathan/.ssh
chmod 600 /home/leviathan/.ssh/authorized_keys

# Signal completion
echo "User data script completed at $(date)" > /var/log/user-data-complete.log
