import React from 'react'
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  LinearProgress,
  Divider,
  IconButton,
  Tooltip,
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  Refresh,
  Speed,
  Security,
} from '@mui/icons-material'
import { DashboardProps } from '../types'
import NarrativeChart from './NarrativeChart'
import ThesisCard from './ThesisCard'
import EventDistribution from './EventDistribution'
import EvidenceList from './EvidenceList'
import FeatureImportance from './FeatureImportance'

const Dashboard: React.FC<DashboardProps> = ({ token, data, onRefresh }) => {
  const { current_thesis, buckets, recent_articles, summary } = data

  const getConfidenceColor = (confidence: string) => {
    switch (confidence) {
      case 'HIGH': return 'success'
      case 'MEDIUM': return 'warning'
      case 'LOW': return 'error'
      default: return 'default'
    }
  }

  const getPredictionIcon = (probability: number) => {
    if (probability > 0.6) return <TrendingUp color="success" />
    if (probability < 0.4) return <TrendingDown color="error" />
    return <TrendingFlat color="warning" />
  }

  // Handle case where current_thesis might be undefined
  if (!current_thesis || typeof current_thesis.p_up_60m !== 'number') {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="h6" color="textSecondary" gutterBottom>
          No trading data available for {token}
        </Typography>
        <Typography variant="body2" color="textSecondary">
          Try refreshing or ingesting token data first.
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="body2">
                    Prediction
                  </Typography>
                  <Typography variant="h4">
                    {(current_thesis.p_up_60m * 100).toFixed(0)}%
                  </Typography>
                  <Chip 
                    label={current_thesis.confidence} 
                    color={getConfidenceColor(current_thesis.confidence) as any}
                    size="small"
                    sx={{ mt: 1 }}
                  />
                </Box>
                <Box>
                  {getPredictionIcon(current_thesis.p_up_60m)}
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="body2">
                    Narrative Heat
                  </Typography>
                  <Typography variant="h4">
                    {current_thesis.narrative_heat.toFixed(1)}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    {current_thesis.hype_velocity > 0 ? '+' : ''}{(current_thesis.hype_velocity * 100).toFixed(0)}% velocity
                  </Typography>
                </Box>
                <Speed color={Math.abs(current_thesis.narrative_heat) > 2 ? 'error' : 'primary'} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="body2">
                    Consensus
                  </Typography>
                  <Typography variant="h4">
                    {(current_thesis.consensus * 100).toFixed(0)}%
                  </Typography>
                  <Typography variant="body2" color="textSecondary" sx={{ textTransform: 'capitalize' }}>
                    {current_thesis.top_event.replace('-', ' ')}
                  </Typography>
                </Box>
                <LinearProgress 
                  variant="determinate" 
                  value={current_thesis.consensus * 100} 
                  sx={{ width: 40, height: 8, borderRadius: 4 }}
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom variant="body2">
                    Risk Polarity
                  </Typography>
                  <Typography variant="h4" color={current_thesis.risk_polarity < 0 ? 'error' : 'success'}>
                    {current_thesis.risk_polarity.toFixed(2)}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    {current_thesis.risk_polarity < -0.1 ? 'High Risk' : current_thesis.risk_polarity > 0.1 ? 'Low Risk' : 'Moderate'}
                  </Typography>
                </Box>
                <Security color={current_thesis.risk_polarity < 0 ? 'error' : 'success'} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content */}
      <Grid container spacing={3}>
        {/* Left Column */}
        <Grid item xs={12} lg={8}>
          {/* Trading Thesis */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between" sx={{ mb: 2 }}>
                <Typography variant="h6" gutterBottom>
                  Trading Thesis
                </Typography>
                <Tooltip title="Refresh Data">
                  <IconButton onClick={onRefresh} size="small">
                    <Refresh />
                  </IconButton>
                </Tooltip>
              </Box>
              <ThesisCard thesis={current_thesis} />
            </CardContent>
          </Card>

          {/* Narrative Heat Chart */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Narrative Heat Timeline
              </Typography>
              <NarrativeChart buckets={buckets} height={300} />
            </CardContent>
          </Card>

          {/* Feature Importance */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Key Factors
              </Typography>
              <FeatureImportance featureImportance={current_thesis.features_snapshot} />
            </CardContent>
          </Card>
        </Grid>

        {/* Right Column */}
        <Grid item xs={12} lg={4}>
          {/* Event Distribution */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Event Distribution
              </Typography>
              <EventDistribution 
                eventDistribution={buckets[buckets.length - 1]?.event_distribution || {}} 
              />
            </CardContent>
          </Card>

          {/* Evidence Articles */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Supporting Evidence
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                {current_thesis.evidence.length} articles analyzed
              </Typography>
              <EvidenceList evidence={current_thesis.evidence} />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Data Summary */}
      <Card sx={{ mt: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Data Summary
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={6} sm={3}>
              <Typography variant="body2" color="textSecondary">
                Total Buckets
              </Typography>
              <Typography variant="h6">
                {summary.total_buckets}
              </Typography>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Typography variant="body2" color="textSecondary">
                Avg Heat
              </Typography>
              <Typography variant="h6">
                {summary.avg_narrative_heat.toFixed(2)}
              </Typography>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Typography variant="body2" color="textSecondary">
                Articles
              </Typography>
              <Typography variant="h6">
                {recent_articles.length}
              </Typography>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Typography variant="body2" color="textSecondary">
                Last Updated
              </Typography>
              <Typography variant="h6">
                {new Date(current_thesis.timestamp).toLocaleTimeString()}
              </Typography>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
    </Box>
  )
}

export default Dashboard