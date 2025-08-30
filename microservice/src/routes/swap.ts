import { Router, type Request, type Response, type NextFunction } from 'express';
import Joi from 'joi';
import { Agentkit, AgentkitToolkit } from '@0xgasless/agentkit';
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { MemorySaver } from '@langchain/langgraph';
import { HumanMessage } from '@langchain/core/messages';
import { logger } from '../utils/logger';

const router = Router();

// Global agent instance
let globalAgent: any = null;
let globalConfig: any = null;

// Initialize the LangChain agent (same as your main agent)
async function initializeAgent() {
  if (!globalAgent) {
    try {
      // Initialize LLM
      const llm = new ChatOpenAI({
        model: "gpt-4o-mini",
        apiKey: process.env.OPENROUTER_API_KEY,
        configuration: {
          baseURL: "https://openrouter.ai/api/v1",
        },
      });

      // Initialize 0xGasless AgentKit
      const agentkit = await Agentkit.configureWithWallet({
        privateKey: process.env.PRIVATE_KEY as `0x${string}`,
        rpcUrl: process.env.RPC_URL as string,
        apiKey: process.env.API_KEY as string,
        chainID: Number(process.env.CHAIN_ID) || 43114,
      });

      // Initialize AgentKit Toolkit and get tools
      const agentkitToolkit = new AgentkitToolkit(agentkit);
      const tools = agentkitToolkit.getTools();

      const memory = new MemorySaver();
      const agentConfig = { configurable: { thread_id: "microservice-agent" } };

      const agent = createReactAgent({
        llm,
        tools,
        checkpointSaver: memory,
        messageModifier: `
          You are a helpful agent that can interact with EVM chains using 0xGasless smart accounts. You can perform 
          gasless transactions using the account abstraction wallet. You can check balances of ETH and any ERC20 token 
          by providing their contract address. If someone asks you to do something you can't do with your currently 
          available tools, you must say so. Be concise and helpful with your responses.
        `,
      });

      globalAgent = agent;
      globalConfig = agentConfig;
      
      logger.info('Agent initialized successfully');
    } catch (error) {
      logger.error('Failed to initialize agent:', error);
      throw error;
    }
  }
  
  return { agent: globalAgent, config: globalConfig };
}

// Helper function to process agent stream
async function processAgentCommand(command: string): Promise<string> {
  const { agent, config } = await initializeAgent();
  
  let result = '';
  const stream = await agent.stream({ messages: [new HumanMessage(command)] }, config);
  
  for await (const chunk of stream) {
    if ("agent" in chunk && chunk.agent?.messages) {
      const messages = Array.isArray(chunk.agent.messages) 
        ? chunk.agent.messages 
        : [chunk.agent.messages];
      
      for (const message of messages) {
        if (message?.content) {
          result += message.content + '\n';
        }
      }
    } else if ("tools" in chunk && chunk.tools?.messages) {
      const messages = Array.isArray(chunk.tools.messages) 
        ? chunk.tools.messages 
        : [chunk.tools.messages];
      
      for (const message of messages) {
        if (message?.content) {
          result += message.content + '\n';
        }
      }
    }
  }
  
  return result.trim();
}

// Request validation schemas
const swapSchema = Joi.object({
  tokenInSymbol: Joi.string().optional(),
  tokenIn: Joi.string().pattern(/^0x[a-fA-F0-9]{40}$/).optional(),
  tokenOutSymbol: Joi.string().optional(), 
  tokenOut: Joi.string().pattern(/^0x[a-fA-F0-9]{40}$/).optional(),
  amount: Joi.string().required(),
  slippage: Joi.string().default('auto'),
  wait: Joi.boolean().default(true),
  approveMax: Joi.boolean().default(false)
}).custom((value: any, helpers: any) => {
  if (!value.tokenInSymbol && !value.tokenIn) {
    return helpers.error('any.custom', { 
      message: 'Either tokenInSymbol or tokenIn must be provided' 
    });
  }
  if (!value.tokenOutSymbol && !value.tokenOut) {
    return helpers.error('any.custom', { 
      message: 'Either tokenOutSymbol or tokenOut must be provided' 
    });
  }
  return value;
});

