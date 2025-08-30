# AgentChain.Trade Microservice - Bun Runtime
FROM oven/bun:1 as base

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json bun.lockb* ./

# Install dependencies
RUN bun install --frozen-lockfile

# Copy source code
COPY . .

# Build the application
RUN bun run build

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 --gid 1001 bunuser

# Create logs directory
RUN mkdir -p /app/logs && chown -R bunuser:nodejs /app

# Switch to non-root user
USER bunuser

# Expose port
EXPOSE 3002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3002/health || exit 1

# Start the application
CMD ["bun", "run", "start"]
