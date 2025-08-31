import React, { useState, useEffect } from 'react'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  CircularProgress,
  Switch,
  FormControlLabel,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  Divider
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  Refresh,
  Settings,
  History,
  Analytics,
  PlayArrow,
  Stop
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../services/api'
import toast from 'react-hot-toast'

interface PortfolioPosition {
  token: string
  balance: number
  value_usd: number
  allocation_percent: number
  price_change_24h?: number
}

interface PortfolioData {
  user_address: string
  status: string
  total_value_usd: number
  positions: PortfolioPosition[]
  last_rebalance?: string
  performance: {
    total_return: number
    daily_return: number
    trades_count: number
  }
}

interface TradeRecord {
  token: string
  action: string
  amount: number
  usd_value: number
  status: string
  timestamp: string
  tx_hash?: string
}

interface PortfolioTabProps {
  userAddress?: string
}

const PortfolioTab: React.FC<PortfolioTabProps> = ({ userAddress = "0x1234...demo" }) => {
  const [autoTradingEnabled, setAutoTradingEnabled] = useState(false)
  const [showTradeHistory, setShowTradeHistory] = useState(false)
  const [showRebalanceDialog, setShowRebalanceDialog] = useState(false)
  const queryClient = useQueryClient()

  // Portfolio status query
  const { data: portfolio, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio', userAddress],
    queryFn: () => apiClient.getPortfolioStatus(userAddress),
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  // Portfolio predictions query
  const { data: predictions } = useQuery({
    queryKey: ['portfolio-predictions', userAddress],
    queryFn: () => apiClient.getPortfolioPredictions(userAddress),
    enabled: !!portfolio && portfolio.status === 'active',
  })

  // Trade history query
  const { data: tradeHistory } = useQuery({
    queryKey: ['trade-history', userAddress],
    queryFn: () => apiClient.getTradeHistory(userAddress),
    enabled: showTradeHistory,
  })

  // Scheduler status query
  const { data: schedulerStatus } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: () => apiClient.getSchedulerStatus(),
    refetchInterval: 10000, // Check every 10 seconds
  })

  // Rebalance mutation
  const rebalanceMutation = useMutation({
    mutationFn: (force: boolean = false) => apiClient.rebalancePortfolio(userAddress, force),
    onSuccess: (data: any) => {
      toast.success(`Portfolio rebalanced! ${data.trades_executed} trades executed.`)
      queryClient.invalidateQueries({ queryKey: ['portfolio', userAddress] })
      setShowRebalanceDialog(false)
    },
    onError: (error: any) => {
      toast.error(`Rebalancing failed: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Auto-trading toggle mutation
  const toggleAutoTradingMutation = useMutation({
    mutationFn: (enabled: boolean) => apiClient.toggleAutoTrading(userAddress, enabled),
    onSuccess: (data: any) => {
      setAutoTradingEnabled(data.auto_trading_enabled)
      toast.success(`Auto-trading ${data.auto_trading_enabled ? 'enabled' : 'disabled'}`)
    },
    onError: (error: any) => {
      toast.error(`Failed to toggle auto-trading: ${error.response?.data?.detail || error.message}`)
    }
  })

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value)
  }

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  const getRecommendationColor = (recommendation: string) => {
    switch (recommendation) {
      case 'increase': return 'success'
      case 'decrease': return 'error'
      default: return 'default'
    }
  }

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
        <Typography variant="h6" sx={{ ml: 2 }}>Loading portfolio...</Typography>
      </Box>
    )
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        Failed to load portfolio: {(error as any)?.message || 'Unknown error'}
      </Alert>
    )
  }

  return (
    <Box>
      {/* Portfolio Overview */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="between" alignItems="center" mb={2}>
                <Typography variant="h5" component="h2">
                  Portfolio Overview
                </Typography>
                <Box>
                  <Tooltip title="Refresh Portfolio">
                    <IconButton onClick={() => refetch()}>
                      <Refresh />
                    </IconButton>
                  </Tooltip>
                  <Button
                    variant="outlined"
                    startIcon={<Analytics />}
                    onClick={() => setShowTradeHistory(true)}
                    sx={{ ml: 1 }}
                  >
                    History
                  </Button>
                  <Button
                    variant="contained"
                    startIcon={<TrendingUp />}
                    onClick={() => setShowRebalanceDialog(true)}
                    disabled={rebalanceMutation.isPending}
                    sx={{ ml: 1 }}
                  >
                    Rebalance
                  </Button>
                </Box>
              </Box>

              <Grid container spacing={2}>
                <Grid item xs={6} md={3}>
                  <Typography variant="body2" color="text.secondary">
                    Total Value
                  </Typography>
                  <Typography variant="h4">
                    {formatCurrency(portfolio?.total_value_usd || 0)}
                  </Typography>
                </Grid>
                <Grid item xs={6} md={3}>
                  <Typography variant="body2" color="text.secondary">
                    24h Return
                  </Typography>
                  <Typography 
                    variant="h6" 
                    color={portfolio?.performance?.daily_return >= 0 ? 'success.main' : 'error.main'}
                  >
                    {formatPercent(portfolio?.performance?.daily_return || 0)}
                  </Typography>
                </Grid>
                <Grid item xs={6} md={3}>
                  <Typography variant="body2" color="text.secondary">
                    Total Return
                  </Typography>
                  <Typography 
                    variant="h6"
                    color={portfolio?.performance?.total_return >= 0 ? 'success.main' : 'error.main'}
                  >
                    {formatPercent(portfolio?.performance?.total_return || 0)}
                  </Typography>
                </Grid>
                <Grid item xs={6} md={3}>
                  <Typography variant="body2" color="text.secondary">
                    Total Trades
                  </Typography>
                  <Typography variant="h6">
                    {portfolio?.performance?.trades_count || 0}
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Automated Trading
              </Typography>
              
              <FormControlLabel
                control={
                  <Switch
                    checked={autoTradingEnabled}
                    onChange={(e) => toggleAutoTradingMutation.mutate(e.target.checked)}
                    disabled={toggleAutoTradingMutation.isPending}
                  />
                }
                label="Enable Auto-Trading"
              />

              <Box mt={2}>
                <Typography variant="body2" color="text.secondary">
                  Scheduler Status
                </Typography>
                <Chip 
                  icon={schedulerStatus?.scheduler?.is_running ? <PlayArrow /> : <Stop />}
                  label={schedulerStatus?.scheduler?.is_running ? 'Running' : 'Stopped'}
                  color={schedulerStatus?.scheduler?.is_running ? 'success' : 'default'}
                  size="small"
                />
              </Box>

              {portfolio?.last_rebalance && (
                <Box mt={2}>
                  <Typography variant="body2" color="text.secondary">
                    Last Rebalance
                  </Typography>
                  <Typography variant="body2">
                    {new Date(portfolio.last_rebalance).toLocaleString()}
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Current Positions */}
      {portfolio?.positions && portfolio.positions.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Current Positions
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Token</TableCell>
                    <TableCell align="right">Balance</TableCell>
                    <TableCell align="right">Value (USD)</TableCell>
                    <TableCell align="right">Allocation</TableCell>
                    <TableCell align="right">24h Change</TableCell>
                    <TableCell align="center">Recommendation</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {portfolio.positions.map((position: PortfolioPosition) => {
                    const prediction = predictions?.predictions?.[position.token]
                    return (
                      <TableRow key={position.token}>
                        <TableCell>
                          <Typography variant="subtitle2">
                            {position.token}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          {position.balance.toFixed(4)}
                        </TableCell>
                        <TableCell align="right">
                          {formatCurrency(position.value_usd)}
                        </TableCell>
                        <TableCell align="right">
                          {position.allocation_percent.toFixed(1)}%
                        </TableCell>
                        <TableCell 
                          align="right"
                          sx={{ 
                            color: (position.price_change_24h || 0) >= 0 ? 'success.main' : 'error.main' 
                          }}
                        >
                          {position.price_change_24h ? formatPercent(position.price_change_24h) : '-'}
                        </TableCell>
                        <TableCell align="center">
                          {prediction && (
                            <Chip
                              label={prediction.recommendation}
                              color={getRecommendationColor(prediction.recommendation)}
                              size="small"
                            />
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {(!portfolio || portfolio.status === 'no_portfolio') && (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No Portfolio Found
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Make a deposit to start building your automated trading portfolio
            </Typography>
            <Button variant="contained" onClick={() => window.location.reload()}>
              Refresh
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Rebalance Confirmation Dialog */}
      <Dialog open={showRebalanceDialog} onClose={() => setShowRebalanceDialog(false)}>
        <DialogTitle>Confirm Portfolio Rebalance</DialogTitle>
        <DialogContent>
          <Typography gutterBottom>
            This will rebalance your portfolio based on current AI predictions and market conditions.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Current portfolio value: {formatCurrency(portfolio?.total_value_usd || 0)}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowRebalanceDialog(false)}>Cancel</Button>
          <Button 
            onClick={() => rebalanceMutation.mutate(false)}
            variant="contained"
            disabled={rebalanceMutation.isPending}
          >
            Rebalance
          </Button>
        </DialogActions>
      </Dialog>

      {/* Trade History Dialog */}
      <Dialog 
        open={showTradeHistory} 
        onClose={() => setShowTradeHistory(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Trade History</DialogTitle>
        <DialogContent>
          {tradeHistory?.trades && tradeHistory.trades.length > 0 ? (
            <List>
              {tradeHistory.trades.map((trade: TradeRecord, index: number) => (
                <React.Fragment key={index}>
                  <ListItem>
                    <ListItemText
                      primary={
                        <Box display="flex" justifyContent="space-between">
                          <Typography>
                            {trade.action.toUpperCase()} {trade.token}
                          </Typography>
                          <Typography color="text.secondary">
                            {formatCurrency(trade.usd_value)}
                          </Typography>
                        </Box>
                      }
                      secondary={
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            Amount: {trade.amount} • {new Date(trade.timestamp).toLocaleString()}
                          </Typography>
                          {trade.tx_hash && (
                            <Typography variant="caption" color="text.secondary">
                              TX: {trade.tx_hash}
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                    <Chip 
                      label={trade.status} 
                      size="small"
                      color={trade.status === 'executed' ? 'success' : 'default'}
                    />
                  </ListItem>
                  {index < tradeHistory.trades.length - 1 && <Divider />}
                </React.Fragment>
              ))}
            </List>
          ) : (
            <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
              No trades found
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowTradeHistory(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default PortfolioTab
