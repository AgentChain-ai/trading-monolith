import { createAppKit } from '@reown/appkit'
import { WagmiAdapter } from '@reown/appkit-adapter-wagmi'
import { mainnet, bsc, polygon, fantom, arbitrum, optimism, base, avalanche, avalancheFuji } from 'wagmi/chains'

// 1. Get projectId from https://cloud.reown.com
const projectId = '857be0522ebbf97bbd9076db7e229b1f'

// 2. Define chains (including testnet for development)
export const supportedChains = [
  mainnet,
  bsc,
  polygon,
  fantom,
  arbitrum,
  optimism,
  base,
  avalanche,
  avalancheFuji  // Testnet for development
] as const

// 3. Set up the Wagmi Adapter (Config)
export const wagmiAdapter = new WagmiAdapter({
  ssr: true,
  projectId,
  networks: [...supportedChains]
})

// 4. Create the modal
export const modal = createAppKit({
  adapters: [wagmiAdapter],
  projectId,
  networks: [...supportedChains],
  defaultNetwork: mainnet,
  metadata: {
    name: 'AgentChain.Trade',
    description: 'AI-powered multi-chain trading signals',
    url: 'https://agentchain.trade',
    icons: ['https://agentchain.trade/favicon.ico']
  },
  features: {
    analytics: true,
    email: false,
    socials: false,
    emailShowWallets: false
  },
  themeMode: 'dark',
  themeVariables: {
    '--w3m-accent': '#00d4aa',
    '--w3m-border-radius-master': '8px'
  }
})

export const config = wagmiAdapter.wagmiConfig

// Chain configuration helper
export const chainConfig = {
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
  },
  [avalancheFuji.id]: {
    name: 'Avalanche Fuji',
    symbol: 'AVAX',
    decimals: 18,
    rpcUrl: 'https://api.avax-test.network/ext/bc/C/rpc',
    blockExplorer: 'https://testnet.snowtrace.io',
    color: '#e84142'
  }
}

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

export const defaultChain = mainnet
