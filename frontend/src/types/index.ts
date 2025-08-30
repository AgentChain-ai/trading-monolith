// API Response Types
export interface TradingThesis {
  token: string
  timestamp: string
  window_minutes: number
  narrative_heat: number
  consensus: number
  top_event: string
  p_up_60m: number
  confidence: string
  hype_velocity: number
  risk_polarity: number
  reasoning: string[]
  guardrails: string[]
  evidence: EvidenceItem[]
  features_snapshot: Record<string, number>
}

export interface EvidenceItem {
  title: string
  url: string
  weight: number
  event_type: string
  sentiment: number
}

export interface Bucket {
  id: number
  token: string
  bucket_ts: string
  narrative_heat: number
  positive_heat: number
  negative_heat: number
  consensus: number
  hype_velocity: number
  risk_polarity: number
  event_distribution: Record<string, number>
  top_event: string
  liquidity_usd?: number
  trades_count_change?: number
  spread_estimate?: number
  created_at: string
}

export interface Article {
  id: number
  token: string
  url: string
  site_name: string
  title: string
  sentiment_score: number
  final_weight: number
  event_probs: Record<string, number>
  created_at: string
}

export interface DashboardData {
  token: string
  current_thesis: TradingThesis
  buckets: Bucket[]
  recent_articles: Article[]
  summary: {
    total_buckets: number
    avg_narrative_heat: number
    latest_consensus: number
    latest_risk_polarity: number
  }
}

export interface PredictionResponse {
  token: string
  probability_up: number
  confidence: string
  timestamp: string
  window_minutes: number
  feature_importance: Record<string, number>
  features_used: Record<string, number>
}

// API Request Types
export interface IngestRequest {
  token: string
  hours_back?: number
  max_articles?: number
}

export interface FeedbackRequest {
  token: string
  bucket_ts: string
  actual_return: number
}

// Component Props Types
export interface DashboardProps {
  token: string
  data: DashboardData
  onRefresh: () => void
}

export interface ThesisCardProps {
  thesis: TradingThesis
}

export interface NarrativeChartProps {
  buckets: Bucket[]
  height?: number
}

export interface EventDistributionProps {
  eventDistribution: Record<string, number>
}

export interface EvidenceListProps {
  evidence: EvidenceItem[]
}

export interface FeatureImportanceProps {
  featureImportance: Record<string, number>
}

// Chart Data Types
export interface ChartDataPoint {
  timestamp: string
  narrative_heat: number
  positive_heat: number
  negative_heat: number
  hype_velocity: number
  consensus: number
  risk_polarity: number
  p_up_60m?: number
}

// Utility Types
export type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW'

export type EventType = 
  | 'listing'
  | 'partnership' 
  | 'hack'
  | 'depeg'
  | 'regulatory'
  | 'funding'
  | 'tech'
  | 'market-note'
  | 'op-ed'

// API Error Type
export interface ApiError {
  detail: string
  status_code: number
}

// Deposit System Types
export interface Chain {
  chain_id: number
  name: string
  native_currency: string
}

export interface ManagedWallet {
  chain_id: number
  chain_name: string
  smart_account: string
  eoa_address: string
}

export interface DepositAddress {
  user_wallet_address: string
  chain_id: number
  chain_name: string
  deposit_address: string
  smart_account: string
  eoa_address: string
}

export interface UserBalance {
  chain_id: number
  chain_name: string
  token_symbol: string
  balance: string
  usd_value?: string
  last_updated: string
}

export interface DepositTransaction {
  id: number
  user_wallet_address: string
  chain_id: number
  token_symbol: string
  amount: string
  tx_hash: string
  status: 'pending' | 'confirmed' | 'failed'
  created_at: string
  confirmed_at?: string
}

export interface DepositHealth {
  success: boolean
  microservice_connected: boolean
  total_chains: number
  active_chains: number
  chains: Chain[]
  timestamp: string
}