/**
 * @swagger
 * /api/swap/execute:
 *   post:
 *     summary: Execute a token swap
 *     tags: [Swap]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - amount
 *             properties:
 *               tokenInSymbol:
 *                 type: string
 *                 example: "USDC"
 *               tokenOutSymbol:
 *                 type: string
 *                 example: "USDT"
 *               amount:
 *                 type: string
 *                 example: "0.001"
 *               slippage:
 *                 type: string
 *                 example: "auto"
 *               wait:
 *                 type: boolean
 *                 example: true
 *               approveMax:
 *                 type: boolean
 *                 example: false
 *     responses:
 *       200:
 *         description: Swap executed successfully
 */
router.post('/execute', async (req: Request, res: Response, next: NextFunction) => {
  try {
    // Validate request
    const { error, value } = swapSchema.validate(req.body);
    if (error) {
      return res.status(400).json({
        success: false,
        error: { message: error.details?.[0]?.message || 'Validation error' }
      });
    }

    logger.info('Executing swap:', value);

    // Build swap command
    let swapCommand = `Swap ${value.amount}`;
    
    if (value.tokenInSymbol) {
      swapCommand += ` ${value.tokenInSymbol}`;
    } else if (value.tokenIn) {
      swapCommand += ` of token ${value.tokenIn}`;
    }
    
    swapCommand += ' to';
    
    if (value.tokenOutSymbol) {
      swapCommand += ` ${value.tokenOutSymbol}`;
    } else if (value.tokenOut) {
      swapCommand += ` token ${value.tokenOut}`;
    }

    if (value.slippage && value.slippage !== 'auto') {
      swapCommand += ` with ${value.slippage}% slippage`;
    }

    if (value.approveMax) {
      swapCommand += ' with max approval';
    }

    if (!value.wait) {
      swapCommand += ' without waiting for confirmation';
    }

    logger.info('Executing command:', swapCommand);

    const startTime = Date.now();
    const result = await processAgentCommand(swapCommand);
    const executionTime = Date.now() - startTime;

    logger.info(`Swap completed in ${executionTime}ms`);

    // Parse result for transaction details
    let transactionHash = null;
    let userOpHash = null;
    let success = false;

    if (result.includes('Transaction Hash:')) {
      const hashMatch = result.match(/Transaction Hash: (0x[a-fA-F0-9]{64})/);
      if (hashMatch) transactionHash = hashMatch[1];
      success = true;
    }

    if (result.includes('User Operation Hash:')) {
      const userOpMatch = result.match(/User Operation Hash: (0x[a-fA-F0-9]{64})/);
      if (userOpMatch) userOpHash = userOpMatch[1];
    }

    const isError = result.includes('Error') || 
                   result.includes('failed') || 
                   result.includes('insufficient');

    res.json({
      success: success && !isError,
      data: {
        result,
        transactionHash,
        userOpHash,
        executionTimeMs: executionTime,
        request: value,
        command: swapCommand
      }
    });

  } catch (error: any) {
    logger.error('Swap execution failed:', error);
    next(error);
  }
});

/**
 * @swagger
 * /api/swap/balance:
 *   get:
 *     summary: Get wallet balance
 *     tags: [Swap]
 *     responses:
 *       200:
 *         description: Balance retrieved successfully
 */
router.get('/balance', async (req: Request, res: Response, next: NextFunction) => {
  try {
    logger.info('Getting balance');

    const startTime = Date.now();
    const result = await processAgentCommand('Get my current balances');
    const executionTime = Date.now() - startTime;

    res.json({
      success: true,
      data: {
        result,
        executionTimeMs: executionTime
      }
    });

  } catch (error: any) {
    logger.error('Balance check failed:', error);
    next(error);
  }
});

/**
 * @swagger
 * /api/swap/address:
 *   get:
 *     summary: Get wallet address
 *     tags: [Swap]
 *     responses:
 *       200:
 *         description: Address retrieved successfully
 */
router.get('/address', async (req: Request, res: Response, next: NextFunction) => {
  try {
    logger.info('Getting address');

    const startTime = Date.now();
    const result = await processAgentCommand('What is my wallet address?');
    const executionTime = Date.now() - startTime;

    // Parse addresses from output
    const smartAccountMatch = result.match(/Smart Account: (0x[a-fA-F0-9]{40})/);
    const eoaMatch = result.match(/EOA: (0x[a-fA-F0-9]{40})/);

    res.json({
      success: true,
      data: {
        result,
        smartAccount: smartAccountMatch ? smartAccountMatch[1] : null,
        eoa: eoaMatch ? eoaMatch[1] : null,
        executionTimeMs: executionTime
      }
    });

  } catch (error: any) {
    logger.error('Address check failed:', error);
    next(error);
  }
});

export { router as swapRouter };
