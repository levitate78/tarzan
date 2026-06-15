# ── Build stage ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Run as non-root
RUN addgroup -S tarzan && adduser -S tarzan -G tarzan \
    && chown -R tarzan:tarzan /var/cache/nginx /var/run /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown tarzan:tarzan /var/run/nginx.pid

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx needs to write its temp dirs even when running unprivileged
RUN mkdir -p /var/cache/nginx/client_temp /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp /var/cache/nginx/uwsgi_temp /var/cache/nginx/scgi_temp \
    && chown -R tarzan:tarzan /var/cache/nginx /usr/share/nginx/html /etc/nginx/conf.d

USER tarzan

# Listen on an unprivileged port since the container runs as non-root
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
