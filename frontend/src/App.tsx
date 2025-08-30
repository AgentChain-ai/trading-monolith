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
  Tabs,
  Tab,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import Dashboard from './components/Dashboard'
import DepositDashboard from './components/DepositDashboard'
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
  const [activeTab, setActiveTab] = useState(0) // 0 = Trading, 1 = Deposits
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
        <Toolbar sx={{ flexDirection: { xs: 'column', md: 'row' }, gap: 2, py: { xs: 2, md: 1 } }}>
          <Typography variant="h6" component="div" sx={{ 
            flexGrow: 1, 
            fontWeight: 600,
            fontSize: { xs: '1.1rem', sm: '1.25rem' },
            textAlign: { xs: 'center', md: 'left' }
          }}>
            🤖 AgentChain.Trade
          </Typography>
          
          {/* Wallet Controls */}
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 2, 
            mr: { xs: 0, md: 2 },
            flexDirection: { xs: 'column', sm: 'row' },
            width: { xs: '100%', sm: 'auto' }
          }}>
            <ChainSwitcher />
            <WalletButton variant="outlined" />
          </Box>
          
          {/* Token Input */}
          <Box component="form" onSubmit={handleTokenSubmit} sx={{ 
            display: 'flex', 
            gap: { xs: 1, sm: 2 }, 
            alignItems: 'center',
            flexDirection: { xs: 'column', sm: 'row' },
            width: { xs: '100%', sm: 'auto' }
          }}>
            <TextField
              size="small"
              placeholder="Enter token symbol (e.g., BTC, ETH, SOL)"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value.toUpperCase())}
              sx={{
                minWidth: { xs: '100%', sm: 280 },
                '& .MuiOutlinedInput-root': {
                  backgroundColor: 'rgba(255, 255, 255, 0.1)',
                  color: 'white',
                  '& fieldset': {
                    borderColor: 'rgba(255, 255, 255, 0.3)',
                  },
                  '&:hover fieldset': {
                    borderColor: 'rgba(255, 255, 255, 0.5)',
                  },
                  '&.Mui-focused fieldset': {
                    borderColor: '#64b5f6',
                  },
                },
                '& .MuiInputBase-input::placeholder': {
                  color: 'rgba(255, 255, 255, 0.7)',
                },
              }}
            />
            <Button 
              type="submit" 
              variant="contained" 
              disabled={!tokenInput.trim() || (analysisState === 'ingesting' || analysisState === 'processing')}
              sx={{
                bgcolor: '#64b5f6',
                '&:hover': {
                  bgcolor: '#42a5f5',
                },
                '&:disabled': {
                  bgcolor: 'rgba(255, 255, 255, 0.12)',
                },
                px: 3,
                py: 1,
                fontWeight: 600,
              }}
            >
              {analysisState === 'ingesting' || analysisState === 'processing' ? (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CircularProgress size={16} sx={{ color: 'white' }} />
                  Analyzing...
                </Box>
              ) : (
                'Analyze Token'
              )}
            </Button>
          </Box>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ py: { xs: 2, sm: 3 }, px: { xs: 1, sm: 3 } }}>
        {/* Progress Indicator */}
        {(analysisState === 'ingesting' || analysisState === 'processing') && (
          <Card sx={{ 
            mb: 3, 
            bgcolor: '#e3f2fd', 
            border: '1px solid #2196f3',
            boxShadow: '0 2px 8px rgba(33, 150, 243, 0.2)'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <CircularProgress size={20} sx={{ mr: 2, color: '#1976d2' }} />
                <Typography variant="body1" sx={{ color: '#1565c0', fontWeight: 500 }}>
                  {progressMessage}
                </Typography>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={getProgressValue()} 
                sx={{ 
                  borderRadius: 1,
                  height: 8,
                  backgroundColor: '#bbdefb',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: '#1976d2'
                  }
                }}
              />
            </CardContent>
          </Card>
        )}

        {/* Success Message */}
        {analysisState === 'completed' && (
          <Alert 
            severity="success" 
            sx={{ 
              mb: 3,
              border: '1px solid #4caf50',
              backgroundColor: '#f1f8e9',
              '& .MuiAlert-icon': {
                color: '#2e7d32'
              }
            }}
            action={
              <Button 
                color="inherit" 
                size="small" 
                onClick={() => setAnalysisState('idle')}
                sx={{ color: '#2e7d32' }}
              >
                Dismiss
              </Button>
            }
          >
            <Box>
              <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5, color: '#2e7d32' }}>
                Analysis Completed Successfully! 🎉
              </Typography>
              <Typography variant="body2" sx={{ color: '#388e3c' }}>
                {selectedToken} insights are ready. Check the dashboard below for detailed analysis.
              </Typography>
            </Box>
          </Alert>
        )}

        {/* Error Message */}
        {analysisState === 'error' && (
          <Alert 
            severity="error" 
            sx={{ 
              mb: 3,
              '& .MuiAlert-message': {
                width: '100%'
              }
            }}
            action={
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button 
                  color="inherit" 
                  size="small" 
                  onClick={() => selectedToken && ingestMutation.mutate(selectedToken)}
                  disabled={ingestMutation.isPending}
                >
                  Retry
                </Button>
                <Button 
                  color="inherit" 
                  size="small" 
                  onClick={() => setAnalysisState('idle')}
                >
                  Dismiss
                </Button>
              </Box>
            }
          >
            <Box>
              <Typography variant="body1" sx={{ fontWeight: 600, mb: 1 }}>
                Analysis Failed
              </Typography>
              <Typography variant="body2">
                {progressMessage}
              </Typography>
            </Box>
          </Alert>
        )}

        {/* Tab Navigation */}
        <Box sx={{ mb: 3 }}>
          <Tabs 
            value={activeTab} 
            onChange={(e, newValue) => setActiveTab(newValue)}
            aria-label="dashboard tabs"
            sx={{
              '& .MuiTab-root': {
                textTransform: 'none',
                fontWeight: 500,
                fontSize: '1rem',
                py: 2,
                px: 3,
                '&.Mui-selected': {
                  color: '#1976d2',
                  fontWeight: 600,
                },
              },
              '& .MuiTabs-indicator': {
                backgroundColor: '#1976d2',
                height: 3,
                borderRadius: '3px 3px 0 0',
              },
            }}
          >
            <Tab label="🏠 Trading Dashboard" />
            <Tab label="💰 Deposit System" />
          </Tabs>
        </Box>

        {/* Tab Content */}
        {activeTab === 0 ? (
          <>
            {/* Current Token Header */}
            <Box sx={{ 
              mb: 3, 
              display: 'flex', 
              alignItems: { xs: 'flex-start', sm: 'center' }, 
              justifyContent: 'space-between',
              flexDirection: { xs: 'column', sm: 'row' },
              gap: { xs: 2, sm: 0 }
            }}>
              <Box>
                <Typography variant="h4" gutterBottom sx={{ 
                  fontWeight: 600, 
                  background: 'linear-gradient(45deg, #1976d2, #42a5f5)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  fontSize: { xs: '1.75rem', sm: '2rem', md: '2.125rem' }
                }}>
                  {selectedToken} Analysis
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                  {analysisState === 'idle' ? 'AI-powered market insights and trading recommendations' : progressMessage}
                </Typography>
              </Box>
          
          <Box sx={{ 
            display: 'flex', 
            gap: 1.5,
            flexDirection: { xs: 'column', sm: 'row' },
            width: { xs: '100%', sm: 'auto' }
          }}>
            <Button 
              onClick={handleManualIngest} 
              disabled={ingestMutation.isPending || analysisState === 'ingesting' || analysisState === 'processing'}
              variant="outlined"
              size="small"
              sx={{
                borderColor: '#1976d2',
                color: '#1976d2',
                '&:hover': {
                  borderColor: '#1565c0',
                  backgroundColor: 'rgba(25, 118, 210, 0.04)',
                },
                fontWeight: 500,
                px: 2,
              }}
            >
              {ingestMutation.isPending || analysisState === 'ingesting' ? (
                <>
                  <CircularProgress size={14} sx={{ mr: 1, color: '#1976d2' }} />
                  Refreshing...
                </>
              ) : (
                <>🔄 Refresh Data</>
              )}
            </Button>
            <Button 
              onClick={handleRefresh} 
              disabled={isLoading} 
              variant="contained"
              size="small"
              sx={{
                bgcolor: '#1976d2',
                '&:hover': {
                  bgcolor: '#1565c0',
                },
                fontWeight: 500,
                px: 2,
              }}
            >
              📊 Reload
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
                disabled={ingestMutation.isPending || analysisState === 'ingesting'}
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
            data={dashboardData as DashboardData} 
            onRefresh={refetch}
          />
        )}

        {/* No Data State */}
        {!isLoading && !error && !dashboardData && (
          <Card sx={{ 
            background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
            border: '1px solid rgba(25, 118, 210, 0.12)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1)',
          }}>
            <CardContent sx={{ textAlign: 'center', py: 8 }}>
              <Box sx={{ mb: 3 }}>
                <Typography variant="h3" sx={{ fontSize: '3rem', mb: 1 }}>
                  🚀
                </Typography>
                <Typography variant="h5" gutterBottom sx={{ fontWeight: 600, color: '#1976d2' }}>
                  Welcome to AgentChain.Trade
                </Typography>
                <Typography variant="body1" color="text.secondary" sx={{ mb: 4, maxWidth: 600, mx: 'auto' }}>
                  Start your AI-powered trading journey by analyzing any cryptocurrency. 
                  Our advanced algorithms provide real-time market insights and trading recommendations.
                </Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                {selectedToken ? 
                  `Ready to analyze ${selectedToken}? Click "Refresh Data" above to begin.` :
                  'Enter a token symbol above to get started with professional trading insights.'
                }
              </Typography>
              <Button 
                onClick={handleManualIngest} 
                variant="contained" 
                disabled={ingestMutation.isPending || analysisState === 'ingesting'}
                sx={{
                  bgcolor: '#1976d2',
                  '&:hover': {
                    bgcolor: '#1565c0',
                  },
                  fontWeight: 600,
                  px: 3,
                  py: 1.5,
                }}
              >
                {ingestMutation.isPending || analysisState === 'ingesting' ? (
                  <>
                    <CircularProgress size={16} sx={{ mr: 1, color: 'white' }} />
                    Starting Analysis...
                  </>
                ) : (
                  '🔍 Start Analysis'
                )}
              </Button>
            </CardContent>
          </Card>
        )}
          </>
        ) : (
          /* Deposit Dashboard Tab */
          <DepositDashboard />
        )}
      </Container>
    </Box>
  )
}

export default App
