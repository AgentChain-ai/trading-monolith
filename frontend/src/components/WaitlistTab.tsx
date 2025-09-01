import React, { useState, useEffect } from 'react'
import {
  Box,
  Container,
  Typography,
  TextField,
  Button,
  Card,
  CardContent,
  Grid,
  Alert,
  CircularProgress,
  Chip,
  InputAdornment,
  IconButton,
  Link,
  Divider,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Paper,
  Fade,
  Slide,
  Grow,
  LinearProgress
} from '@mui/material'
import {
  Email,
  AccountBalanceWallet,
  Twitter,
  Group,
  EmojiEvents,
  TrendingUp,
  Security,
  Rocket,
  Person,
  ContentCopy,
  CheckCircle,
  AccessTime,
  Star
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../services/api'
import toast from 'react-hot-toast'

interface WaitlistStats {
  total_registrations: number
  recent_registrations_24h: number
  total_airdrop_allocated: number
  wallet_completion_rate: number
}

interface RecentRegistration {
  position: number
  email_domain: string
  wallet_connected: boolean
  airdrop_amount: number
  time_ago: string
}

interface WaitlistTabProps {
  isActive?: boolean
}

const WaitlistTab: React.FC<WaitlistTabProps> = ({ isActive = true }) => {
  const [formData, setFormData] = useState({
    email: '',
    wallet_address: '',
    twitter_handle: '',
    discord_handle: '',
    referral_code: ''
  })
  const [registrationComplete, setRegistrationComplete] = useState(false)
  const [registrationResult, setRegistrationResult] = useState<any>(null)
  const [copiedReferral, setCopiedReferral] = useState(false)
  const queryClient = useQueryClient()

  // Get waitlist stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['waitlist-stats'],
    queryFn: () => apiClient.getWaitlistStats(),
    refetchInterval: 30000, // Update every 30 seconds
  })

  // Get recent registrations
  const { data: recentRegistrations } = useQuery({
    queryKey: ['recent-registrations'],
    queryFn: () => apiClient.getRecentRegistrations(10),
    refetchInterval: 15000, // Update every 15 seconds
  })

  // Registration mutation
  const registerMutation = useMutation({
    mutationFn: (data: typeof formData) => apiClient.registerForWaitlist(data),
    onSuccess: (data: any) => {
      setRegistrationResult(data.data)
      setRegistrationComplete(true)
      toast.success(`Welcome to AgentChain.Trade! You're #${data.data.position} on the waitlist!`)
      queryClient.invalidateQueries({ queryKey: ['waitlist-stats'] })
      queryClient.invalidateQueries({ queryKey: ['recent-registrations'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Registration failed. Please try again.')
    }
  })

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!formData.email) {
      toast.error('Email address is required')
      return
    }

    registerMutation.mutate(formData)
  }

  const copyReferralCode = () => {
    if (registrationResult?.referral_code) {
      navigator.clipboard.writeText(registrationResult.referral_code)
      setCopiedReferral(true)
      toast.success('Referral code copied!')
      setTimeout(() => setCopiedReferral(false), 2000)
    }
  }

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat().format(num)
  }

  if (registrationComplete && registrationResult) {
    return (
      <Fade in={true} timeout={800}>
        <Container maxWidth="md" sx={{ py: 4 }}>
          <Card sx={{ 
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: 'white',
            borderRadius: 4,
            boxShadow: '0 20px 40px rgba(0,0,0,0.1)'
          }}>
            <CardContent sx={{ p: 6, textAlign: 'center' }}>
              <CheckCircle sx={{ fontSize: 80, color: '#4ade80', mb: 2 }} />
              
              <Typography variant="h3" fontWeight="bold" gutterBottom>
                Welcome to AgentChain.Trade!
              </Typography>
              
              <Typography variant="h6" sx={{ mb: 4, opacity: 0.9 }}>
                You're officially on the waitlist for the future of AI trading
              </Typography>

              <Grid container spacing={3} sx={{ mb: 4 }}>
                <Grid item xs={12} md={3}>
                  <Paper sx={{ p: 3, bgcolor: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)' }}>
                    <Typography variant="h4" fontWeight="bold" color="primary">
                      #{formatNumber(registrationResult.position)}
                    </Typography>
                    <Typography variant="body2">Your Position</Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={3}>
                  <Paper sx={{ p: 3, bgcolor: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)' }}>
                    <Typography variant="h4" fontWeight="bold" color="success.main">
                      {formatNumber(registrationResult.airdrop_amount)}
                    </Typography>
                    <Typography variant="body2">Token Allocation</Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper sx={{ p: 3, bgcolor: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)' }}>
                    <Box display="flex" alignItems="center" justifyContent="space-between">
                      <Box>
                        <Typography variant="h6" fontWeight="bold">
                          {registrationResult.referral_code}
                        </Typography>
                        <Typography variant="body2">Your Referral Code</Typography>
                      </Box>
                      <IconButton 
                        onClick={copyReferralCode}
                        sx={{ color: 'white' }}
                      >
                        {copiedReferral ? <CheckCircle /> : <ContentCopy />}
                      </IconButton>
                    </Box>
                  </Paper>
                </Grid>
              </Grid>

              <Typography variant="h6" sx={{ mb: 2 }}>
                🎉 What happens next?
              </Typography>
              
              <Grid container spacing={2} sx={{ mb: 4 }}>
                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 3 }}>
                    <Email sx={{ fontSize: 40, color: '#4ade80', mb: 1 }} />
                    <Typography variant="h6" gutterBottom>Email Updates</Typography>
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>
                      Get notified about platform updates, beta access, and airdrop announcements
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 3 }}>
                    <EmojiEvents sx={{ fontSize: 40, color: '#fbbf24', mb: 1 }} />
                    <Typography variant="h6" gutterBottom>Token Airdrop</Typography>
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>
                      Receive your allocation of AgentChain tokens when we launch
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 3 }}>
                    <Rocket sx={{ fontSize: 40, color: '#8b5cf6', mb: 1 }} />
                    <Typography variant="h6" gutterBottom>Early Access</Typography>
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>
                      Get priority access to advanced AI trading features
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              <Typography variant="body1" sx={{ mb: 3, opacity: 0.9 }}>
                Share your referral code with friends to earn bonus tokens!
              </Typography>

              <Button
                variant="contained"
                size="large"
                onClick={() => window.location.reload()}
                sx={{ 
                  bgcolor: 'rgba(255,255,255,0.2)',
                  backdropFilter: 'blur(10px)',
                  '&:hover': { bgcolor: 'rgba(255,255,255,0.3)' }
                }}
              >
                Join Another Person
              </Button>
            </CardContent>
          </Card>
        </Container>
      </Fade>
    )
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Hero Section */}
      <Slide direction="up" in={isActive} timeout={600}>
        <Box textAlign="center" sx={{ mb: 6 }}>
          <Typography variant="h2" fontWeight="bold" gutterBottom sx={{ 
            background: 'linear-gradient(45deg, #667eea, #764ba2)',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            mb: 2
          }}>
            Join the Future of AI Trading
          </Typography>
          
          <Typography variant="h5" color="text.secondary" sx={{ mb: 4, maxWidth: '800px', mx: 'auto' }}>
            Get early access to AgentChain.Trade's revolutionary AI Trading Thesis Engine and receive exclusive token airdrops
          </Typography>

          {/* Stats Counter */}
          <Grow in={!statsLoading} timeout={800}>
            <Paper sx={{ 
              p: 3, 
              mb: 4, 
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              color: 'white',
              display: 'inline-block',
              borderRadius: 3
            }}>
              <Typography variant="h3" fontWeight="bold">
                {statsLoading ? (
                  <CircularProgress color="inherit" size={40} />
                ) : (
                  formatNumber(stats?.stats?.total_registrations || 0)
                )}
              </Typography>
              <Typography variant="h6">
                Traders Already Registered
              </Typography>
              {stats?.stats?.recent_registrations_24h > 0 && (
                <Typography variant="body2" sx={{ opacity: 0.9, mt: 1 }}>
                  {/* +{stats.stats.recent_registrations_24h} joined today */}
                </Typography>
              )}
            </Paper>
          </Grow>
        </Box>
      </Slide>

      <Grid container spacing={6}>
        {/* Registration Form */}
        <Grid item xs={12} md={8}>
          <Fade in={isActive} timeout={800}>
            <Card sx={{ 
              borderRadius: 4,
              boxShadow: '0 20px 40px rgba(0,0,0,0.1)',
              background: 'linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%)',
              backdropFilter: 'blur(10px)'
            }}>
              <CardContent sx={{ p: 4 }}>
                <Typography variant="h4" fontWeight="bold" gutterBottom>
                  Join the Waitlist
                </Typography>
                
                <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
                  Be among the first to experience next-generation AI trading technology
                </Typography>

                <form onSubmit={handleSubmit}>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label="Email Address"
                        type="email"
                        value={formData.email}
                        onChange={(e) => handleInputChange('email', e.target.value)}
                        required
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Email color="primary" />
                            </InputAdornment>
                          ),
                        }}
                        sx={{ mb: 2 }}
                      />
                    </Grid>

                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label="Wallet Address (Optional)"
                        value={formData.wallet_address}
                        onChange={(e) => handleInputChange('wallet_address', e.target.value)}
                        placeholder="0x..."
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <AccountBalanceWallet color="primary" />
                            </InputAdornment>
                          ),
                        }}
                        helperText="Connect your wallet to receive airdrops directly"
                        sx={{ mb: 2 }}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Twitter Handle (Optional)"
                        value={formData.twitter_handle}
                        onChange={(e) => handleInputChange('twitter_handle', e.target.value)}
                        placeholder="@username"
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Twitter color="primary" />
                            </InputAdornment>
                          ),
                        }}
                        sx={{ mb: 2 }}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Referral Code (Optional)"
                        value={formData.referral_code}
                        onChange={(e) => handleInputChange('referral_code', e.target.value)}
                        placeholder="Enter referral code"
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Group color="primary" />
                            </InputAdornment>
                          ),
                        }}
                        helperText="Get bonus tokens with a referral code"
                        sx={{ mb: 3 }}
                      />
                    </Grid>

                    <Grid item xs={12}>
                      <Button
                        type="submit"
                        fullWidth
                        variant="contained"
                        size="large"
                        disabled={registerMutation.isPending}
                        sx={{ 
                          py: 2,
                          background: 'linear-gradient(45deg, #667eea 30%, #764ba2 90%)',
                          fontSize: '1.1rem',
                          fontWeight: 'bold'
                        }}
                      >
                        {registerMutation.isPending ? (
                          <CircularProgress size={24} color="inherit" />
                        ) : (
                          'Join Waitlist & Get Tokens'
                        )}
                      </Button>
                    </Grid>
                  </Grid>
                </form>

                {/* Benefits */}
                <Box sx={{ mt: 4 }}>
                  <Typography variant="h6" gutterBottom>
                    🎁 What you'll get:
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={4}>
                      <Box display="flex" alignItems="center" sx={{ mb: 1 }}>
                        <EmojiEvents sx={{ color: 'gold', mr: 1 }} />
                        <Typography variant="body2">Token Airdrops</Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Box display="flex" alignItems="center" sx={{ mb: 1 }}>
                        <Security sx={{ color: 'green', mr: 1 }} />
                        <Typography variant="body2">Early Access</Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Box display="flex" alignItems="center" sx={{ mb: 1 }}>
                        <TrendingUp sx={{ color: 'blue', mr: 1 }} />
                        <Typography variant="body2">Beta Features</Typography>
                      </Box>
                    </Grid>
                  </Grid>
                </Box>
              </CardContent>
            </Card>
          </Fade>
        </Grid>

        {/* Recent Activity & Stats */}
        <Grid item xs={12} md={4}>
          <Fade in={isActive} timeout={1000}>
            <Box>
              {/* Live Activity */}
              <Card sx={{ mb: 3, borderRadius: 3 }}>
                <CardContent>
                  <Box display="flex" alignItems="center" sx={{ mb: 2 }}>
                    <AccessTime sx={{ mr: 1, color: 'primary.main' }} />
                    <Typography variant="h6" fontWeight="bold">
                      Live Activity
                    </Typography>
                  </Box>
                  
                  {recentRegistrations?.recent_registrations?.length > 0 ? (
                    <List dense>
                      {recentRegistrations.recent_registrations.slice(0, 5).map((reg: RecentRegistration, index: number) => (
                        <ListItem key={index} sx={{ px: 0 }}>
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: 'primary.main', width: 32, height: 32 }}>
                              <Person sx={{ fontSize: 18 }} />
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary={`***@${reg.email_domain}`}
                            secondary={
                              <Box>
                                <Typography variant="caption" color="text.secondary">
                                  {reg.time_ago} • {formatNumber(reg.airdrop_amount)} tokens
                                </Typography>
                                {reg.wallet_connected && (
                                  <Chip 
                                    label="Wallet Connected" 
                                    size="small" 
                                    color="success" 
                                    sx={{ ml: 1, height: 16, fontSize: '0.7rem' }}
                                  />
                                )}
                              </Box>
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      No recent activity
                    </Typography>
                  )}
                </CardContent>
              </Card>

              {/* Stats Summary */}
              <Card sx={{ borderRadius: 3 }}>
                <CardContent>
                  <Typography variant="h6" fontWeight="bold" gutterBottom>
                    📊 Community Stats
                  </Typography>
                  
                  {stats?.stats && (
                    <Grid container spacing={2}>
                      <Grid item xs={6}>
                        <Typography variant="h4" fontWeight="bold" color="primary.main">
                          {formatNumber(stats.stats.total_airdrop_allocated)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Total Tokens Allocated
                        </Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="h4" fontWeight="bold" color="success.main">
                          {Math.round(stats.stats.wallet_completion_rate)}%
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Have Connected Wallets
                        </Typography>
                      </Grid>
                    </Grid>
                  )}
                </CardContent>
              </Card>
            </Box>
          </Fade>
        </Grid>
      </Grid>
    </Container>
  )
}

export default WaitlistTab
