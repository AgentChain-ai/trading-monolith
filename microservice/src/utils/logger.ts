import winston from 'winston';

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.colorize(),
    winston.format.printf((info: any) => {
      return `${info.timestamp} [${info.level}]: ${info.message}${info.stack ? '\n' + info.stack : ''}`;
    })
  ),
  transports: [
    new winston.transports.Console(),
    new winston.transports.File({ 
      filename: 'logs/error.log', 
      level: 'error',
      handleExceptions: true
    }),
    new winston.transports.File({ 
      filename: 'logs/combined.log',
      handleExceptions: true
    })
  ],
  exitOnError: false
});

export { logger };
