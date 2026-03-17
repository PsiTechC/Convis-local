#!/bin/bash
set -e

# ============================================
# Convis VPS Deployment Script
# ============================================
# Prerequisites on VPS:
#   - Ubuntu 22.04+ with Docker & Docker Compose installed
#   - DNS A records pointing to VPS IP:
#       api.convis.ai    → <VPS_IP>
#       webapp.convis.ai → <VPS_IP>
#   - Ports 80, 443 open in firewall
#
# Usage:
#   1. First time:  ./deploy-vps.sh setup
#   2. Deploy:      ./deploy-vps.sh deploy
#   3. SSL certs:   ./deploy-vps.sh ssl
#   4. Logs:        ./deploy-vps.sh logs
#   5. Status:      ./deploy-vps.sh status
# ============================================

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env.production"
DOMAIN_API="api.convis.ai"
DOMAIN_WEB="webapp.convis.ai"
EMAIL="no-reply@convis.ai"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---- Commands ----

setup() {
    log "Setting up VPS for Convis deployment..."

    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        log "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker $USER
        warn "Docker installed. You may need to log out and back in for group changes."
    else
        log "Docker already installed: $(docker --version)"
    fi

    # Install Docker Compose plugin if not present
    if ! docker compose version &> /dev/null; then
        log "Installing Docker Compose plugin..."
        sudo apt-get update && sudo apt-get install -y docker-compose-plugin
    else
        log "Docker Compose already installed: $(docker compose version)"
    fi

    # Copy production env
    if [ ! -f ".env" ] || [ "$1" = "--force" ]; then
        log "Copying .env.production → .env"
        cp "$ENV_FILE" .env
    else
        warn ".env already exists. Use './deploy-vps.sh setup --force' to overwrite."
    fi

    # Create required directories
    mkdir -p nginx/ssl

    log "Setup complete! Next steps:"
    echo "  1. Edit .env with your production values"
    echo "  2. Point DNS records to this server's IP"
    echo "  3. Run: ./deploy-vps.sh ssl"
    echo "  4. Run: ./deploy-vps.sh deploy"
}

ssl() {
    log "Obtaining SSL certificates from Let's Encrypt..."

    # Start nginx temporarily with HTTP-only config for ACME challenge
    # Create a minimal nginx config for cert issuance
    cat > /tmp/nginx-certbot.conf << 'NGINX_CONF'
events { worker_connections 1024; }
http {
    server {
        listen 80;
        server_name api.convis.ai webapp.convis.ai;
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        location / {
            return 200 'Waiting for SSL setup...';
            add_header Content-Type text/plain;
        }
    }
}
NGINX_CONF

    # Stop any running containers
    docker compose down 2>/dev/null || true

    # Run temporary nginx for ACME challenge
    log "Starting temporary nginx for certificate verification..."
    docker run -d --name certbot-nginx \
        -p 80:80 \
        -v /tmp/nginx-certbot.conf:/etc/nginx/nginx.conf:ro \
        -v convis_certbot-www:/var/www/certbot \
        nginx:alpine

    # Get certificates
    log "Requesting certificate for $DOMAIN_API..."
    docker run --rm \
        -v convis_certbot-etc:/etc/letsencrypt \
        -v convis_certbot-www:/var/www/certbot \
        certbot/certbot certonly \
        --webroot --webroot-path=/var/www/certbot \
        --email "$EMAIL" --agree-tos --no-eff-email \
        -d "$DOMAIN_API"

    log "Requesting certificate for $DOMAIN_WEB..."
    docker run --rm \
        -v convis_certbot-etc:/etc/letsencrypt \
        -v convis_certbot-www:/var/www/certbot \
        certbot/certbot certonly \
        --webroot --webroot-path=/var/www/certbot \
        --email "$EMAIL" --agree-tos --no-eff-email \
        -d "$DOMAIN_WEB"

    # Cleanup temporary nginx
    docker stop certbot-nginx && docker rm certbot-nginx

    log "SSL certificates obtained successfully!"
    log "Now run: ./deploy-vps.sh deploy"
}

deploy() {
    log "Deploying Convis to VPS..."

    # Verify .env exists
    [ -f ".env" ] || error ".env file not found. Run './deploy-vps.sh setup' first."

    # Build and start all services
    log "Building Docker images..."
    docker compose --env-file .env build

    log "Starting services..."
    docker compose --env-file .env up -d

    log "Waiting for services to start..."
    sleep 10

    # Check health
    status

    log "Deployment complete!"
    echo ""
    echo "  API:      https://$DOMAIN_API"
    echo "  Frontend: https://$DOMAIN_WEB"
    echo "  Health:   https://$DOMAIN_API/health"
    echo ""
}

update() {
    log "Updating Convis deployment..."

    # Rebuild only changed images and restart
    docker compose --env-file .env build
    docker compose --env-file .env up -d --remove-orphans

    log "Update complete!"
}

logs() {
    SERVICE=${2:-""}
    if [ -z "$SERVICE" ]; then
        docker compose logs -f --tail=100
    else
        docker compose logs -f --tail=100 "$SERVICE"
    fi
}

status() {
    log "Service status:"
    docker compose ps
    echo ""

    # Health check
    if curl -sf "http://localhost:8010/health" > /dev/null 2>&1; then
        log "API health: ${GREEN}OK${NC}"
    else
        warn "API health: NOT RESPONDING (may still be starting)"
    fi
}

stop() {
    log "Stopping all services..."
    docker compose down
    log "All services stopped."
}

restart() {
    log "Restarting services..."
    docker compose restart
    log "Services restarted."
}

# ---- Main ----

case "${1:-help}" in
    setup)   setup "$2" ;;
    ssl)     ssl ;;
    deploy)  deploy ;;
    update)  update ;;
    logs)    logs "$@" ;;
    status)  status ;;
    stop)    stop ;;
    restart) restart ;;
    help|*)
        echo "Usage: ./deploy-vps.sh <command>"
        echo ""
        echo "Commands:"
        echo "  setup    - Install Docker, prepare .env file"
        echo "  ssl      - Obtain SSL certificates from Let's Encrypt"
        echo "  deploy   - Build and start all services"
        echo "  update   - Rebuild and restart (for code changes)"
        echo "  logs     - View logs (optional: logs api|web|nginx)"
        echo "  status   - Check service status and health"
        echo "  stop     - Stop all services"
        echo "  restart  - Restart all services"
        ;;
esac
