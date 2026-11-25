FROM alpine:latest

#Dependencies (including openssh-client for the SSH Deploy Key and ca-certificates for HTTPS Harbor)
RUN apk upgrade --no-cache && \
    apk add --no-cache git curl jq ca-certificates openssh-client

# Create non-root system user
RUN adduser -D -u 10001 app

WORKDIR /home/app

# Copy your script and set ownership + execute permissions cleanly
COPY --chown=app:app backup-harbor.sh .
RUN chmod +x backup-harbor.sh

# Switch to non-root user
USER app

# Set script as container entrypoint
ENTRYPOINT ["/home/app/backup-harbor.sh"]