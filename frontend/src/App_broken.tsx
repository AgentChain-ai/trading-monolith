import React, { useState, useEffect } from 'react'
import {
  Box,
  Container,
  Typography,
  AppBar,
  Toolbar,
  TextField,
  Button,
  Grid,
  Card,
  CardContent,
  CircularProgress,
  LinearProgress,
  Alert,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import Dashboard from './components/Dashboard'
import WalletButton from './components/WalletButton'
import ChainSwitcher from './components/ChainSwitcher'
import { apiClient } from './services/api'
import { TradingThesis, DashboardData } from './types'

type AnalysisState = 'idle' | 'ingesting' | 'processing' | 'completed' | 'error'

function App() {
  const [selectedToken, setSelectedToken] = useState('USDC')
  const [tokenInput, setTokenInput] = useState('')
  const [analysisState, setAnalysisState] = useState<AnalysisState>('idle')
  const [progressMessage, setProgressMessage] = useState('')
  const queryClient = useQueryClient()

    // Query for dashboard data with smarter refetching
  const { data: dashboardData, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard', selectedToken],
    queryFn: () => apiClient.getDashboardData(selectedToken),
    enabled: !!selectedToken,
    refetchInterval: analysisState === 'processing' ? 5000 : 30000, // Fast polling during processing
  })

  // Auto-ingestion mutation with progress tracking
  const autoIngestMutation = useMutation({
    mutationFn: (token: string) => apiClient.ingestToken(token),
    onMutate: () => {
      setAnalysisState('ingesting')
      setProgressMessage('Searching for news articles...')
    },
    onSuccess: () => {
  // Auto-ingestion mutation with progress tracking
  const autoIngestMutation = useMutation({
    mutationFn: (token: string) => apiClient.ingestToken(token),
    onMutate: () => {
      setAnalysisState('ingesting')
      setProgressMessage('Searching for news articles...')
    },
    onSuccess: () => {
      setAnalysisState('processing')
      setProgressMessage('Processing articles and generating insights...')
      toast.success('Data ingestion started! Processing in background...')
    },
    onError: (error: any) => {
      setAnalysisState('error')
      setProgressMessage('Failed to ingest data. Please try again.')
      toast.error(`Analysis failed: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Auto-trigger analysis when token changes
  useEffect(() => {
    if (selectedToken && selectedToken !== 'USDC') { // Don't auto-trigger for default
      // Check if we have recent data first
      if (!dashboardData || (dashboardData as any)?.buckets?.length === 0) {
        autoIngestMutation.mutate(selectedToken)
      } else {
        setAnalysisState('completed')
        setProgressMessage('Using existing analysis data')
      }
    }
  }, [selectedToken, dashboardData])

  // Poll ingestion status during processing
  useEffect(() => {
    let statusInterval: NodeJS.Timeout | null = null

    if (analysisState === 'ingesting' || analysisState === 'processing') {
      statusInterval = setInterval(async () => {
        try {
          const status = await apiClient.getIngestionStatus(selectedToken)
          
          if (status.status === 'completed') {
            setAnalysisState('completed')
            setProgressMessage(status.message)
            refetch() // Refresh dashboard data
          } else if (status.status === 'error') {
            setAnalysisState('error')
            setProgressMessage(status.message)
          } else {
            setProgressMessage(status.message)
            // Keep current state but update message
          }
        } catch (error) {
          console.error('Failed to get status:', error)
        }
      }, 2000) // Poll every 2 seconds during processing
    }

    return () => {
      if (statusInterval) {
        clearInterval(statusInterval)
      }
    }
  }, [analysisState, selectedToken, refetch])

  // Manual refresh for existing data
  const ingestMutation = useMutation({
    mutationFn: (token: string) => apiClient.ingestToken(token),
    onMutate: () => {
      setAnalysisState('ingesting')
      setProgressMessage('Refreshing data...')
    },
    onSuccess: () => {
      setAnalysisState('processing')
      setProgressMessage('Processing updated data...')
      toast.success('Data refresh started!')
    },
    onError: (error: any) => {
      setAnalysisState('error')
      setProgressMessage(error.response?.data?.detail || 'Refresh failed')
      toast.error('Refresh failed!')
    }
  })

  // Auto-trigger analysis when token changes
  useEffect(() => {
    if (selectedToken && selectedToken !== 'USDC') { // Don't auto-trigger for default
      // Check if we have recent data first
      if (!dashboardData || (dashboardData.buckets && dashboardData.buckets.length === 0)) {
        autoIngestMutation.mutate(selectedToken)
      } else {
        setAnalysisState('completed')
        setProgressMessage('Using existing analysis data')
      }
    }
  }, [selectedToken])

  // Poll ingestion status during processing
  useEffect(() => {
    let statusInterval: NodeJS.Timeout | null = null

    if (analysisState === 'ingesting' || analysisState === 'processing') {
      statusInterval = setInterval(async () => {
        try {
          const status = await apiClient.getIngestionStatus(selectedToken)
          
          if (status.status === 'completed') {
            setAnalysisState('completed')
            setProgressMessage(status.message)
            refetch() // Refresh dashboard data
          } else if (status.status === 'error') {
            setAnalysisState('error')
            setProgressMessage(status.message)
          } else {
            setProgressMessage(status.message)
            // Keep current state but update message
          }
        } catch (error) {
          console.error('Failed to get status:', error)
        }
      }, 2000) // Poll every 2 seconds during processing
    }

    return () => {
      if (statusInterval) {
        clearInterval(statusInterval)
      }
    }
  }, [analysisState, selectedToken])

  // Manual refresh for existing data
  const ingestMutation = useMutation(
    (token: string) => apiClient.ingestToken(token),
    {
      onMutate: () => {
        setAnalysisState('ingesting')
        setProgressMessage('Refreshing data...')
      },
      onSuccess: () => {
        setAnalysisState('processing')
        setProgressMessage('Processing updated data...')
        toast.success('Data refresh started!')
      },
      onError: (error: any) => {
        setAnalysisState('error')
        setProgressMessage('Failed to refresh data.')
        toast.error(`Refresh failed: ${error.response?.data?.detail || error.message}`)
      }
    }
  )

  const handleTokenSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (tokenInput.trim()) {
      const newToken = tokenInput.trim().toUpperCase()
      setSelectedToken(newToken)
      setTokenInput('')
      setAnalysisState('idle')
      // Auto-ingestion will trigger via useEffect
    }
  }

  const handleManualIngest = () => {
    if (selectedToken) {
      ingestMutation.mutate(selectedToken)
    }
  }

  const handleRefresh = () => {
    refetch()
    toast.success('Dashboard refreshed!')
  }

  const getProgressValue = () => {
    switch (analysisState) {
      case 'ingesting': return 25
      case 'processing': return 75
      case 'completed': return 100
      default: return 0
    }
  }

  return (
    <Box sx={{ flexGrow: 1, minHeight: '100vh' }}>
      <AppBar position="static" elevation={0} sx={{ backgroundColor: '#1e2139' }}>
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 600 }}>
            AgentChain.Trade
          </Typography>
          
          {/* Wallet Controls */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mr: 2 }}>
            <ChainSwitcher />
            <WalletButton variant="outlined" />
          </Box>
          
          {/* Token Input */}
          <Box component="form" onSubmit={handleTokenSubmit} sx={{ display: 'flex', gap: 1 }}>
            <TextField
              size="small"
              variant="outlined"
              placeholder="Enter token (e.g., BTC)"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              sx={{
                '& .MuiOutlinedInput-root': {
                  backgroundColor: 'rgba(255, 255, 255, 0.1)',
                },
              }}
            />
            <Button type="submit" variant="contained" disabled={!tokenInput.trim()}>
              {analysisState === 'ingesting' || analysisState === 'processing' ? 'Analyzing...' : 'Analyze Token'}
            </Button>
          </Box>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ py: 3 }}>
        {/* Progress Indicator */}
        {(analysisState === 'ingesting' || analysisState === 'processing') && (
          <Card sx={{ mb: 3, bgcolor: '#f5f5f5' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <CircularProgress size={20} sx={{ mr: 2 }} />
                <Typography variant="body1">
                  {progressMessage}
                </Typography>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={getProgressValue()} 
                sx={{ borderRadius: 1 }}
              />
            </CardContent>
          </Card>
        )}

        {/* Success Message */}
        {analysisState === 'completed' && (
          <Alert severity="success" sx={{ mb: 3 }} onClose={() => setAnalysisState('idle')}>
            Analysis completed! {selectedToken} insights are ready.
          </Alert>
        )}

        {/* Error Message */}
        {analysisState === 'error' && (
          <Alert severity="error" sx={{ mb: 3 }} onClose={() => setAnalysisState('idle')}>
            {progressMessage}
          </Alert>
        )}

        {/* Current Token Header */}
        <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box>
            <Typography variant="h4" gutterBottom>
              {selectedToken} Analysis
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {analysisState === 'idle' ? 'Real-time narrative analysis and trading signals' : progressMessage}
            </Typography>
          </Box>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button 
              onClick={handleManualIngest} 
              disabled={ingestMutation.isLoading || analysisState === 'ingesting' || analysisState === 'processing'}
              variant="outlined"
            >
              {ingestMutation.isLoading || analysisState === 'ingesting' ? (
                <>
                  <CircularProgress size={16} sx={{ mr: 1 }} />
                  Refreshing...
                </>
              ) : (
                'Refresh Data'
              )}
            </Button>
            <Button onClick={handleRefresh} disabled={isLoading} variant="contained">
              Reload
            </Button>
          </Box>
        </Box>

        {/* Error State */}
        {error && (
          <Card sx={{ mb: 3, borderLeft: '4px solid #f44336' }}>
            <CardContent>
              <Typography variant="h6" color="error" gutterBottom>
                Error Loading Data
              </Typography>
              <Typography variant="body2">
                {error instanceof Error ? error.message : 'Failed to load dashboard data'}
              </Typography>
              <Button 
                onClick={handleManualIngest} 
                variant="outlined" 
                sx={{ mt: 2 }}
                disabled={ingestMutation.isLoading || analysisState === 'ingesting'}
              >
                Try Refreshing Data
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Loading State */}
        {isLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress size={48} />
          </Box>
        )}

        {/* Dashboard */}
        {dashboardData && (
          <Dashboard 
            token={selectedToken} 
            data={dashboardData} 
            onRefresh={refetch}
          />
        )}

        {/* No Data State */}
        {!isLoading && !error && !dashboardData && (
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 8 }}>
              <Typography variant="h6" gutterBottom>
                No Data Available
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Start by ingesting data for {selectedToken} or try a different token
              </Typography>
              <Button 
                onClick={handleManualIngest} 
                variant="contained" 
                disabled={ingestMutation.isLoading || analysisState === 'ingesting'}
              >
                {ingestMutation.isLoading || analysisState === 'ingesting' ? 'Starting...' : 'Analyze Token Data'}
              </Button>
            </CardContent>
          </Card>
        )}
      </Container>
    </Box>
  )
}

export default App