# Secure Proxy

Secure Proxy is a simple proxy system that uses an AWS EC2 server as a remote proxy. It has two parts: a local client running on your computer and a proxy server running on AWS.

Your browser connects to the local client on `127.0.0.1:8080`. The client then sends the requests to the AWS proxy server. A shared authentication token is used between the client and server.

## Configuration

First, create your local `.env` file from the example:

```bash
cp .env.example .env
```

Do not upload your `.env` file, private keys, certificates, or real AWS IP address to GitHub. These files and values are excluded with `.gitignore`.

Generate an authentication token and use the same token on both the local client and AWS server:

```bash
export PROXY_AUTH_TOKEN="$(openssl rand -hex 32)"
```

On the local client, set the AWS server address:

```bash
export PROXY_SERVER_HOST="<your-ec2-elastic-ip-or-public-dns>"
export PROXY_SERVER_PORT=9000
```

`PROXY_SERVER_HOST` is the main variable used by the project. `AWS_PROXY_HOST` and `AWS_PUBLIC_IP` can also be used as alternative names.

## AWS Server Setup

1. Create an AWS EC2 instance. Ubuntu 22.04 or 24.04 can be used.
2. Assign an Elastic IP to the instance so the public IP does not change after a restart.
3. In the EC2 Security Group, allow TCP port `9000` only from your own public IP address. Do not open port `9000` to `0.0.0.0/0`.
4. Connect to the instance using SSH and make sure Python 3.11 or newer is installed.
5. Clone or copy this project to the server.
6. Start the proxy server:

```bash
cd Secure-Proxy

export PROXY_AUTH_TOKEN="<same-token-as-local-client>"
export SERVER_LISTEN_HOST=0.0.0.0
export PROXY_SERVER_PORT=9000

PYTHONPATH=secure-proxy python3 -m server.main
```

The server will listen on port `9000`. The AWS Security Group determines which external clients can connect to the server.

## Local Client Setup

Run the following commands on your own computer:

```bash
cd Secure-Proxy

export PROXY_AUTH_TOKEN="<same-token-as-aws-server>"
export PROXY_SERVER_HOST="<your-ec2-elastic-ip-or-public-dns>"
export PROXY_SERVER_PORT=9000

export CLIENT_LISTEN_HOST=127.0.0.1
export CLIENT_LISTEN_PORT=8080

PYTHONPATH=secure-proxy python3 -m client.main
```

After starting the client, configure your browser or operating system to use the following proxy:

```text
127.0.0.1:8080
```

The local client receives the browser traffic and forwards it to the proxy server running on AWS.

## TLS

The project also supports TLS between the local client and the AWS server.

Without TLS, the authentication token and proxy traffic between the local client and AWS are not encrypted by the application itself. For a real public-internet deployment, TLS should be enabled.

On the AWS server:

```bash
export CLIENT_SERVER_TLS=true
export PROXY_TLS_CERT_PATH=/etc/secure-proxy/server.crt
export PROXY_TLS_KEY_PATH=/etc/secure-proxy/server.key
```

On the local client:

```bash
export CLIENT_SERVER_TLS=true
export PROXY_CA_CERT_PATH=/path/to/ca-or-server.crt
```

If a self-signed certificate is used, its subject/SAN should match the value configured in `PROXY_SERVER_HOST`.

## Security Notes

* Do not commit your `.env` file.
* Do not commit authentication tokens or private keys.
* Keep AWS port `9000` restricted to trusted IP addresses.
* Do not use `0.0.0.0/0` for the proxy port unless you specifically understand the security risks.
* Use TLS when sending proxy traffic over the public internet.

