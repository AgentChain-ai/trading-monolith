import { Router, type Request, type Response, type NextFunction } from 'express';
import { logger } from '../utils/logger';
import { 
  getAgentKitForChain, 
  getSupportedChainIds, 
  getChainConfig,
  isChainSupported 
} from '../config/chains';

const router = Router();

/**
 * @swagger
 * components:
 *   schemas:
 *     BalanceResponse:
 *       type: object
 *       properties:
 *         success:
 *           type: boolean
 *         data:
 *           type: object
 *           properties:
 *             chainId:
 *               type: number
 *               description: Chain ID
 *             chainName:
 *               type: string
 *               description: Chain name
 *             smartAccount:
 *               type: string
 *               description: Smart account address
 *             eoaAddress:
 *               type: string
 *               description: EOA address
 *             balances:
 *               type: object
 *               description: Account balances
 *     MultiChainBalanceResponse:
 *       type: object
 *       properties:
 *         success:
 *           type: boolean
 *         data:
 *           type: array
 *           items:
 *             $ref: '#/components/schemas/BalanceResponse'
 */

/**
 * @swagger
 * /api/balance:
 *   get:
 *     summary: Get wallet balances for all supported chains
 *     tags: [Balance]
 *     responses:
 *       200:
 *         description: Current balances across all chains
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/MultiChainBalanceResponse'
 */
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const supportedChains = getSupportedChainIds();
    const balances = [];

    for (const chainId of supportedChains) {
      try {
        const agentkit = await getAgentKitForChain(chainId);
        const chainConfig = getChainConfig(chainId);
        
        // Get addresses and balances
        const smartAccount = await agentkit.getAddress();
        const eoaAddress = await agentkit.getEOAAddress ? await agentkit.getEOAAddress() : "Not available";
        const smartAccountBalance = await agentkit.getBalance();
        const eoaBalance = await agentkit.getEOABalance ? await agentkit.getEOABalance() : "Not available";
        
        balances.push({
          chainId,
          chainName: chainConfig.name,
          smartAccount,
          eoaAddress,
          balances: {
            smartAccount: smartAccountBalance,
            eoa: eoaBalance
          }
        });
      } catch (error: any) {
        logger.warn(`Failed to get balance for chain ${chainId}:`, error.message);
        // Continue with other chains even if one fails
        balances.push({
          chainId,
          chainName: getChainConfig(chainId).name,
          error: error.message
        });
      }
    }

    res.json({
      success: true,
      data: balances
    });

  } catch (error: any) {
    logger.error('Multi-chain balance check failed:', error);
    next(error);
  }
});

/**
 * @swagger
 * /api/balance/{chainId}:
 *   get:
 *     summary: Get wallet balances for a specific chain
 *     tags: [Balance]
 *     parameters:
 *       - in: path
 *         name: chainId
 *         required: true
 *         schema:
 *           type: integer
 *         description: Chain ID (1, 56, 137, 250, 42161, 10, 8453, 43114, 43113)
 *     responses:
 *       200:
 *         description: Current balances for the specified chain
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/BalanceResponse'
 *       400:
 *         description: Invalid or unsupported chain ID
 */
router.get('/:chainId', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const chainId = parseInt(req.params.chainId);
    
    if (!isChainSupported(chainId)) {
      return res.status(400).json({
        success: false,
        error: `Unsupported chain ID: ${chainId}. Supported chains: ${getSupportedChainIds().join(', ')}`
      });
    }

    const agentkit = await getAgentKitForChain(chainId);
    const chainConfig = getChainConfig(chainId);
    
    // Get addresses and balances
    logger.info("Available agentkit methods:", Object.getOwnPropertyNames(agentkit));
    logger.info("Available agentkit methods (prototype):", Object.getOwnPropertyNames(Object.getPrototypeOf(agentkit)));
    
    const smartAccount = await agentkit.getAddress();
    // For now, just return basic info while we debug the API
    const response = {
      chainId,
      chainName: chainConfig.name,
      smartAccount,
      debug: {
        methods: Object.getOwnPropertyNames(agentkit),
        prototypeMethods: Object.getOwnPropertyNames(Object.getPrototypeOf(agentkit))
      }
    };
    
    res.json({
      success: true,
      data: response
    });

  } catch (error: any) {
    logger.error(`Balance check failed for chain ${req.params.chainId}:`, error);
    next(error);
  }
});

/**
 * @swagger
 * /api/balance/addresses:
 *   get:
 *     summary: Get wallet addresses for all supported chains
 *     tags: [Balance]
 *     responses:
 *       200:
 *         description: Wallet addresses across all chains
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                 data:
 *                   type: array
 *                   items:
 *                     type: object
 *                     properties:
 *                       chainId:
 *                         type: number
 *                       chainName:
 *                         type: string
 *                       smartAccount:
 *                         type: string
 *                       eoaAddress:
 *                         type: string
 */
router.get('/addresses', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const supportedChains = getSupportedChainIds();
    const addresses = [];

    for (const chainId of supportedChains) {
      try {
        const agentkit = await getAgentKitForChain(chainId);
        const chainConfig = getChainConfig(chainId);
        
        // Get addresses only (faster than full balance check)
        const smartAccount = await agentkit.getAddress();
        const eoaAddress = await agentkit.getEOAAddress ? await agentkit.getEOAAddress() : "Not available";
        
        addresses.push({
          chainId,
          chainName: chainConfig.name,
          smartAccount,
          eoaAddress
        });
      } catch (error: any) {
        logger.warn(`Failed to get addresses for chain ${chainId}:`, error.message);
        // Continue with other chains even if one fails
        addresses.push({
          chainId,
          chainName: getChainConfig(chainId).name,
          error: error.message
        });
      }
    }

    res.json({
      success: true,
      data: addresses
    });

  } catch (error: any) {
    logger.error('Multi-chain address fetch failed:', error);
    next(error);
  }
});

/**
 * @swagger
 * /api/balance/chains:
 *   get:
 *     summary: Get list of supported chains
 *     tags: [Balance]
 *     responses:
 *       200:
 *         description: List of supported blockchain networks
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                 data:
 *                   type: array
 *                   items:
 *                     type: object
 *                     properties:
 *                       chainId:
 *                         type: number
 *                       name:
 *                         type: string
 *                       nativeCurrency:
 *                         type: string
 */
router.get('/chains', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const supportedChains = getSupportedChainIds();
    const chains = supportedChains.map(chainId => {
      const config = getChainConfig(chainId);
      return {
        chainId,
        name: config.name,
        nativeCurrency: config.nativeCurrency
      };
    });

    res.json({
      success: true,
      data: chains
    });

  } catch (error: any) {
    logger.error('Failed to get supported chains:', error);
    next(error);
  }
});

export { router as balanceRouter };
