import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { Box, Typography, useTheme } from '@mui/material'
import { NarrativeChartProps, ChartDataPoint } from '../types'

const NarrativeChart: React.FC<NarrativeChartProps> = ({ buckets, height = 400 }) => {
  const theme = useTheme()

  // Transform buckets data for chart
  const chartData: ChartDataPoint[] = buckets.map(bucket => ({
    timestamp: new Date(bucket.bucket_ts).toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit' 
    }),
    narrative_heat: bucket.narrative_heat || 0,
    positive_heat: bucket.positive_heat || 0,
    negative_heat: -(bucket.negative_heat || 0), // Negative for visual separation
    hype_velocity: bucket.hype_velocity || 0,
    consensus: (bucket.consensus || 0) * 5, // Scale for visibility
    risk_polarity: bucket.risk_polarity || 0,
  }))

  if (chartData.length === 0) {
    return (
      <Box 
        display="flex" 
        alignItems="center" 
        justifyContent="center" 
        height={height}
        sx={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderRadius: 1 }}
      >
        <Typography color="textSecondary">
          No data available for chart
        </Typography>
      </Box>
    )
  }

  return (
    <Box sx={{ width: '100%', height, display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ width: '100%', height: height - 60, minHeight: height - 60 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={chartData}
            margin={{
              top: 10,
              right: 40,
              left: 30,
              bottom: 20,
            }}
          >
          <CartesianGrid 
            strokeDasharray="3 3" 
            stroke={theme.palette.divider}
            opacity={0.3}
          />
          <XAxis 
            dataKey="timestamp" 
            stroke={theme.palette.text.secondary}
            fontSize={12}
            tick={{ fill: theme.palette.text.secondary }}
          />
          <YAxis 
            stroke={theme.palette.text.secondary}
            fontSize={12}
            tick={{ fill: theme.palette.text.secondary }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: '8px',
              color: theme.palette.text.primary,
            }}
            labelStyle={{ color: theme.palette.text.primary }}
            formatter={(value: number, name: string) => [
              typeof value === 'number' ? value.toFixed(3) : value,
              name.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())
            ]}
          />
          <Legend
            wrapperStyle={{
              color: theme.palette.text.secondary,
              paddingTop: '10px'
            }}
            height={36}
          />
          
          {/* Reference line at zero */}
          <ReferenceLine 
            y={0} 
            stroke={theme.palette.divider} 
            strokeDasharray="2 2"
            opacity={0.5}
          />
          
          {/* Main narrative heat line */}
          <Line
            type="monotone"
            dataKey="narrative_heat"
            stroke={theme.palette.primary.main}
            strokeWidth={3}
            dot={{ fill: theme.palette.primary.main, strokeWidth: 2, r: 4 }}
            activeDot={{ r: 6, fill: theme.palette.primary.main }}
            name="Narrative Heat"
          />
          
          {/* Positive heat */}
          <Line
            type="monotone"
            dataKey="positive_heat"
            stroke={theme.palette.success.main}
            strokeWidth={2}
            dot={false}
            strokeDasharray="5 5"
            name="Positive Heat"
          />
          
          {/* Negative heat */}
          <Line
            type="monotone"
            dataKey="negative_heat"
            stroke={theme.palette.error.main}
            strokeWidth={2}
            dot={false}
            strokeDasharray="5 5"
            name="Negative Heat"
          />
          
          {/* Hype velocity */}
          <Line
            type="monotone"
            dataKey="hype_velocity"
            stroke={theme.palette.warning.main}
            strokeWidth={2}
            dot={false}
            opacity={0.7}
            name="Hype Velocity"
          />
          
          {/* Consensus (scaled) */}
          <Line
            type="monotone"
            dataKey="consensus"
            stroke={theme.palette.info.main}
            strokeWidth={1}
            dot={false}
            opacity={0.5}
            name="Consensus (x5)"
          />
          </LineChart>
        </ResponsiveContainer>
      </Box>
      
      {/* Enhanced Chart Legend with better spacing */}
      <Box sx={{
        mt: 1,
        pt: 1,
        display: 'flex',
        flexWrap: 'wrap',
        gap: { xs: 1, sm: 2 },
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: 40,
        borderTop: `1px solid ${theme.palette.divider}`,
        backgroundColor: 'rgba(255, 255, 255, 0.02)'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{
            width: 12,
            height: 3,
            backgroundColor: theme.palette.primary.main,
            borderRadius: '2px'
          }} />
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: '0.75rem' }}>
            Narrative Heat
          </Typography>
        </Box>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{
            width: 12,
            height: 2,
            backgroundColor: theme.palette.success.main,
            borderRadius: '1px',
            opacity: 0.7,
            border: `1px dashed ${theme.palette.success.main}`
          }} />
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: '0.75rem' }}>
            Positive Heat
          </Typography>
        </Box>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{
            width: 12,
            height: 2,
            backgroundColor: theme.palette.error.main,
            borderRadius: '1px',
            opacity: 0.7,
            border: `1px dashed ${theme.palette.error.main}`
          }} />
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: '0.75rem' }}>
            Negative Heat
          </Typography>
        </Box>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{
            width: 12,
            height: 2,
            backgroundColor: theme.palette.warning.main,
            borderRadius: '1px',
            opacity: 0.7
          }} />
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: '0.75rem' }}>
            Hype Velocity
          </Typography>
        </Box>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{
            width: 12,
            height: 2,
            backgroundColor: theme.palette.info.main,
            borderRadius: '1px',
            opacity: 0.5
          }} />
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: '0.75rem' }}>
            Consensus (×5)
          </Typography>
        </Box>
      </Box>
    </Box>
  )
}

export default NarrativeChart