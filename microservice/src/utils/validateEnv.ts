import Joi from 'joi';
import { logger } from './logger';

const envSchema = Joi.object({
  NODE_ENV: Joi.string()
    .valid('development', 'production', 'test')
    .default('development'),
  
  PORT: Joi.number()
    .port()
    .default(3000),
  
  // 0xGasless Configuration
  CHAIN_ID: Joi.string()
    .required()
    .valid('43114', '1', '56', '137', '250', '42161', '10', '8453') // Supported chains
    .messages({
      'any.required': 'CHAIN_ID is required',
      'any.only': 'CHAIN_ID must be one of the supported networks: Avalanche (43114), Ethereum (1), BSC (56), Polygon (137), Fantom (250), Arbitrum (42161), Optimism (10), Base (8453)'
    }),
  
  PRIVATE_KEY: Joi.string()
    .pattern(/^0x[a-fA-F0-9]{64}$/)
    .required()
    .messages({
      'any.required': 'PRIVATE_KEY is required',
      'string.pattern.base': 'PRIVATE_KEY must be a valid 64-character hex string starting with 0x'
    }),
  
  RPC_URL: Joi.string()
    .uri({ scheme: ['http', 'https', 'ws', 'wss'] })
    .required()
    .messages({
      'any.required': 'RPC_URL is required',
      'string.uri': 'RPC_URL must be a valid HTTP/HTTPS/WS/WSS URL'
    }),
  
  API_KEY: Joi.string()
    .required()
    .messages({
      'any.required': 'API_KEY is required for 0xGasless'
    }),
  
  OPENROUTER_API_KEY: Joi.string()
    .required()
    .messages({
      'any.required': 'OPENROUTER_API_KEY is required for LangChain LLM'
    }),
  
  // Security Configuration
  ALLOWED_ORIGINS: Joi.string()
    .default('http://localhost:3000')
    .description('Comma-separated list of allowed CORS origins'),
  
  RATE_LIMIT_WINDOW_MS: Joi.number()
    .positive()
    .default(15 * 60 * 1000) // 15 minutes
    .description('Rate limiting window in milliseconds'),
  
  RATE_LIMIT_MAX_REQUESTS: Joi.number()
    .positive()
    .default(100)
    .description('Maximum requests per window per IP'),
  
  // Optional Configuration
  ENABLE_DOCS: Joi.string()
    .valid('true', 'false')
    .default('false')
    .description('Enable API documentation in production'),
  
  LOG_LEVEL: Joi.string()
    .valid('error', 'warn', 'info', 'debug')
    .default('info')
    .description('Winston log level'),
  
  // Gas Configuration (optional)
  MAX_GAS_PRICE_GWEI: Joi.number()
    .positive()
    .description('Maximum gas price in Gwei for transactions'),
  
  // Slippage Configuration (optional)
  DEFAULT_SLIPPAGE_TOLERANCE: Joi.number()
    .min(0.1)
    .max(50)
    .default(1)
    .description('Default slippage tolerance percentage'),
  
  // Timeout Configuration (optional)
  AGENT_TIMEOUT_MS: Joi.number()
    .positive()
    .default(120000) // 2 minutes
    .description('Agent operation timeout in milliseconds')

}).unknown(true); // Allow additional environment variables

export function validateEnv(): void {
  const { error, value } = envSchema.validate(process.env);

  if (error) {
    const errorMessage = `Environment validation failed: ${error.details.map(detail => detail.message).join(', ')}`;
    logger.error(errorMessage);
    
    // In production, exit immediately on validation failure
    if (process.env.NODE_ENV === 'production') {
      console.error(errorMessage);
      process.exit(1);
    } else {
      // In development, log warning but continue
      logger.warn('Continuing with invalid environment in development mode');
      console.warn('\n⚠️  Environment Configuration Issues:');
      error.details.forEach(detail => {
        console.warn(`   - ${detail.message}`);
      });
      console.warn('\n💡 Check your .env file or environment variables\n');
    }
  } else {
    logger.info('✅ Environment validation passed');
    
    // Log configuration summary (excluding sensitive data)
    logger.info(`🌐 Running on chain ID: ${value.CHAIN_ID}`);
    logger.info(`🔗 RPC URL: ${value.RPC_URL.replace(/\/\/.*@/, '//***@')}`); // Hide credentials in URL
    logger.info(`🛡️  Security: CORS origins = ${value.ALLOWED_ORIGINS}`);
    logger.info(`⏱️  Rate limiting: ${value.RATE_LIMIT_MAX_REQUESTS} requests per ${value.RATE_LIMIT_WINDOW_MS / 1000}s`);
    
    if (value.NODE_ENV === 'development') {
      logger.info('🚧 Development mode: Enhanced logging and error details enabled');
    }
  }
}

// Export validated environment with proper types
export interface ValidatedEnv {
  NODE_ENV: 'development' | 'production' | 'test';
  PORT: number;
  CHAIN_ID: string;
  PRIVATE_KEY: string;
  RPC_URL: string;
  API_KEY: string;
  OPENROUTER_API_KEY: string;
  ALLOWED_ORIGINS: string;
  RATE_LIMIT_WINDOW_MS: number;
  RATE_LIMIT_MAX_REQUESTS: number;
  ENABLE_DOCS: string;
  LOG_LEVEL: 'error' | 'warn' | 'info' | 'debug';
  MAX_GAS_PRICE_GWEI?: number;
  DEFAULT_SLIPPAGE_TOLERANCE: number;
  AGENT_TIMEOUT_MS: number;
}

export function getValidatedEnv(): ValidatedEnv {
  const { value } = envSchema.validate(process.env);
  return value as ValidatedEnv;
}
