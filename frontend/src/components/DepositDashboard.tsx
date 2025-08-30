import React, { useState, useEffect } from 'react'
import { useAccount, useChainId, useSendTransaction, useBalance } from 'wagmi'
import { parseEther, formatEther } from 'viem'
import QRCode from 'qrcode'
import { 
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  Button,
  TextField,
  Grid,
  Paper,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Chip,
  Avatar,
  LinearProgress,
  CircularProgress,
  Alert,
  IconButton,
  Dialog,
  DialogContent,
  DialogTitle,
  Fade,
  Grow,
  Slide,
} from '@mui/material'
import { 
  AccountBalanceWallet,
  ContentCopy,
  CheckCircle,
  Warning,
  QrCode2,
  Send,
  TrendingUp,
  Security,
  Speed,
} from '@mui/icons-material'
import { apiClient } from '../services/api'
import { Chain, ManagedWallet, DepositAddress, UserBalance, DepositHealth } from '../types'

type DepositStep = 'select-amount' | 'confirm-details' | 'send-transaction' | 'monitoring' | 'success'

const DepositDashboard: React.FC = () => {
  const { address, isConnected } = useAccount()
  const chainId = useChainId()
  
  const [health, setHealth] = useState<DepositHealth | null>(null)
  const [chains, setChains] = useState<Chain[]>([])
  const [managedWallets, setManagedWallets] = useState<ManagedWallet[]>([])
  const [depositAddress, setDepositAddress] = useState<DepositAddress | null>(null)
  const [userBalances, setUserBalances] = useState<UserBalance[]>([])
  const [selectedChain, setSelectedChain] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Deposit flow state
  const [currentStep, setCurrentStep] = useState<DepositStep>('select-amount')
  const [depositAmount, setDepositAmount] = useState('')
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null)
  const [showQR, setShowQR] = useState(false)

  // Get user's native token balance
  const { data: userBalance } = useBalance({
    address: address,
    chainId: selectedChain || undefined,
  })

  // Transaction sending
  const { sendTransaction, isPending: isTxPending, isSuccess: isTxSuccess, error: txError } = useSendTransaction()

  // Load initial data
  useEffect(() => {
    loadDepositData()
  }, [])

  // Load user-specific data when wallet connects
  useEffect(() => {
    if (isConnected && address) {
      loadUserData()
    }
  }, [isConnected, address])

  // Set default chain when chains load, prioritizing user's current chain
  useEffect(() => {
    if (chains.length > 0 && !selectedChain) {
      // Check if user's current chain is supported
      const userChainSupported = chains.find(chain => chain.chain_id === chainId)
      if (userChainSupported) {
        setSelectedChain(chainId)
        showNotification(`Connected to ${userChainSupported.name} network`, 'info')
      } else {
        setSelectedChain(chains[0].chain_id)
        showNotification(`Using ${chains[0].name} network`, 'info')
      }
    }
  }, [chains, selectedChain, chainId])

  // Generate QR code when deposit address is available
  useEffect(() => {
    if (depositAddress && depositAmount) {
      generateQRCode()
    }
  }, [depositAddress, depositAmount])

  const loadDepositData = async () => {
    try {
      setLoading(true)
      setError(null)

      // Load health status first
      const healthData = await apiClient.getDepositHealth()
      setHealth(healthData)

      // Load supported chains
      const chainsData = await apiClient.getSupportedChains()
      setChains(chainsData)
      if (chainsData.length > 0 && !selectedChain) {
        setSelectedChain(chainsData[0].chain_id)
      }

      // Load managed wallets with error handling
      try {
        const walletsData = await apiClient.getManagedWallets()
        setManagedWallets(walletsData)
      } catch (walletErr: any) {
        console.warn('Failed to load managed wallets:', walletErr)
        // Don't fail the entire load if wallets fail
        setManagedWallets([])
      }

    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load deposit data')
    } finally {
      setLoading(false)
    }
  }

  const loadUserData = async () => {
    if (!address) return

    try {
      const balancesData = await apiClient.getUserBalances(address)
      setUserBalances(balancesData)
    } catch (err: any) {
      console.error('Failed to load user data:', err)
    }
  }

  const generateDepositAddress = async () => {
    if (!address || !selectedChain) {
      setError('Please connect wallet and select a chain')
      return
    }

    try {
      setLoading(true)
      setError(null)
      
      const addressData = await apiClient.generateDepositAddress(address, selectedChain)
      
      setDepositAddress(addressData)
      setCurrentStep('confirm-details')
      showNotification('Deposit address generated successfully! 🎉', 'success')
    } catch (err: any) {
      console.error('Failed to generate deposit address:', err)
      setError(err.response?.data?.detail || err.message || 'Failed to generate deposit address')
      showNotification('Failed to generate deposit address', 'error')
    } finally {
      setLoading(false)
    }
  }

  const generateQRCode = async () => {
    if (!depositAddress || !depositAmount) return

    try {
      // Create a simple payment URI (this could be enhanced for specific wallets)
      const paymentUri = `ethereum:${depositAddress.smart_account}?value=${parseEther(depositAmount)}`
      const qrUrl = await QRCode.toDataURL(paymentUri)
      setQrCodeUrl(qrUrl)
    } catch (err) {
      console.error('Failed to generate QR code:', err)
    }
  }

  const handleSendTransaction = () => {
    if (!depositAddress || !depositAmount) return

    sendTransaction({
      to: depositAddress.smart_account as `0x${string}`,
      value: parseEther(depositAmount),
      chainId: selectedChain as any,
    })

    setCurrentStep('monitoring')
  }

  const openInWallet = () => {
    if (!depositAddress || !depositAmount) return

    // MetaMask deep link
    const metamaskUrl = `https://metamask.app.link/send/${depositAddress.smart_account}?value=${parseEther(depositAmount)}`
    window.open(metamaskUrl, '_blank')
  }

  const [notificationOpen, setNotificationOpen] = useState(false)
  const [notificationMessage, setNotificationMessage] = useState('')
  const [notificationSeverity, setNotificationSeverity] = useState<'success' | 'error' | 'info'>('success')

  const showNotification = (message: string, severity: 'success' | 'error' | 'info' = 'success') => {
    setNotificationMessage(message)
    setNotificationSeverity(severity)
    setNotificationOpen(true)
    setTimeout(() => setNotificationOpen(false), 4000)
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    showNotification('Copied to clipboard! 📋', 'success')
  }

  const resetFlow = () => {
    setCurrentStep('select-amount')
    setDepositAmount('')
    setDepositAddress(null)
    setQrCodeUrl(null)
    setShowQR(false)
    setError(null)
  }

  const getCurrentChain = () => {
    return chains.find(chain => chain.chain_id === selectedChain)
  }

  if (loading && !health) {
    return (
      <Box 
        sx={{ 
          minHeight: '100vh',
          background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        <Card sx={{ p: 4, textAlign: 'center', backgroundColor: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)' }}>
          <CircularProgress size={60} sx={{ color: '#00d4ff', mb: 3 }} />
          <Typography variant="h5" sx={{ color: 'white', mb: 1 }}>
            Loading Deposit System
          </Typography>
          <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
            Connecting to AgentChain.Trade...
          </Typography>
        </Card>
      </Box>
    )
  }

  return (
    <Box 
      sx={{ 
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
        py: 4,
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      {/* Background Pattern */}
      <Box 
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          opacity: 0.1,
          backgroundImage: 'radial-gradient(circle at 25% 25%, #00d4ff 0%, transparent 50%), radial-gradient(circle at 75% 75%, #7c3aed 0%, transparent 50%)',
        }}
      />
      
      <Container maxWidth="lg" sx={{ position: 'relative', zIndex: 1 }}>
        {/* Modern Header */}
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Fade in timeout={1000}>
            <Avatar 
              sx={{ 
                width: 80, 
                height: 80, 
                mx: 'auto', 
                mb: 3,
                background: 'linear-gradient(45deg, #00d4ff, #7c3aed)',
                boxShadow: '0 8px 32px rgba(0, 212, 255, 0.3)'
              }}
            >
              <AccountBalanceWallet sx={{ fontSize: 40, color: 'white' }} />
            </Avatar>
          </Fade>
          <Slide direction="up" in timeout={1200}>
            <Typography 
              variant="h2" 
              sx={{ 
                fontWeight: 'bold',
                background: 'linear-gradient(45deg, #ffffff, #b0b3b8)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                mb: 2
              }}
            >
              Deposit Funds
            </Typography>
          </Slide>
          <Slide direction="up" in timeout={1400}>
            <Typography 
              variant="h6" 
              sx={{ 
                color: '#b0b3b8',
                maxWidth: '600px',
                mx: 'auto',
                lineHeight: 1.6
              }}
            >
              Seamlessly transfer funds from your wallet to AgentChain.Trade for automated trading
            </Typography>
          </Slide>
        </Box>

        {/* System Status Card */}
        {health && (
          <Grow in timeout={1600}>
            <Card 
              sx={{ 
                mb: 4,
                background: 'rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(20px)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: 4,
                overflow: 'hidden',
                transition: 'transform 0.3s ease',
                '&:hover': {
                  transform: 'translateY(-4px)',
                  boxShadow: '0 20px 40px rgba(0, 212, 255, 0.2)'
                }
              }}
            >
              <CardContent sx={{ p: 4 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                  <Typography variant="h5" sx={{ color: 'white', fontWeight: 'bold' }}>
                    System Status
                  </Typography>
                  <Chip
                    icon={<Security />}
                    label={health.microservice_connected ? 'Online' : 'Offline'}
                    color={health.microservice_connected ? 'success' : 'error'}
                    variant="filled"
                    sx={{ 
                      fontSize: '16px',
                      height: 40,
                      '& .MuiChip-icon': { fontSize: 20 }
                    }}
                  />
                </Box>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={4}>
                    <Paper 
                      sx={{ 
                        p: 3, 
                        textAlign: 'center',
                        background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 212, 255, 0.1))',
                        border: '1px solid rgba(0, 212, 255, 0.3)',
                        borderRadius: 3
                      }}
                    >
                      <Typography variant="h3" sx={{ color: '#00d4ff', fontWeight: 'bold', mb: 1 }}>
                        {health.active_chains}
                      </Typography>
                      <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                        Active Chains
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <Paper 
                      sx={{ 
                        p: 3, 
                        textAlign: 'center',
                        background: 'linear-gradient(135deg, rgba(76, 175, 80, 0.2), rgba(76, 175, 80, 0.1))',
                        border: '1px solid rgba(76, 175, 80, 0.3)',
                        borderRadius: 3
                      }}
                    >
                      <Typography variant="h3" sx={{ color: '#4caf50', fontWeight: 'bold', mb: 1 }}>
                        {managedWallets.length}
                      </Typography>
                      <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                        Managed Wallets
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <Paper 
                      sx={{ 
                        p: 3, 
                        textAlign: 'center',
                        background: 'linear-gradient(135deg, rgba(124, 58, 237, 0.2), rgba(124, 58, 237, 0.1))',
                        border: '1px solid rgba(124, 58, 237, 0.3)',
                        borderRadius: 3
                      }}
                    >
                      <Typography variant="h3" sx={{ color: '#7c3aed', fontWeight: 'bold', mb: 1 }}>
                        {userBalances.length}
                      </Typography>
                      <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                        Your Deposits
                      </Typography>
                    </Paper>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grow>
        )}

        {/* Wallet Connection */}
        {!isConnected ? (
          <Grow in timeout={1800}>
            <Card 
              sx={{ 
                mb: 4,
                background: 'rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(20px)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: 4,
                textAlign: 'center',
                transition: 'transform 0.3s ease',
                '&:hover': {
                  transform: 'translateY(-4px)',
                  boxShadow: '0 20px 40px rgba(0, 212, 255, 0.2)'
                }
              }}
            >
              <CardContent sx={{ p: 6 }}>
                <Avatar 
                  sx={{ 
                    width: 100, 
                    height: 100, 
                    mx: 'auto', 
                    mb: 3,
                    background: 'linear-gradient(45deg, #00d4ff, #7c3aed)',
                    animation: 'pulse 2s infinite'
                  }}
                >
                  <AccountBalanceWallet sx={{ fontSize: 50 }} />
                </Avatar>
                <Typography variant="h4" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                  Connect Your Wallet
                </Typography>
                <Typography variant="body1" sx={{ color: '#b0b3b8', mb: 4, maxWidth: 400, mx: 'auto' }}>
                  Connect your wallet to start depositing funds for automated trading
                </Typography>
                <Button
                  variant="contained"
                  size="large"
                  sx={{
                    background: 'linear-gradient(45deg, #00d4ff, #7c3aed)',
                    color: 'white',
                    px: 4,
                    py: 1.5,
                    fontSize: '18px',
                    borderRadius: 3,
                    textTransform: 'none',
                    fontWeight: 'bold',
                    boxShadow: '0 8px 32px rgba(0, 212, 255, 0.3)',
                    '&:hover': {
                      background: 'linear-gradient(45deg, #0099cc, #5a2d91)',
                      transform: 'translateY(-2px)',
                      boxShadow: '0 12px 40px rgba(0, 212, 255, 0.4)'
                    }
                  }}
                >
                  Connect Wallet
                </Button>
              </CardContent>
            </Card>
          </Grow>
        ) : (
          <>
            {/* Wallet Info */}
            <Grow in timeout={2000}>
              <Card 
                sx={{ 
                  mb: 4,
                  background: 'linear-gradient(135deg, rgba(76, 175, 80, 0.2), rgba(56, 142, 60, 0.1))',
                  backdropFilter: 'blur(20px)',
                  border: '1px solid rgba(76, 175, 80, 0.3)',
                  borderRadius: 4,
                  transition: 'transform 0.3s ease',
                  '&:hover': {
                    transform: 'translateY(-4px)'
                  }
                }}
              >
                <CardContent sx={{ p: 4 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Box>
                      <Typography variant="h5" sx={{ color: 'white', fontWeight: 'bold', mb: 1 }}>
                        Connected Wallet
                      </Typography>
                      <Chip
                        label={address}
                        sx={{ 
                          fontFamily: 'monospace',
                          backgroundColor: 'rgba(76, 175, 80, 0.2)',
                          color: '#4caf50',
                          border: '1px solid rgba(76, 175, 80, 0.3)',
                          fontSize: '14px'
                        }}
                      />
                      <Box sx={{ mt: 2, display: 'flex', gap: 3 }}>
                        <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                          <strong style={{ color: 'white' }}>Chain:</strong> {getCurrentChain()?.name || 'Unknown'}
                        </Typography>
                        <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                          <strong style={{ color: 'white' }}>Balance:</strong> {userBalance ? `${parseFloat(formatEther(userBalance.value)).toFixed(4)} ${userBalance.symbol}` : '0'}
                        </Typography>
                      </Box>
                    </Box>
                    <Avatar 
                      sx={{ 
                        width: 60, 
                        height: 60,
                        background: 'linear-gradient(45deg, #4caf50, #2e7d32)'
                      }}
                    >
                      <CheckCircle sx={{ fontSize: 30 }} />
                    </Avatar>
                  </Box>
                </CardContent>
              </Card>
            </Grow>

            {/* Deposit Flow */}
            <Grow in timeout={2200}>
              <Card 
                sx={{ 
                  background: 'rgba(255, 255, 255, 0.1)',
                  backdropFilter: 'blur(20px)',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  borderRadius: 4,
                  overflow: 'hidden'
                }}
              >
                {/* Progress Steps */}
                <Box 
                  sx={{ 
                    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                    p: 4,
                    background: 'rgba(0, 0, 0, 0.2)'
                  }}
                >
                  <Stepper 
                    activeStep={['select-amount', 'confirm-details', 'send-transaction', 'success'].indexOf(currentStep)}
                    alternativeLabel
                    sx={{
                      '& .MuiStepLabel-label': {
                        color: '#b0b3b8',
                        fontWeight: 'bold'
                      },
                      '& .MuiStepLabel-label.Mui-active': {
                        color: 'white'
                      },
                      '& .MuiStepLabel-label.Mui-completed': {
                        color: '#4caf50'
                      }
                    }}
                  >
                    {['Select Amount', 'Confirm Details', 'Send Transaction', 'Success'].map((label) => (
                      <Step key={label}>
                        <StepLabel>{label}</StepLabel>
                      </Step>
                    ))}
                  </Stepper>
                </Box>

                {/* Step Content */}
                <CardContent sx={{ p: 4 }}>
                  {currentStep === 'select-amount' && (
                    <Box sx={{ maxWidth: 600, mx: 'auto' }}>
                      <Box sx={{ textAlign: 'center', mb: 4 }}>
                        <Typography variant="h4" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                          How much would you like to deposit?
                        </Typography>
                        <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                          Choose your network and amount to get started
                        </Typography>
                      </Box>
                      
                      {/* Chain Selection */}
                      <Box sx={{ mb: 4 }}>
                        <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold', mb: 3 }}>
                          Select Network
                        </Typography>
                        <Grid container spacing={2}>
                          {chains.map((chain) => (
                            <Grid item xs={12} key={chain.chain_id}>
                              <Paper
                                onClick={() => {
                                  setSelectedChain(chain.chain_id)
                                  showNotification(`Switched to ${chain.name} network`, 'info')
                                }}
                                sx={{
                                  p: 3,
                                  cursor: 'pointer',
                                  border: selectedChain === chain.chain_id 
                                    ? '2px solid #00d4ff' 
                                    : '2px solid rgba(255, 255, 255, 0.1)',
                                  background: selectedChain === chain.chain_id 
                                    ? 'linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(124, 58, 237, 0.2))'
                                    : 'rgba(255, 255, 255, 0.05)',
                                  transition: 'all 0.3s ease',
                                  '&:hover': {
                                    background: 'rgba(255, 255, 255, 0.1)',
                                    transform: 'translateY(-2px)'
                                  }
                                }}
                              >
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                  <Box>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                                      <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold' }}>
                                        {chain.name}
                                      </Typography>
                                      {chain.chain_id === 43114 && (
                                        <Chip 
                                          label="ACTIVE" 
                                          size="small" 
                                          sx={{ 
                                            backgroundColor: '#4caf50', 
                                            color: 'white', 
                                            fontSize: '10px',
                                            height: '20px'
                                          }} 
                                        />
                                      )}
                                      {chain.chain_id === 43113 && (
                                        <Chip 
                                          label="INACTIVE" 
                                          size="small" 
                                          sx={{ 
                                            backgroundColor: '#ff9800', 
                                            color: 'white', 
                                            fontSize: '10px',
                                            height: '20px'
                                          }} 
                                        />
                                      )}
                                    </Box>
                                    <Typography variant="body2" sx={{ color: '#b0b3b8' }}>
                                      Native Token: {chain.native_currency}
                                    </Typography>
                                    {chain.chain_id === 43113 && (
                                      <Typography variant="caption" sx={{ color: '#ff9800', fontSize: '11px' }}>
                                        Microservice configured for mainnet
                                      </Typography>
                                    )}
                                  </Box>
                                  {selectedChain === chain.chain_id && (
                                    <CheckCircle sx={{ color: '#00d4ff', fontSize: 30 }} />
                                  )}
                                </Box>
                              </Paper>
                            </Grid>
                          ))}
                        </Grid>
                      </Box>

                      {/* Chain Mismatch Warning */}
                      {isConnected && selectedChain && chainId !== selectedChain && (
                        <Box sx={{ mb: 4 }}>
                          <Alert 
                            severity="warning" 
                            sx={{ 
                              backgroundColor: 'rgba(255, 193, 7, 0.1)',
                              border: '1px solid rgba(255, 193, 7, 0.3)',
                              '& .MuiAlert-message': { color: '#ffc107' }
                            }}
                          >
                            <Typography variant="body2" sx={{ mb: 1 }}>
                              Your wallet is connected to chain {chainId}, but you've selected chain {selectedChain}.
                            </Typography>
                            <Typography variant="body2">
                              Please switch your wallet to the selected network or choose a different network above.
                            </Typography>
                          </Alert>
                        </Box>
                      )}

                      {/* Amount Input */}
                      <Box sx={{ mb: 4 }}>
                        <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                          Amount ({getCurrentChain()?.native_currency || 'ETH'})
                        </Typography>
                        <TextField
                          fullWidth
                          type="number"
                          value={depositAmount}
                          onChange={(e) => {
                            setDepositAmount(e.target.value)
                          }}
                          placeholder="0.0"
                          inputProps={{ step: '0.001', min: '0' }}
                          sx={{
                            '& .MuiOutlinedInput-root': {
                              backgroundColor: 'rgba(255, 255, 255, 0.1)',
                              '& fieldset': {
                                borderColor: 'rgba(255, 255, 255, 0.3)',
                                borderWidth: 2
                              },
                              '&:hover fieldset': {
                                borderColor: 'rgba(255, 255, 255, 0.5)',
                              },
                              '&.Mui-focused fieldset': {
                                borderColor: '#00d4ff',
                              },
                              '& input': {
                                color: 'white',
                                fontSize: '20px',
                                padding: '16px'
                              }
                            }
                          }}
                        />
                        {userBalance && (
                          <Typography variant="body2" sx={{ color: '#4caf50', mt: 1, fontWeight: 'bold' }}>
                            Available: {parseFloat(formatEther(userBalance.value)).toFixed(4)} {userBalance.symbol}
                          </Typography>
                        )}
                      </Box>

                      {/* Quick Amount Buttons */}
                      <Box sx={{ mb: 4 }}>
                        <Grid container spacing={2}>
                          {['0.1', '0.5', '1.0', '2.0'].map((amount) => (
                            <Grid item xs={3} key={amount}>
                              <Button
                                fullWidth
                                variant="outlined"
                                onClick={() => {
                                  setDepositAmount(amount)
                                  showNotification(`Set amount to ${amount} AVAX`, 'info')
                                }}
                                sx={{
                                  borderColor: 'rgba(255, 255, 255, 0.3)',
                                  color: 'white',
                                  py: 1.5,
                                  fontWeight: 'bold',
                                  '&:hover': {
                                    borderColor: '#00d4ff',
                                    backgroundColor: 'rgba(0, 212, 255, 0.1)',
                                    transform: 'scale(1.05)'
                                  }
                                }}
                              >
                                {amount}
                              </Button>
                            </Grid>
                          ))}
                        </Grid>
                      </Box>

                      <Button
                        fullWidth
                        variant="contained"
                        size="large"
                        onClick={generateDepositAddress}
                        disabled={!depositAmount || !selectedChain || loading}
                        sx={{
                          background: 'linear-gradient(45deg, #00d4ff, #7c3aed)',
                          color: 'white',
                          py: 2,
                          fontSize: '18px',
                          fontWeight: 'bold',
                          textTransform: 'none',
                          borderRadius: 3,
                          boxShadow: '0 8px 32px rgba(0, 212, 255, 0.3)',
                          '&:hover': {
                            background: 'linear-gradient(45deg, #0099cc, #5a2d91)',
                            transform: 'translateY(-2px)',
                            boxShadow: '0 12px 40px rgba(0, 212, 255, 0.4)'
                          },
                          '&:disabled': {
                            opacity: 0.5,
                            transform: 'none',
                            background: 'gray'
                          }
                        }}
                      >
                        {loading ? (
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <CircularProgress size={24} sx={{ color: 'white', mr: 2 }} />
                            Generating Address...
                          </Box>
                        ) : (
                          'Continue to Confirmation'
                        )}
                      </Button>
                    </Box>
                  )}
                  {/* Other steps would go here with similar Material-UI styling */}
                  {currentStep === 'confirm-details' && depositAddress && (
                    <Box sx={{ maxWidth: 600, mx: 'auto' }}>
                      <Box sx={{ textAlign: 'center', mb: 4 }}>
                        <Typography variant="h4" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                          Confirm Deposit Details
                        </Typography>
                        <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                          Please review your deposit information before proceeding
                        </Typography>
                      </Box>

                      {/* Deposit Summary */}
                      <Card sx={{ mb: 4, backgroundColor: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
                        <CardContent sx={{ p: 4 }}>
                          <Grid container spacing={3}>
                            <Grid item xs={12} sm={6}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 1 }}>Amount</Typography>
                              <Typography variant="h6" sx={{ color: '#00d4ff', fontWeight: 'bold' }}>
                                {depositAmount} {getCurrentChain()?.native_currency}
                              </Typography>
                            </Grid>
                            <Grid item xs={12} sm={6}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 1 }}>Network</Typography>
                              <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold' }}>
                                {depositAddress.chain_name}
                              </Typography>
                            </Grid>
                            <Grid item xs={12}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 1 }}>From (Your Wallet)</Typography>
                              <Chip 
                                label={address} 
                                sx={{ 
                                  fontFamily: 'monospace',
                                  backgroundColor: 'rgba(76, 175, 80, 0.2)',
                                  color: '#4caf50',
                                  border: '1px solid rgba(76, 175, 80, 0.3)',
                                  fontSize: '12px'
                                }}
                              />
                            </Grid>
                            <Grid item xs={12}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 1 }}>To (AgentChain Platform)</Typography>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Chip 
                                  label={depositAddress.smart_account} 
                                  sx={{ 
                                    fontFamily: 'monospace',
                                    backgroundColor: 'rgba(0, 212, 255, 0.2)',
                                    color: '#00d4ff',
                                    border: '1px solid rgba(0, 212, 255, 0.3)',
                                    fontSize: '12px',
                                    maxWidth: 300
                                  }}
                                />
                                <IconButton
                                  onClick={() => copyToClipboard(depositAddress.smart_account)}
                                  sx={{ color: '#00d4ff' }}
                                >
                                  <ContentCopy />
                                </IconButton>
                              </Box>
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>

                      {/* Important Notice */}
                      <Alert 
                        severity="info"
                        sx={{ 
                          mb: 4,
                          backgroundColor: 'rgba(33, 150, 243, 0.1)',
                          border: '1px solid rgba(33, 150, 243, 0.3)',
                          '& .MuiAlert-icon': { color: '#2196f3' },
                          '& .MuiAlert-message': { color: 'white' }
                        }}
                      >
                        <Typography variant="body2">
                          <strong>Important:</strong> Send exactly {depositAmount} {getCurrentChain()?.native_currency} to the address above. 
                          Your funds will be automatically detected and credited to your AgentChain account.
                        </Typography>
                      </Alert>

                      {/* Action Buttons */}
                      <Box sx={{ display: 'flex', gap: 2 }}>
                        <Button
                          variant="outlined"
                          onClick={() => setCurrentStep('select-amount')}
                          sx={{ 
                            borderColor: 'rgba(255, 255, 255, 0.3)', 
                            color: 'white',
                            px: 3,
                            py: 1.5,
                            '&:hover': {
                              borderColor: 'rgba(255, 255, 255, 0.5)',
                              backgroundColor: 'rgba(255, 255, 255, 0.05)'
                            }
                          }}
                        >
                          Back
                        </Button>
                        <Button
                          fullWidth
                          variant="contained"
                          onClick={() => setCurrentStep('send-transaction')}
                          sx={{
                            background: 'linear-gradient(45deg, #00d4ff, #7c3aed)',
                            color: 'white',
                            py: 1.5,
                            fontSize: '16px',
                            fontWeight: 'bold',
                            textTransform: 'none',
                            '&:hover': {
                              background: 'linear-gradient(45deg, #0099cc, #5a2d91)',
                              transform: 'translateY(-1px)'
                            }
                          }}
                        >
                          Proceed to Send Transaction
                        </Button>
                      </Box>
                    </Box>
                  )}

                  {currentStep === 'send-transaction' && depositAddress && (
                    <Box sx={{ maxWidth: 700, mx: 'auto' }}>
                      <Box sx={{ textAlign: 'center', mb: 4 }}>
                        <Typography variant="h4" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                          Send Transaction
                        </Typography>
                        <Typography variant="body1" sx={{ color: '#b0b3b8' }}>
                          Choose how you'd like to send your deposit
                        </Typography>
                      </Box>

                      <Grid container spacing={3} sx={{ mb: 4 }}>
                        {/* Direct Wallet Send */}
                        <Grid item xs={12} md={6}>
                          <Card sx={{ 
                            height: '100%',
                            backgroundColor: 'rgba(255, 255, 255, 0.05)', 
                            border: '1px solid rgba(0, 212, 255, 0.3)',
                            '&:hover': { backgroundColor: 'rgba(255, 255, 255, 0.08)' }
                          }}>
                            <CardContent sx={{ p: 3, textAlign: 'center' }}>
                              <Send sx={{ fontSize: 40, color: '#00d4ff', mb: 2 }} />
                              <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold', mb: 1 }}>
                                Send via Connected Wallet
                              </Typography>
                              <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 3 }}>
                                Send directly from your connected wallet with one click
                              </Typography>
                              <Button
                                fullWidth
                                variant="contained"
                                onClick={handleSendTransaction}
                                disabled={isTxPending}
                                sx={{
                                  background: 'linear-gradient(45deg, #00d4ff, #7c3aed)',
                                  '&:disabled': { opacity: 0.5 }
                                }}
                              >
                                {isTxPending ? (
                                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                    <CircularProgress size={20} sx={{ color: 'white', mr: 1 }} />
                                    Sending...
                                  </Box>
                                ) : (
                                  'Send Transaction'
                                )}
                              </Button>
                            </CardContent>
                          </Card>
                        </Grid>

                        {/* QR Code Option */}
                        <Grid item xs={12} md={6}>
                          <Card sx={{ 
                            height: '100%',
                            backgroundColor: 'rgba(255, 255, 255, 0.05)', 
                            border: '1px solid rgba(124, 58, 237, 0.3)',
                            '&:hover': { backgroundColor: 'rgba(255, 255, 255, 0.08)' }
                          }}>
                            <CardContent sx={{ p: 3, textAlign: 'center' }}>
                              <QrCode2 sx={{ fontSize: 40, color: '#7c3aed', mb: 2 }} />
                              <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold', mb: 1 }}>
                                Scan QR Code
                              </Typography>
                              <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 3 }}>
                                Scan with your mobile wallet app
                              </Typography>
                              <Button
                                fullWidth
                                variant="outlined"
                                onClick={() => setShowQR(!showQR)}
                                sx={{
                                  borderColor: '#7c3aed',
                                  color: '#7c3aed',
                                  '&:hover': {
                                    borderColor: '#7c3aed',
                                    backgroundColor: 'rgba(124, 58, 237, 0.1)'
                                  }
                                }}
                              >
                                {showQR ? 'Hide QR Code' : 'Show QR Code'}
                              </Button>
                            </CardContent>
                          </Card>
                        </Grid>
                      </Grid>

                      {/* QR Code Display */}
                      {showQR && qrCodeUrl && (
                        <Fade in>
                          <Card sx={{ mb: 4, backgroundColor: 'rgba(255, 255, 255, 0.05)', textAlign: 'center' }}>
                            <CardContent sx={{ p: 4 }}>
                              <img 
                                src={qrCodeUrl} 
                                alt="Deposit QR Code" 
                                style={{ maxWidth: '250px', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px' }}
                              />
                              <Typography variant="body2" sx={{ color: '#b0b3b8', mt: 2 }}>
                                Scan with your mobile wallet to send {depositAmount} {getCurrentChain()?.native_currency}
                              </Typography>
                            </CardContent>
                          </Card>
                        </Fade>
                      )}

                      {/* Manual Transfer */}
                      <Card sx={{ mb: 4, backgroundColor: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(76, 175, 80, 0.3)' }}>
                        <CardContent sx={{ p: 3 }}>
                          <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                            Manual Transfer
                          </Typography>
                          <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 2 }}>
                            Copy the address below and send manually from any wallet:
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 2, backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: 1 }}>
                            <Typography 
                              variant="body2" 
                              sx={{ 
                                fontFamily: 'monospace', 
                                color: '#4caf50',
                                flex: 1,
                                wordBreak: 'break-all'
                              }}
                            >
                              {depositAddress.smart_account}
                            </Typography>
                            <IconButton
                              onClick={() => copyToClipboard(depositAddress.smart_account)}
                              sx={{ color: '#4caf50' }}
                            >
                              <ContentCopy />
                            </IconButton>
                          </Box>
                        </CardContent>
                      </Card>

                      {/* Back Button */}
                      <Box sx={{ textAlign: 'center' }}>
                        <Button
                          variant="outlined"
                          onClick={() => setCurrentStep('confirm-details')}
                          sx={{ 
                            borderColor: 'rgba(255, 255, 255, 0.3)', 
                            color: 'white',
                            px: 4,
                            '&:hover': {
                              borderColor: 'rgba(255, 255, 255, 0.5)',
                              backgroundColor: 'rgba(255, 255, 255, 0.05)'
                            }
                          }}
                        >
                          Back to Confirmation
                        </Button>
                      </Box>
                    </Box>
                  )}

                  {currentStep === 'monitoring' && (
                    <Box sx={{ maxWidth: 500, mx: 'auto', textAlign: 'center' }}>
                      <CircularProgress size={80} sx={{ color: '#00d4ff', mb: 4 }} />
                      <Typography variant="h5" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                        Transaction Sent
                      </Typography>
                      <Typography variant="body1" sx={{ color: '#b0b3b8', mb: 4 }}>
                        Waiting for confirmation on the blockchain...
                      </Typography>
                      
                      {isTxSuccess && (
                        <Fade in>
                          <Alert 
                            severity="success"
                            sx={{ 
                              backgroundColor: 'rgba(76, 175, 80, 0.1)',
                              border: '1px solid rgba(76, 175, 80, 0.3)',
                              '& .MuiAlert-icon': { color: '#4caf50' },
                              '& .MuiAlert-message': { color: 'white' },
                              mb: 3
                            }}
                          >
                            <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                              Transaction successful!
                            </Typography>
                            <Button
                              onClick={() => setCurrentStep('success')}
                              sx={{ mt: 2, color: '#4caf50', fontWeight: 'bold' }}
                            >
                              Continue
                            </Button>
                          </Alert>
                        </Fade>
                      )}

                      {txError && (
                        <Fade in>
                          <Alert 
                            severity="error"
                            sx={{ 
                              backgroundColor: 'rgba(211, 47, 47, 0.1)',
                              border: '1px solid rgba(211, 47, 47, 0.3)',
                              '& .MuiAlert-icon': { color: '#f44336' },
                              '& .MuiAlert-message': { color: 'white' },
                              mb: 3
                            }}
                          >
                            <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                              Transaction failed
                            </Typography>
                            <Typography variant="body2" sx={{ mt: 1 }}>
                              {txError.message}
                            </Typography>
                            <Button
                              onClick={() => setCurrentStep('send-transaction')}
                              sx={{ mt: 2, color: '#f44336', fontWeight: 'bold' }}
                            >
                              Try Again
                            </Button>
                          </Alert>
                        </Fade>
                      )}
                    </Box>
                  )}

                  {currentStep === 'success' && (
                    <Box sx={{ maxWidth: 500, mx: 'auto', textAlign: 'center' }}>
                      <CheckCircle sx={{ fontSize: 100, color: '#4caf50', mb: 3 }} />
                      <Typography variant="h4" sx={{ color: 'white', fontWeight: 'bold', mb: 2 }}>
                        Deposit Successful!
                      </Typography>
                      <Typography variant="body1" sx={{ color: '#b0b3b8', mb: 4 }}>
                        Your funds have been deposited and will be available for trading shortly.
                      </Typography>
                      
                      <Card sx={{ mb: 4, backgroundColor: 'rgba(76, 175, 80, 0.1)', border: '1px solid rgba(76, 175, 80, 0.3)' }}>
                        <CardContent sx={{ p: 3 }}>
                          <Typography variant="body2" sx={{ color: '#b0b3b8', mb: 1 }}>
                            Deposited Amount
                          </Typography>
                          <Typography variant="h4" sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                            {depositAmount} {getCurrentChain()?.native_currency}
                          </Typography>
                        </CardContent>
                      </Card>

                      <Button
                        variant="contained"
                        onClick={resetFlow}
                        sx={{
                          background: 'linear-gradient(45deg, #00d4ff, #7c3aed)',
                          px: 4,
                          py: 1.5,
                          fontSize: '16px',
                          fontWeight: 'bold',
                          textTransform: 'none',
                          '&:hover': {
                            background: 'linear-gradient(45deg, #0099cc, #5a2d91)'
                          }
                        }}
                      >
                        Make Another Deposit
                      </Button>
                    </Box>
                  )}

                  {/* Fallback for any other steps */}
                  {!['select-amount', 'confirm-details', 'send-transaction', 'monitoring', 'success'].includes(currentStep) && (
                    <Box sx={{ textAlign: 'center', p: 4 }}>
                      <Typography variant="h5" sx={{ color: 'white', mb: 2 }}>
                        Unknown Step
                      </Typography>
                      <Button
                        variant="outlined"
                        onClick={() => setCurrentStep('select-amount')}
                        sx={{ color: 'white', borderColor: 'white' }}
                      >
                        Start Over
                      </Button>
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grow>

            {/* User Balances */}
            {userBalances.length > 0 && (
              <Grow in timeout={2400}>
                <Card 
                  sx={{ 
                    mt: 4,
                    background: 'rgba(255, 255, 255, 0.1)',
                    backdropFilter: 'blur(20px)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: 4,
                    overflow: 'hidden'
                  }}
                >
                  <CardContent sx={{ p: 0 }}>
                    <Box sx={{ p: 3, borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
                      <Typography variant="h5" sx={{ color: 'white', fontWeight: 'bold' }}>
                        Your Deposit History
                      </Typography>
                    </Box>
                    <Box sx={{ overflowX: 'auto' }}>
                      {userBalances.map((balance, index) => (
                        <Box 
                          key={index}
                          sx={{ 
                            p: 3, 
                            borderBottom: index < userBalances.length - 1 ? '1px solid rgba(255, 255, 255, 0.1)' : 'none',
                            '&:hover': { backgroundColor: 'rgba(255, 255, 255, 0.05)' }
                          }}
                        >
                          <Grid container spacing={2} alignItems="center">
                            <Grid item xs={12} sm={2}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8' }}>Chain</Typography>
                              <Typography variant="body1" sx={{ color: 'white', fontWeight: 'bold' }}>
                                {balance.chain_name}
                              </Typography>
                            </Grid>
                            <Grid item xs={12} sm={2}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8' }}>Token</Typography>
                              <Typography variant="body1" sx={{ color: 'white', fontWeight: 'bold' }}>
                                {balance.token_symbol}
                              </Typography>
                            </Grid>
                            <Grid item xs={12} sm={2}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8' }}>Balance</Typography>
                              <Typography variant="body1" sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                                {balance.balance}
                              </Typography>
                            </Grid>
                            <Grid item xs={12} sm={2}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8' }}>USD Value</Typography>
                              <Typography variant="body1" sx={{ color: 'white', fontWeight: 'bold' }}>
                                {balance.usd_value || 'N/A'}
                              </Typography>
                            </Grid>
                            <Grid item xs={12} sm={4}>
                              <Typography variant="body2" sx={{ color: '#b0b3b8' }}>Last Updated</Typography>
                              <Typography variant="body1" sx={{ color: 'white' }}>
                                {new Date(balance.last_updated).toLocaleString()}
                              </Typography>
                            </Grid>
                          </Grid>
                        </Box>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grow>
            )}
          </>
        )}

        {/* Error Display */}
        {error && (
          <Fade in>
            <Alert 
              severity="error" 
              sx={{ 
                mt: 3,
                backgroundColor: 'rgba(211, 47, 47, 0.1)',
                border: '1px solid rgba(211, 47, 47, 0.3)',
                '& .MuiAlert-icon': { color: '#f44336' },
                '& .MuiAlert-message': { color: 'white' }
              }}
            >
              <strong>Error:</strong> {error}
            </Alert>
          </Fade>
        )}
      </Container>
      
      {/* Notification Snackbar */}
      <Slide direction="up" in={notificationOpen} mountOnEnter unmountOnExit>
        <Alert 
          severity={notificationSeverity}
          sx={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 9999,
            minWidth: 300,
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.24)',
            backgroundColor: notificationSeverity === 'success' ? '#2e7d32' : 
                           notificationSeverity === 'error' ? '#d32f2f' : '#1976d2',
            color: 'white',
            '& .MuiAlert-icon': {
              color: 'white'
            },
            border: `1px solid ${notificationSeverity === 'success' ? '#4caf50' : 
                                notificationSeverity === 'error' ? '#f44336' : '#2196f3'}`
          }}
          onClose={() => setNotificationOpen(false)}
        >
          {notificationMessage}
        </Alert>
      </Slide>
    </Box>
  )
}

export default DepositDashboard
