# EC2 One-Time Setup

Run these steps once on a fresh Ubuntu EC2 instance.

## 1) Install Docker and Compose plugin

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

Re-login to apply Docker group membership.

## 2) Install nginx

```bash
sudo apt-get update
sudo apt-get install -y nginx
```

## 3) Clone the repository on EC2

```bash
cd ~
git clone https://github.com/mashinsp/LinkVault.git linkvault
cd ~/linkvault
```

If the folder already exists and you just want latest code:

```bash
cd ~/linkvault
git pull origin main
```

## 4) Configure nginx proxy

From your repo folder on EC2:

```bash
sudo cp deploy/nginx/linkvault.conf /etc/nginx/sites-available/linkvault
sudo ln -sf /etc/nginx/sites-available/linkvault /etc/nginx/sites-enabled/linkvault
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 5) Create server-side env file

Inside `$HOME/linkvault/.env`, create production-safe values (do not commit secrets).

At minimum:

```env
POSTGRES_USER=linkvault
POSTGRES_PASSWORD=change_me
POSTGRES_DB=linkvault
DATABASE_URL=postgresql://linkvault:change_me@db:5432/linkvault

APP_ENV=production
BASE_URL=http://your-domain-or-ec2-ip
RATE_LIMIT_PER_MINUTE=60

REDIS_URL=redis://redis:6379/0
CACHE_TTL_SECONDS=300

RABBITMQ_USER=linkvault
RABBITMQ_PASSWORD=change_me
RABBITMQ_URL=amqp://linkvault:change_me@rabbitmq:5672/
```

## 6) Start services

```bash
cd ~/linkvault
docker compose up -d --build
curl -f http://localhost:8000/health
```

Fast path (recommended for small EC2 instances):

```bash
cd ~/linkvault
bash deploy/ec2/deploy.sh
```

Observability services are profile-gated and can be started when needed:

```bash
cd ~/linkvault
docker compose --profile observability up -d
```

## 7) GitHub Actions repo sync over SSH (recommended)

The deploy workflow now syncs repo code on EC2 using SSH deploy key (not HTTPS), which is more reliable than `git pull https://...` on flaky networks.

1. Generate a deploy key pair locally:

```bash
ssh-keygen -t ed25519 -C "linkvault-deploy" -f ./linkvault_deploy_key -N ""
```

2. Add public key (`linkvault_deploy_key.pub`) to this repo:
   - GitHub repo -> Settings -> Deploy keys -> Add deploy key
   - Allow read access (write not required).

3. Add the private key as a **single-line base64** GitHub Actions secret (avoids YAML corrupting multiline PEM in the deploy script):
   - Name: `REPO_DEPLOY_KEY_B64`
   - Value: output of (Linux):

```bash
base64 -w0 < linkvault_deploy_key
```

   On macOS use `base64 -i linkvault_deploy_key | tr -d '\n'`.
