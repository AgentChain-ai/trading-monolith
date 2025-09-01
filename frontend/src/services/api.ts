import axios from 'axios'
import { DashboardData, TradingThesis, PredictionResponse, IngestRequest, FeedbackRequest } from '../types'

const API_BASE_URL = 'https://api.agentchain.trade/api/v1'  // In development, call backend directly

// Create axios instance with default config
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 seconds
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`)
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export const apiClient = {
  // Health check
  async healthCheck() {
    const response = await api.get('/health/detailed')
    return response.data
  },

  // Token ingestion
  async ingestToken(token: string, hoursBack: number = 24, maxArticles: number = 20) {
    const response = await api.post('/ingest', {
      token,
      hours_back: hoursBack,
      max_articles: maxArticles,
    } as IngestRequest)
    return response.data
  },

  // Get token features
  async getTokenFeatures(token: string, bucketTs?: string, hoursBack: number = 24) {
    const params = new URLSearchParams({
      hours_back: hoursBack.toString(),
    })
    if (bucketTs) {
      params.append('bucket_ts', bucketTs)
    }
    
    const response = await api.get(`/features/${token}?${params}`)
    return response.data
  },

  // Get prediction
  async getTokenPrediction(token: string, horizonMinutes: number = 60): Promise<PredictionResponse> {
    const response = await api.get(`/predict/${token}?horizon_minutes=${horizonMinutes}`)
    return response.data
  },

  // Get trading thesis
  async getTradingThesis(token: string, windowMinutes: number = 60): Promise<TradingThesis> {
    const response = await api.get(`/thesis/${token}?window_minutes=${windowMinutes}`)
    return response.data
  },

  // Get ingestion status
  async getIngestionStatus(token: string) {
    const response = await api.get(`/ingestion-status/${token}`)
    return response.data
  },

  // Submit feedback
  async submitFeedback(feedback: FeedbackRequest) {
    const response = await api.post('/feedback', feedback)
    return response.data
  },

  // Get dashboard data
  async getDashboardData(token: string, hoursBack: number = 48): Promise<DashboardData> {
    const response = await api.get(`/dashboard/${token}?hours_back=${hoursBack}`)
    return response.data
  },

  // Train model
  async trainModel(modelType: string = 'lightgbm') {
    const response = await api.post(`/train?model_type=${modelType}`)
    return response.data
  },

  // Deposit System APIs
  async getDepositHealth() {
    const response = await api.get('/deposit/health')
    return response.data
  },

  async getSupportedChains() {
    const response = await api.get('/deposit/chains')
    return response.data
  },

  async getManagedWallets() {
    const response = await api.get('/deposit/managed-wallets')
    return response.data
  },

  async generateDepositAddress(userWalletAddress: string, chainId: number) {
    const response = await api.post('/deposit/address', {
      user_wallet_address: userWalletAddress,
      chain_id: chainId
    })
    return response.data
  },

  async recordDeposit(userWalletAddress: string, chainId: number, tokenSymbol: string, amount: string, txHash: string) {
    const response = await api.post('/deposit/record', {
      user_wallet_address: userWalletAddress,
      chain_id: chainId,
      token_symbol: tokenSymbol,
      amount: amount,
      tx_hash: txHash
    })
    return response.data
  },

  async getUserBalances(userWalletAddress: string) {
    const response = await api.get(`/deposit/balances/${userWalletAddress}`)
    return response.data
  },

  async initializeManagedWallets() {
    const response = await api.post('/deposit/initialize')
    return response.data
  },

  // Portfolio Management APIs
  async getPortfolioStatus(userAddress: string) {
    const response = await api.get(`/portfolio/status/${userAddress}`)
    return response.data
  },

  async rebalancePortfolio(userAddress: string, force: boolean = false) {
    const response = await api.post('/portfolio/rebalance', {
      user_address: userAddress,
      force: force
    })
    return response.data
  },

  async getPortfolioPredictions(userAddress: string) {
    const response = await api.get(`/portfolio/predictions/${userAddress}`)
    return response.data
  },

  async getPortfolioPerformance(userAddress: string, days: number = 30) {
    const response = await api.get(`/portfolio/performance/${userAddress}?days=${days}`)
    return response.data
  },

  async toggleAutoTrading(userAddress: string, enabled: boolean) {
    const response = await api.post(`/portfolio/auto-trade/toggle?enable=${enabled}`, {
      user_address: userAddress
    })
    return response.data
  },

  async getTradeHistory(userAddress: string, limit: number = 50) {
    const response = await api.get(`/portfolio/trades/${userAddress}?limit=${limit}`)
    return response.data
  },

  async getPortfolioAnalytics() {
    const response = await api.get('/portfolio/analytics')
    return response.data
  },

  // Scheduler APIs
  async getSchedulerStatus() {
    const response = await api.get('/scheduler/status')
    return response.data
  },

  async startScheduler() {
    const response = await api.post('/scheduler/start')
    return response.data
  },

  async stopScheduler() {
    const response = await api.post('/scheduler/stop')
    return response.data
  },

  // Waitlist APIs
  async registerForWaitlist(data: {
    email: string
    wallet_address?: string
    twitter_handle?: string
    discord_handle?: string
    referral_code?: string
  }) {
    const response = await api.post('/waitlist/register', data)
    return response.data
  },

  async getWaitlistStats() {
    const response = await api.get('/waitlist/stats')
    return response.data
  },

  async getRecentRegistrations(limit: number = 10) {
    const response = await api.get(`/waitlist/recent?limit=${limit}`)
    return response.data
  },

  async getUserWaitlistInfo(email: string) {
    const response = await api.get(`/waitlist/user/${encodeURIComponent(email)}`)
    return response.data
  },

  async getReferralInfo(referralCode: string) {
    const response = await api.get(`/waitlist/referral/${referralCode}`)
    return response.data
  }
}

// Export the axios instance for direct use if needed
export { api }