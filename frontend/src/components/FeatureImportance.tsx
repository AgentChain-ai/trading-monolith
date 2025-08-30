import React from 'react'
import {
  Box,
  Typography,
  LinearProgress,
  Tooltip,
} from '@mui/material'
import { FeatureImportanceProps } from '../types'

const FeatureImportance: React.FC<FeatureImportanceProps> = ({ featureImportance }) => {
  // Feature display names and descriptions
  const featureConfig: Record<string, { name: string; description: string; color: string }> = {
    'narrative_heat': {
      name: 'Narrative Heat',
      description: 'Overall sentiment-weighted narrative strength',
      color: '#2196f3'
    },
    'positive_heat': {
      name: 'Positive Heat', 
      description: 'Positive sentiment contributions',
      color: '#4caf50'
    },
    'negative_heat': {
      name: 'Negative Heat',
      description: 'Negative sentiment contributions', 
      color: '#f44336'
    },
    'hype_velocity': {
      name: 'Hype Velocity',
      description: 'Rate of narrative change',
      color: '#ff9800'
    },
    'consensus': {
      name: 'Consensus',
      description: 'Agreement across sources',
      color: '#9c27b0'
    },
    'risk_polarity': {
      name: 'Risk Polarity',
      description: 'Risk vs opportunity balance',
      color: '#f44336'
    },
    'p_listing': {
      name: 'Listing Probability',
      description: 'Likelihood of exchange listing',
      color: '#4caf50'
    },
    'p_partnership': {
      name: 'Partnership Probability',
      description: 'Likelihood of partnership announcement',
      color: '#2196f3'
    },
    'p_hack': {
      name: 'Hack Risk',
      description: 'Security incident probability',
      color: '#f44336'
    },
    'p_regulatory': {
      name: 'Regulatory Risk',
      description: 'Regulatory event probability',
      color: '#ff5722'
    },
    'p_funding': {
      name: 'Funding Probability',
      description: 'Investment/funding event likelihood',
      color: '#9c27b0'
    },
    'p_tech': {
      name: 'Tech Update Probability',
      description: 'Technical development likelihood',
      color: '#00bcd4'
    },
    'liquidity_usd_log': {
      name: 'Liquidity (Log)',
      description: 'Available trading liquidity',
      color: '#607d8b'
    },
    'trades_count_change': {
      name: 'Trading Activity',
      description: 'Change in trading volume',
      color: '#795548'
    },
    'spread_estimate': {
      name: 'Spread',
      description: 'Bid-ask spread estimate',
      color: '#9e9e9e'
    }
  }

  // Sort features by importance
  const sortedFeatures = Object.entries(featureImportance)
    .filter(([_, importance]) => importance > 0)
    .sort(([_, a], [__, b]) => b - a)
    .slice(0, 8) // Show top 8 features

  if (sortedFeatures.length === 0) {
    return (
      <Box textAlign="center" py={4}>
        <Typography color="textSecondary" variant="body2">
          No feature importance data available
        </Typography>
      </Box>
    )
  }

  const maxImportance = Math.max(...sortedFeatures.map(([_, importance]) => importance))

  return (
    <Box>
      {sortedFeatures.map(([feature, importance], index) => {
        const config = featureConfig[feature] || {
          name: feature.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
          description: 'Feature importance',
          color: '#9e9e9e'
        }
        
        const normalizedImportance = (importance / maxImportance) * 100

        return (
          <Box key={feature} sx={{ mb: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
              <Tooltip title={config.description} arrow>
                <Typography 
                  variant="body2" 
                  sx={{ 
                    fontWeight: 500,
                    cursor: 'help',
                    '&:hover': {
                      color: 'primary.main'
                    }
                  }}
                >
                  {index + 1}. {config.name}
                </Typography>
              </Tooltip>
              
              <Typography variant="body2" color="textSecondary">
                {importance.toFixed(3)}
              </Typography>
            </Box>
            
            <LinearProgress
              variant="determinate"
              value={normalizedImportance}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: config.color,
                  borderRadius: 4,
                }
              }}
            />
            
            {/* Rank indicator */}
            <Box display="flex" alignItems="center" gap={1} sx={{ mt: 0.5 }}>
              <Box
                sx={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  backgroundColor: config.color,
                }}
              />
              <Typography variant="caption" color="textSecondary">
                {normalizedImportance.toFixed(1)}% relative importance
              </Typography>
            </Box>
          </Box>
        )
      })}
      
      {/* Summary */}
      <Box sx={{ mt: 3, p: 2, backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: 1 }}>
        <Typography variant="body2" color="textSecondary">
          Top {sortedFeatures.length} features shown • 
          {' '}Total features analyzed: {Object.keys(featureImportance).length}
        </Typography>
        <Typography variant="caption" color="textSecondary" display="block" sx={{ mt: 1 }}>
          Feature importance indicates how much each factor contributed to the prediction
        </Typography>
      </Box>
    </Box>
  )
}

export default FeatureImportance