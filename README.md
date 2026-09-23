# Secure Proxy

Secure Proxy runs a small proxy server on an AWS EC2 instance and a local client
on your computer. Your browser connects to the local client, and the local
client forwards traffic to the AWS server with a shared auth token.

## Configuration

Create local environment files from the example:

```bash
cp .env.example .env
```

Do not commit `.env`, certificate files, private keys, or real AWS IPs. They are
ignored by `.gitignore`.

Required on both the AWS server and local client:

```bash
export PROXY_AUTH_TOKEN="$(openssl rand -hex 32)"
```

Required on the local client:

```bash
export PROXY_SERVER_HOST="<your-ec2-elastic-ip-or-public-dns>"
export PROXY_SERVER_PORT=9000
```

`AWS_PROXY_HOST` and `AWS_PUBLIC_IP` are also supported as aliases, but
`PROXY_SERVER_HOST` is the canonical variable.

## AWS Setup

1. Create an EC2 instance, for example Ubuntu 22.04 or 24.04.
2. Give it an Elastic IP so the proxy address does not change after restarts.
3. In the EC2 security group, allow inbound TCP `9000` only from your own public
   IP address. Avoid opening this port to `0.0.0.0/0`.
4. SSH into the instance and install Python 3.11+.
5. Copy or clone this repository onto the instance.
6. Start the server:

```bash
cd Secure-Proxy
export PROXY_AUTH_TOKEN="<same-token-as-local-client>"
export SERVER_LISTEN_HOST=0.0.0.0
export PROXY_SERVER_PORT=9000
PYTHONPATH=secure-proxy python3 -m server.main
```

The server listens on `0.0.0.0:9000` inside AWS. The security group controls who
can reach it from the internet.

## Local Client

Run this on your computer:

```bash
cd Secure-Proxy
export PROXY_AUTH_TOKEN="<same-token-as-aws-server>"
export PROXY_SERVER_HOST="<your-ec2-elastic-ip-or-public-dns>"
export PROXY_SERVER_PORT=9000
export CLIENT_LISTEN_HOST=127.0.0.1
export CLIENT_LISTEN_PORT=8080
PYTHONPATH=secure-proxy python3 -m client.main
```

Configure your browser or operating system HTTP/HTTPS proxy to:

```text
127.0.0.1:8080
```

## Optional TLS

The auth token protects access, but without TLS the token and proxied traffic
between your local client and AWS are not encrypted by this app. Enable TLS for
safer public-internet use:

AWS server:

```bash
export CLIENT_SERVER_TLS=true
export PROXY_TLS_CERT_PATH=/etc/secure-proxy/server.crt
export PROXY_TLS_KEY_PATH=/etc/secure-proxy/server.key
```

Local client:

```bash
export CLIENT_SERVER_TLS=true
export PROXY_CA_CERT_PATH=/path/to/ca-or-server.crt
```

If you use a self-signed certificate, make sure its subject/SAN matches the
value in `PROXY_SERVER_HOST`.
