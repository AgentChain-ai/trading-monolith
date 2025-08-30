import React from 'react'
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemText,
  Chip,
  Link,
  Avatar,
  Divider,
} from '@mui/material'
import {
  Article,
  Launch,
  TrendingUp,
  TrendingDown,
  TrendingFlat,
} from '@mui/icons-material'
import { EvidenceListProps } from '../types'

const EvidenceList: React.FC<EvidenceListProps> = ({ evidence }) => {
  const getSentimentIcon = (sentiment: number) => {
    if (sentiment > 0.1) return <TrendingUp color="success" fontSize="small" />
    if (sentiment < -0.1) return <TrendingDown color="error" fontSize="small" />
    return <TrendingFlat color="warning" fontSize="small" />
  }

  const getSentimentColor = (sentiment: number) => {
    if (sentiment > 0.1) return 'success.main'
    if (sentiment < -0.1) return 'error.main'
    return 'warning.main'
  }

  const getEventColor = (eventType: string) => {
    const colors: Record<string, string> = {
      'listing': '#4caf50',
      'partnership': '#2196f3', 
      'hack': '#f44336',
      'depeg': '#ff5722',
      'regulatory': '#ff9800',
      'funding': '#9c27b0',
      'tech': '#00bcd4',
      'market-note': '#607d8b',
      'op-ed': '#795548',
    }
    return colors[eventType] || '#9e9e9e'
  }

  if (!evidence || evidence.length === 0) {
    return (
      <Box textAlign="center" py={4}>
        <Typography color="textSecondary" variant="body2">
          No evidence articles available
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      <List sx={{ maxHeight: 600, overflow: 'auto' }}>
        {evidence.map((item, index) => (
          <React.Fragment key={index}>
            <ListItem alignItems="flex-start" sx={{ px: 0 }}>
              <Avatar
                sx={{ 
                  width: 32, 
                  height: 32, 
                  mr: 2,
                  backgroundColor: getEventColor(item.event_type),
                  fontSize: '0.75rem'
                }}
              >
                <Article fontSize="small" />
              </Avatar>
              
              <ListItemText
                primary={
                  <Box>
                    <Link
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      color="inherit"
                      underline="hover"
                      sx={{ 
                        fontWeight: 500,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.5,
                        mb: 1,
                        '&:hover': {
                          color: 'primary.main'
                        }
                      }}
                    >
                      {item.title}
                      <Launch fontSize="small" />
                    </Link>
                  </Box>
                }
                secondary={
                  <Box>
                    <Box display="flex" alignItems="center" gap={1} sx={{ mb: 1 }}>
                      <Chip
                        label={item.event_type.replace('-', ' ')}
                        size="small"
                        sx={{
                          backgroundColor: getEventColor(item.event_type),
                          color: 'white',
                          fontWeight: 500,
                          fontSize: '0.7rem',
                          height: 20,
                        }}
                      />
                      
                      <Box display="flex" alignItems="center" gap={0.5}>
                        {getSentimentIcon(item.sentiment)}
                        <Typography 
                          variant="caption" 
                          color={getSentimentColor(item.sentiment)}
                          sx={{ fontWeight: 500 }}
                        >
                          {item.sentiment > 0 ? '+' : ''}{item.sentiment.toFixed(2)}
                        </Typography>
                      </Box>
                      
                      <Typography variant="caption" color="textSecondary">
                        Weight: {item.weight.toFixed(2)}
                      </Typography>
                    </Box>
                  </Box>
                }
              />
            </ListItem>
            {index < evidence.length - 1 && <Divider variant="inset" component="li" />}
          </React.Fragment>
        ))}
      </List>
      
      {/* Summary */}
      <Box sx={{ mt: 2, p: 2, backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: 1 }}>
        <Typography variant="body2" color="textSecondary">
          {evidence.length} article{evidence.length !== 1 ? 's' : ''} analyzed • 
          {' '}Avg Weight: {(evidence.reduce((sum, item) => sum + item.weight, 0) / evidence.length).toFixed(2)} • 
          {' '}Avg Sentiment: {(evidence.reduce((sum, item) => sum + item.sentiment, 0) / evidence.length).toFixed(2)}
        </Typography>
      </Box>
    </Box>
  )
}

export default EvidenceList