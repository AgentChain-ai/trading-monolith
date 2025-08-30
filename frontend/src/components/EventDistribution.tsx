import React from 'react'
import {
  Box,
  Typography,
  LinearProgress,
  Chip,
} from '@mui/material'
import { EventDistributionProps, EventType } from '../types'

const EventDistribution: React.FC<EventDistributionProps> = ({ eventDistribution }) => {
  // Event type colors and labels
  const eventConfig: Record<EventType, { color: string; label: string }> = {
    'listing': { color: '#4caf50', label: 'Listing' },
    'partnership': { color: '#2196f3', label: 'Partnership' },
    'hack': { color: '#f44336', label: 'Hack' },
    'depeg': { color: '#ff5722', label: 'Depeg' },
    'regulatory': { color: '#ff9800', label: 'Regulatory' },
    'funding': { color: '#9c27b0', label: 'Funding' },
    'tech': { color: '#00bcd4', label: 'Technical' },
    'market-note': { color: '#607d8b', label: 'Market Note' },
    'op-ed': { color: '#795548', label: 'Opinion' },
  }

  // Sort events by probability
  const sortedEvents = Object.entries(eventDistribution)
    .map(([event, probability]) => ({
      event: event as EventType,
      probability: probability || 0,
      config: eventConfig[event as EventType] || { color: '#9e9e9e', label: event }
    }))
    .filter(item => item.probability > 0.01) // Only show events with >1% probability
    .sort((a, b) => b.probability - a.probability)

  if (sortedEvents.length === 0) {
    return (
      <Box textAlign="center" py={4}>
        <Typography color="textSecondary" variant="body2">
          No event data available
        </Typography>
      </Box>
    )
  }

  const topEvent = sortedEvents[0]

  return (
    <Box>
      {/* Top Event Highlight */}
      <Box sx={{ mb: 3, p: 2, borderRadius: 2, backgroundColor: 'rgba(255, 255, 255, 0.05)' }}>
        <Typography variant="h6" gutterBottom>
          Primary Event
        </Typography>
        <Box display="flex" alignItems="center" gap={2}>
          <Chip 
            label={topEvent.config.label}
            sx={{ 
              backgroundColor: topEvent.config.color,
              color: 'white',
              fontWeight: 600
            }}
          />
          <Typography variant="h4" color={topEvent.config.color}>
            {(topEvent.probability * 100).toFixed(0)}%
          </Typography>
        </Box>
        <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
          Confidence level for this event type
        </Typography>
      </Box>

      {/* Event Distribution Bars */}
      <Box>
        <Typography variant="subtitle2" gutterBottom color="textSecondary">
          Event Breakdown
        </Typography>
        
        {sortedEvents.map((item, index) => (
          <Box key={item.event} sx={{ mb: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 500 }}>
                {item.config.label}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {(item.probability * 100).toFixed(1)}%
              </Typography>
            </Box>
            
            <LinearProgress
              variant="determinate"
              value={item.probability * 100}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: item.config.color,
                  borderRadius: 4,
                }
              }}
            />
          </Box>
        ))}
      </Box>

      {/* Event Type Legend */}
      <Box sx={{ mt: 3 }}>
        <Typography variant="caption" color="textSecondary" gutterBottom display="block">
          Event Types
        </Typography>
        <Box display="flex" flexWrap="wrap" gap={1}>
          {Object.entries(eventConfig).map(([event, config]) => (
            <Box key={event} display="flex" alignItems="center" gap={0.5}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: config.color,
                }}
              />
              <Typography variant="caption" color="textSecondary">
                {config.label}
              </Typography>
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  )
}

export default EventDistribution