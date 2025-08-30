# 0xGasless Swap Microservice

A production-ready microservice that provides REST APIs for gasless token swaps using the 0xGasless AgentKit.

## 🚀 Features

- **RESTful APIs** for token swaps
- **Swagger Documentation** at `/api-docs`
- **Health Monitoring** at `/api/health`
- **Balance Checking** at `/api/balance`
- **Smart Swap Execution** at `/api/swap/execute`
- **Transaction Status** checking
- **Rate Limiting** and security middleware
- **Comprehensive Logging**
- **Input Validation**

## 📋 API Endpoints

### Health Check
- `GET /api/health` - Service health status

### Balance Management
- `GET /api/balance` - Get all wallet balances
- `POST /api/balance/tokens` - Get specific token balances

### Smart Swap
- `POST /api/swap/execute` - Execute a token swap
- `POST /api/swap/estimate` - Get swap estimation
- `GET /api/swap/status/{hash}` - Check transaction status
- `GET /api/swap/supported-tokens` - List supported tokens

## 🛠️ Setup

### 1. Install Dependencies
```bash
cd microservice
bun install
```

### 2. Configure Environment
Copy `.env.example` to `.env` and configure:

```env
PRIVATE_KEY=your_private_key
API_KEY=your_0xgasless_api_key
RPC_URL=your_rpc_url
CHAIN_ID=43114
OPENROUTER_API_KEY=your_openrouter_key
PORT=3000
```

### 3. Run Development Server
```bash
bun run dev
```

### 4. Run Production Server
```bash
bun run build
bun start
```

## 📖 API Documentation

Visit `http://localhost:3000/api-docs` for interactive Swagger documentation.

## 🧪 Testing the APIs

### Example: Execute a Swap
```bash
curl -X POST http://localhost:3000/api/swap/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tokenInSymbol": "USDC",
    "tokenOutSymbol": "USDT", 
    "amount": "0.1",
    "slippage": "auto",
    "wait": true
  }'
```

### Example: Check Balance
```bash
curl http://localhost:3000/api/balance
```

### Example: Get Supported Tokens
```bash
curl http://localhost:3000/api/swap/supported-tokens
```

## 🔒 Security Features

- **Rate Limiting**: 100 requests per 15 minutes per IP
- **CORS Protection**: Configurable allowed origins
- **Helmet Security**: Security headers
- **Input Validation**: Joi schema validation
- **Error Handling**: Comprehensive error responses

## 📊 Monitoring

- **Health Endpoint**: `/api/health`
- **Logs**: Winston logging to console and files
- **Request Tracking**: All requests logged with details

## 🏗️ Architecture

```
Backend → HTTP Request → Microservice → 0xGasless → Blockchain
                      ↓
                  Swagger Docs
                  Rate Limiting
                  Validation
                  Logging
```

## 🚀 Production Deployment

1. **Environment**: Set `NODE_ENV=production`
2. **Logging**: Configure log files and rotation
3. **Security**: Add API key authentication
4. **Monitoring**: Add health checks and alerting
5. **Load Balancing**: Run multiple instances

## 📈 Scaling

- **Horizontal**: Run multiple instances behind a load balancer
- **Caching**: Add Redis for frequently requested data
- **Database**: Store transaction history and analytics
- **Queue**: Add job queue for async processing
