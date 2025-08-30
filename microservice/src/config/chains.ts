import { Agentkit } from '@0xgasless/agentkit';
import { logger } from '../utils/logger';

// Supported chain configurations
export const SUPPORTED_CHAINS = {
  // Mainnets
  1: {
    name: 'Ethereum',
    rpcUrl: 'https://eth.llamarpc.com',
    nativeCurrency: 'ETH'
  },
  56: {
    name: 'BNB Smart Chain',
    rpcUrl: 'https://bsc-dataseed1.binance.org',
    nativeCurrency: 'BNB'
  },
  137: {
    name: 'Polygon',
    rpcUrl: 'https://polygon-rpc.com',
    nativeCurrency: 'MATIC'
  },
  250: {
    name: 'Fantom',
    rpcUrl: 'https://rpc.ftm.tools',
    nativeCurrency: 'FTM'
  },
  42161: {
    name: 'Arbitrum One',
    rpcUrl: 'https://arb1.arbitrum.io/rpc',
    nativeCurrency: 'ETH'
  },
  10: {
    name: 'Optimism',
    rpcUrl: 'https://mainnet.optimism.io',
    nativeCurrency: 'ETH'
  },
  8453: {
    name: 'Base',
    rpcUrl: 'https://mainnet.base.org',
    nativeCurrency: 'ETH'
  },
  43114: {
    name: 'Avalanche',
    rpcUrl: 'https://api.avax.network/ext/bc/C/rpc',
    nativeCurrency: 'AVAX'
  },
  // Testnets
  43113: {
    name: 'Avalanche Fuji',
    rpcUrl: 'https://api.avax-test.network/ext/bc/C/rpc',
    nativeCurrency: 'AVAX'
  }
} as const;

export type SupportedChainId = keyof typeof SUPPORTED_CHAINS;

// AgentKit instances per chain (singleton pattern)
const agentKitInstances: Map<number, any> = new Map();

/**
 * Initialize AgentKit for a specific chain
 */
export const initializeAgentKitForChain = async (chainId: number): Promise<any> => {
  // Check if chain is supported
  if (!(chainId in SUPPORTED_CHAINS)) {
    throw new Error(`Unsupported chain ID: ${chainId}`);
  }

  // Return existing instance if already initialized
  if (agentKitInstances.has(chainId)) {
    return agentKitInstances.get(chainId);
  }

  const chainConfig = SUPPORTED_CHAINS[chainId as SupportedChainId];
  
  try {
    logger.info(`Initializing AgentKit for ${chainConfig.name} (${chainId})`);
    
    const agentkit = await Agentkit.configureWithWallet({
      privateKey: process.env.PRIVATE_KEY as `0x${string}`,
      rpcUrl: chainConfig.rpcUrl,
      apiKey: process.env.API_KEY as string,
      chainID: chainId,
    });

    // Cache the instance
    agentKitInstances.set(chainId, agentkit);
    
    logger.info(`AgentKit initialized successfully for ${chainConfig.name}`);
    return agentkit;
    
  } catch (error) {
    logger.error(`Failed to initialize AgentKit for ${chainConfig.name}:`, error);
    throw error;
  }
};

/**
 * Get AgentKit instance for a specific chain
 */
export const getAgentKitForChain = async (chainId: number) => {
  return await initializeAgentKitForChain(chainId);
};

/**
 * Get all supported chain IDs
 */
export const getSupportedChainIds = (): number[] => {
  return Object.keys(SUPPORTED_CHAINS).map(Number);
};

/**
 * Get chain configuration
 */
export const getChainConfig = (chainId: number) => {
  if (!(chainId in SUPPORTED_CHAINS)) {
    throw new Error(`Unsupported chain ID: ${chainId}`);
  }
  return SUPPORTED_CHAINS[chainId as SupportedChainId];
};

/**
 * Validate if chain ID is supported
 */
export const isChainSupported = (chainId: number): boolean => {
  return chainId in SUPPORTED_CHAINS;
};
