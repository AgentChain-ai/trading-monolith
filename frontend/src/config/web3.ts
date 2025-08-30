import { createConfig, http } from 'wagmi'
import { mainnet, bsc, polygon, fantom, arbitrum, optimism, base, avalanche } from 'wagmi/chains'
import { walletConnect, metaMask, injected } from 'wagmi/connectors'

// Reown (WalletConnect) Project ID
const projectId = '857be0522ebbf97bbd9076db7e229b1f'

// Define supported chains for AgentChain.Trade
export const supportedChains = [
  mainnet,     // Ethereum (1)
  bsc,         // BSC (56) 
  polygon,     // Polygon (137)
  fantom,      // Fantom (250)
  arbitrum,    // Arbitrum (42161)
  optimism,    // Optimism (10)
  base,        // Base (8453)
  avalanche,   // Avalanche (43114)
] as const

// Chain configuration with RPC endpoints
export const chainConfig: Record<number, {
  name: string
  symbol: string
  decimals: number
  rpcUrl: string
  blockExplorer: string
  color: string
}> = {
  [mainnet.id]: {
    name: 'Ethereum',
    symbol: 'ETH',
    decimals: 18,
    rpcUrl: 'https://eth.llamarpc.com',
    blockExplorer: 'https://etherscan.io',
    color: '#627eea'
  },
  [bsc.id]: {
    name: 'BNB Smart Chain',
    symbol: 'BNB', 
    decimals: 18,
    rpcUrl: 'https://bsc-dataseed1.binance.org',
    blockExplorer: 'https://bscscan.com',
    color: '#f3ba2f'
  },
  [polygon.id]: {
    name: 'Polygon',
    symbol: 'MATIC',
    decimals: 18,
    rpcUrl: 'https://polygon-rpc.com',
    blockExplorer: 'https://polygonscan.com',
    color: '#8247e5'
  },
  [fantom.id]: {
    name: 'Fantom',
    symbol: 'FTM',
    decimals: 18,
    rpcUrl: 'https://rpc.ftm.tools',
    blockExplorer: 'https://ftmscan.com',
    color: '#1969ff'
  },
  [arbitrum.id]: {
    name: 'Arbitrum',
    symbol: 'ETH',
    decimals: 18,
    rpcUrl: 'https://arb1.arbitrum.io/rpc',
    blockExplorer: 'https://arbiscan.io',
    color: '#28a0f0'
  },
  [optimism.id]: {
    name: 'Optimism',
    symbol: 'ETH',
    decimals: 18,
    rpcUrl: 'https://mainnet.optimism.io',
    blockExplorer: 'https://optimistic.etherscan.io',
    color: '#ff0420'
  },
  [base.id]: {
    name: 'Base',
    symbol: 'ETH',
    decimals: 18,
    rpcUrl: 'https://mainnet.base.org',
    blockExplorer: 'https://basescan.org',
    color: '#0052ff'
  },
  [avalanche.id]: {
    name: 'Avalanche',
    symbol: 'AVAX',
    decimals: 18,
    rpcUrl: 'https://api.avax.network/ext/bc/C/rpc',
    blockExplorer: 'https://snowtrace.io',
    color: '#e84142'
  }
}

// Wagmi configuration
export const config = createConfig({
  chains: supportedChains,
  connectors: [
    metaMask(),
    walletConnect({ 
      projectId,
      showQrModal: true,
    }),
    injected({ target: 'metaMask' }),
  ],
  transports: {
    [mainnet.id]: http(chainConfig[mainnet.id].rpcUrl),
    [bsc.id]: http(chainConfig[bsc.id].rpcUrl),
    [polygon.id]: http(chainConfig[polygon.id].rpcUrl),
    [fantom.id]: http(chainConfig[fantom.id].rpcUrl),
    [arbitrum.id]: http(chainConfig[arbitrum.id].rpcUrl),
    [optimism.id]: http(chainConfig[optimism.id].rpcUrl),
    [base.id]: http(chainConfig[base.id].rpcUrl),
    [avalanche.id]: http(chainConfig[avalanche.id].rpcUrl),
  },
})

// Utility functions
export const getChainById = (chainId: number) => {
  return supportedChains.find(chain => chain.id === chainId)
}

export const getChainConfig = (chainId: number) => {
  return chainConfig[chainId]
}

export const isChainSupported = (chainId: number) => {
  return chainId in chainConfig
}

// Default chain (Ethereum)
export const defaultChain = mainnet
