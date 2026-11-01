#!/bin/bash
# First boot only (EC2 user data, a Terraform template): Docker, the Compose plugin, and the
# first release. Later releases go through up.sh, so this never needs to change on a server.
set -euxo pipefail
exec > >(tee -a /var/log/actie-bootstrap.log) 2>&1

dnf install -y docker
systemctl enable --now docker

# The Compose plugin from Docker's release, checked against its published SHA-256.
compose=/usr/libexec/docker/cli-plugins/docker-compose
mkdir -p "$(dirname "$compose")"
curl -fsSL -o "$compose" \
  https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-linux-x86_64
echo "40343e21ca777173e69cff5dbafeb37c6f81f3b0d57d9e597f036e95eb63e76a  $compose" | sha256sum --check
chmod 755 "$compose"

# Swap: 2 GB of memory is enough, a little room for image pulls and upgrades.
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=1024 && chmod 600 /swapfile
  mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

mkdir -p /opt/actie && cd /opt/actie
echo "${region}" >region
echo "${site_address}" >site
curl -fsSL -o up.sh \
  "https://raw.githubusercontent.com/Aletimo03/Actie-AI/${release}/deploy/aws/server/up.sh"
chmod 755 up.sh
./up.sh "${release}"
