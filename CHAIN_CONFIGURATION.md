# Chain Configuration Guide

## Current Issue
Your wallet is connected to **Avalanche Fuji Testnet (Chain ID: 43113)** but the microservice is configured for **Avalanche Mainnet (Chain ID: 43114)**.

## Solution 1: Switch to Avalanche Mainnet (Recommended)

1. Open your wallet (MetaMask, etc.)
2. Switch network to **Avalanche Mainnet**
3. Refresh the deposit dashboard
4. The deposit flow will work normally

## Solution 2: Reconfigure Microservice for Fuji Testnet

If you specifically need to use Fuji testnet, update the microservice configuration:

### Step 1: Update Environment Variables
Edit `/microservice/.env`:

```bash
# Change from mainnet to testnet
CHAIN_ID=43113
RPC_URL="https://avalanche-fuji.infura.io/v3/YOUR_INFURA_PROJECT_ID"

# Or use public RPC
RPC_URL="https://api.avax-test.network/ext/bc/C/rpc"
```

### Step 2: Restart Microservice
```bash
cd /home/mason/Desktop/prog/onchain-island/0xgasless/microservice
bun dev
```

### Step 3: Update Backend Chain Info
The backend will automatically detect the change and work with Fuji testnet.

## Chain Status Indicators

The frontend now shows:
- **🟢 ACTIVE**: Chain is supported by microservice
- **🟠 INACTIVE**: Chain is not currently supported by microservice configuration

## Network Information

**Avalanche Mainnet (43114)**
- Status: ✅ Active
- Native Token: AVAX
- Microservice: Configured

**Avalanche Fuji Testnet (43113)** 
- Status: ⚠️ Inactive
- Native Token: AVAX
- Microservice: Not configured

## Testing

After making changes, test the deposit address generation:

```bash
# Test Fuji (should work after reconfiguration)
curl -X POST "http://localhost:8000/api/v1/deposit/address" \
  -H "Content-Type: application/json" \
  -d '{"user_wallet_address": "0x1234567890123456789012345678901234567890", "chain_id": 43113}'

# Test Mainnet (should work with current config)
curl -X POST "http://localhost:8000/api/v1/deposit/address" \
  -H "Content-Type: application/json" \
  -d '{"user_wallet_address": "0x1234567890123456789012345678901234567890", "chain_id": 43114}'
```
