import React from 'react'
import {
  Card,
  Typography,
  Box,
  Chip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Alert,
  LinearProgress,
} from '@mui/material'
import {
  CheckCircle,
  Warning,
} from '@mui/icons-material'
import { ThesisCardProps } from '../types'

const ThesisCard: React.FC<ThesisCardProps> = ({ thesis }) => {
  const getConfidenceColor = (confidence: string) => {
    switch (confidence) {
      case 'HIGH': return 'success'
      case 'MEDIUM': return 'warning' 
      case 'LOW': return 'error'
      default: return 'default'
    }
  }

  const getProbabilityColor = (probability: number) => {
    if (probability > 0.7) return 'success.main'
    if (probability > 0.3) return 'warning.main'
    return 'error.main'
  }

  const getDirectionText = (probability: number) => {
    if (probability > 0.6) return 'BULLISH'
    if (probability < 0.4) return 'BEARISH'
    return 'NEUTRAL'
  }

  return (
    <Box>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600 }}>
            {getDirectionText(thesis.p_up_60m)} Signal
          </Typography>
          <Typography variant="body2" color="textSecondary">
            {thesis.window_minutes} minute window • Updated {new Date(thesis.timestamp).toLocaleTimeString()}
          </Typography>
        </Box>
        <Box textAlign="right">
          <Typography variant="h3" color={getProbabilityColor(thesis.p_up_60m)}>
            {(thesis.p_up_60m * 100).toFixed(0)}%
          </Typography>
          <Chip 
            label={`${thesis.confidence} CONFIDENCE`}
            color={getConfidenceColor(thesis.confidence) as any}
            variant="filled"
          />
        </Box>
      </Box>

      {/* Probability Bar */}
      <Box sx={{ mb: 3 }}>
        <Box display="flex" justifyContent="space-between" sx={{ mb: 1 }}>
          <Typography variant="body2" color="textSecondary">
            Probability Up
          </Typography>
          <Typography variant="body2" color="textSecondary">
            {(thesis.p_up_60m * 100).toFixed(1)}%
          </Typography>
        </Box>
        <LinearProgress 
          variant="determinate" 
          value={thesis.p_up_60m * 100}
          sx={{ 
            height: 8, 
            borderRadius: 4,
            backgroundColor: 'rgba(255, 255, 255, 0.1)',
            '& .MuiLinearProgress-bar': {
              backgroundColor: getProbabilityColor(thesis.p_up_60m)
            }
          }}
        />
      </Box>

      {/* Key Metrics */}
      <Box display="flex" gap={2} sx={{ mb: 3 }}>
        <Card variant="outlined" sx={{ flex: 1, p: 1 }}>
          <Typography variant="body2" color="textSecondary" align="center">
            Heat
          </Typography>
          <Typography variant="h6" align="center" color={thesis.narrative_heat > 0 ? 'success.main' : 'error.main'}>
            {thesis.narrative_heat.toFixed(1)}
          </Typography>
        </Card>
        <Card variant="outlined" sx={{ flex: 1, p: 1 }}>
          <Typography variant="body2" color="textSecondary" align="center">
            Consensus
          </Typography>
          <Typography variant="h6" align="center">
            {(thesis.consensus * 100).toFixed(0)}%
          </Typography>
        </Card>
        <Card variant="outlined" sx={{ flex: 1, p: 1 }}>
          <Typography variant="body2" color="textSecondary" align="center">
            Velocity
          </Typography>
          <Typography variant="h6" align="center" color={thesis.hype_velocity > 0 ? 'success.main' : 'error.main'}>
            {thesis.hype_velocity > 0 ? '+' : ''}{(thesis.hype_velocity * 100).toFixed(0)}%
          </Typography>
        </Card>
        <Card variant="outlined" sx={{ flex: 1, p: 1 }}>
          <Typography variant="body2" color="textSecondary" align="center">
            Risk
          </Typography>
          <Typography variant="h6" align="center" color={thesis.risk_polarity < 0 ? 'error.main' : 'success.main'}>
            {thesis.risk_polarity.toFixed(2)}
          </Typography>
        </Card>
      </Box>

      {/* Primary Event */}
      <Alert severity="info" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Primary Narrative: {thesis.top_event.replace('-', ' ').toUpperCase()}
          </Typography>
          <Typography variant="body2">
            {thesis.consensus > 0.7 ? 'Strong' : thesis.consensus > 0.5 ? 'Moderate' : 'Weak'} consensus detected across sources
          </Typography>
        </Box>
      </Alert>

      {/* Reasoning */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Key Reasoning
        </Typography>
        <List dense>
          {thesis.reasoning.slice(0, 4).map((reason, index) => (
            <ListItem key={index} sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <CheckCircle color="primary" fontSize="small" />
              </ListItemIcon>
              <ListItemText 
                primary={reason}
                primaryTypographyProps={{ variant: 'body2' }}
              />
            </ListItem>
          ))}
        </List>
      </Box>

      {/* Guardrails */}
      <Box>
        <Typography variant="h6" gutterBottom sx={{ color: 'warning.main' }}>
          Risk Guardrails
        </Typography>
        <List dense>
          {thesis.guardrails.slice(0, 3).map((guardrail, index) => (
            <ListItem key={index} sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Warning color="warning" fontSize="small" />
              </ListItemIcon>
              <ListItemText 
                primary={guardrail}
                primaryTypographyProps={{ variant: 'body2' }}
              />
            </ListItem>
          ))}
        </List>
      </Box>
    </Box>
  )
}

export default ThesisCard