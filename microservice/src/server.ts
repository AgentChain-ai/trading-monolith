import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import swaggerJsdoc from 'swagger-jsdoc';
import swaggerUi from 'swagger-ui-express';
import dotenv from 'dotenv';
import { logger } from './utils/logger';
import { errorHandler } from './middleware/errorHandler';
import { swapRouter } from './routes/swap';
import { healthRouter } from './routes/health';
import { balanceRouter } from './routes/balance';
import { validateEnv } from './utils/validateEnv';

dotenv.config();

// Validate environment variables
validateEnv();

const app = express();
const PORT = process.env.PORT || 3003;
const isProduction = process.env.NODE_ENV === 'production';

// Security middleware
app.use(helmet({
  contentSecurityPolicy: isProduction,
  crossOriginEmbedderPolicy: isProduction
}));

app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:3000'],
  credentials: true,
  methods: ['GET', 'POST'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key']
}));

// Rate limiting - more restrictive in production
const limiter = rateLimit({
  windowMs: Number(process.env.RATE_LIMIT_WINDOW_MS) || 15 * 60 * 1000, // 15 minutes
  max: Number(process.env.RATE_LIMIT_MAX_REQUESTS) || (isProduction ? 50 : 100),
  message: 'Too many requests from this IP, please try again later.',
  standardHeaders: true,
  legacyHeaders: false,
  skip: (req) => req.path === '/api/health' // Don't rate limit health checks
});
app.use(limiter);

// Body parsing middleware with size limits
app.use(express.json({ 
  limit: '1mb',
  type: ['application/json']
}));
app.use(express.urlencoded({ 
  extended: true, 
  limit: '1mb'
}));

// Request logging in development
if (!isProduction) {
  app.use((req, res, next) => {
    logger.info(`${req.method} ${req.path} - ${req.ip}`);
    next();
  });
}

// Swagger configuration
const swaggerOptions = {
  definition: {
    openapi: '3.0.0',
    info: {
      title: '0xGasless Swap Microservice API',
      version: '1.0.0',
      description: 'Production-ready microservice for gasless token swaps using 0xGasless AgentKit',
      contact: {
        name: 'API Support',
        email: 'support@example.com'
      }
    },
    servers: [
      {
        url: `http://localhost:${PORT}`,
        description: isProduction ? 'Production server' : 'Development server'
      }
    ],
    components: {
      securitySchemes: {
        ApiKeyAuth: {
          type: 'apiKey',
          in: 'header',
          name: 'X-API-Key'
        }
      }
    }
  },
  apis: ['./src/routes/*.ts']
};

const swaggerSpec = swaggerJsdoc(swaggerOptions);

// API Documentation - only in development unless explicitly enabled
if (!isProduction || process.env.ENABLE_DOCS === 'true') {
  app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));
}

// API Routes
app.use('/api/health', healthRouter);
app.use('/api/balance', balanceRouter);
app.use('/api/swap', swapRouter);

// Root endpoint
app.get('/', (req, res) => {
  res.json({
    name: '0xGasless Swap Microservice',
    version: '1.0.0',
    status: 'running',
    environment: process.env.NODE_ENV,
    chainId: process.env.CHAIN_ID,
    documentation: !isProduction || process.env.ENABLE_DOCS === 'true' ? '/api-docs' : 'disabled',
    endpoints: {
      health: '/api/health',
      balance: '/api/balance',
      swap: '/api/swap'
    }
  });
});

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({
    success: false,
    error: { message: 'Endpoint not found' }
  });
});

// Error handling middleware (should be last)
app.use(errorHandler);

// Graceful shutdown
process.on('SIGTERM', () => {
  logger.info('SIGTERM received, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', () => {
  logger.info('SIGINT received, shutting down gracefully');
  process.exit(0);
});

// Start server
const server = app.listen(PORT, () => {
  logger.info(`🚀 0xGasless Swap Microservice running on port ${PORT}`);
  logger.info(`🌐 Environment: ${process.env.NODE_ENV}`);
  logger.info(`⛓️  Chain ID: ${process.env.CHAIN_ID}`);
  if (!isProduction || process.env.ENABLE_DOCS === 'true') {
    logger.info(`📚 API Documentation: http://localhost:${PORT}/api-docs`);
  }
  logger.info(`🏥 Health Check: http://localhost:${PORT}/api/health`);
});

// Handle server errors
server.on('error', (error: any) => {
  if (error.code === 'EADDRINUSE') {
    logger.error(`Port ${PORT} is already in use`);
  } else {
    logger.error('Server error:', error);
  }
  process.exit(1);
});

export default app;
