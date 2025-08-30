import React, { useState } from 'react'
import {
  Button,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
  Typography,
  Box,
  Divider,
  Alert,
  Chip
} from '@mui/material'
import {
  ExpandMore,
  CheckCircle,
  Warning,
  Language
} from '@mui/icons-material'
import { useChainId, useSwitchChain, useAccount } from 'wagmi'
import { supportedChains, getChainConfig, isChainSupported } from '../config/appkit'

export const ChainSwitcher: React.FC = () => {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)
  const { isConnected } = useAccount()
  const chainId = useChainId()
  const { switchChain, isPending, error } = useSwitchChain()

  const currentChain = getChainConfig(chainId)
  const isUnsupportedChain = isConnected && !isChainSupported(chainId)

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleClose = () => {
    setAnchorEl(null)
  }

  const handleChainSwitch = (targetChainId: number) => {
    switchChain({ chainId: targetChainId })
    handleClose()
  }

  const getChainEmoji = (chainId: number) => {
    const emojiMap: Record<number, string> = {
      1: '⟠',      // Ethereum
      56: '💛',     // BSC
      137: '🟣',    // Polygon
      250: '🔵',    // Fantom
      42161: '🔹',  // Arbitrum
      10: '🔴',     // Optimism
      8453: '🔵',   // Base
      43114: '❄️'   // Avalanche
    }
    return emojiMap[chainId] || '🌐'
  }

  if (!isConnected) {
    return null
  }

  return (
    <Box>
      <Button
        onClick={handleClick}
        endIcon={<ExpandMore />}
        variant="outlined"
        size="small"
        disabled={isPending}
        color={isUnsupportedChain ? 'warning' : 'primary'}
        sx={{
          textTransform: 'none',
          minWidth: 'auto'
        }}
      >
        <Box display="flex" alignItems="center" gap={1}>
          <Typography component="span">
            {currentChain ? getChainEmoji(chainId) : '❌'}
          </Typography>
          <Typography variant="body2">
            {currentChain?.name || 'Unsupported'}
          </Typography>
          {isUnsupportedChain && (
            <Warning fontSize="small" color="warning" />
          )}
        </Box>
      </Button>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleClose}
        PaperProps={{
          sx: { minWidth: 200, maxWidth: 300 }
        }}
      >
        <Box px={2} py={1}>
          <Typography variant="subtitle2" color="text.secondary">
            Select Network
          </Typography>
        </Box>
        
        <Divider />

        {error && (
          <Box px={2} py={1}>
            <Alert severity="error" variant="outlined" sx={{ fontSize: '0.75rem' }}>
              {error.message}
            </Alert>
          </Box>
        )}

        {supportedChains.map((chain) => {
          const config = getChainConfig(chain.id)
          const isCurrentChain = chainId === chain.id
          
          return (
            <MenuItem
              key={chain.id}
              onClick={() => handleChainSwitch(chain.id)}
              disabled={isPending || isCurrentChain}
              sx={{
                py: 1.5,
                bgcolor: isCurrentChain ? 'action.selected' : 'transparent'
              }}
            >
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Box
                  sx={{
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    bgcolor: config?.color || '#gray',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.75rem'
                  }}
                >
                  {getChainEmoji(chain.id)}
                </Box>
              </ListItemIcon>
              
              <ListItemText
                primary={
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2">
                      {config?.name || chain.name}
                    </Typography>
                    {isCurrentChain && (
                      <CheckCircle fontSize="small" color="primary" />
                    )}
                  </Box>
                }
                secondary={
                  <Typography variant="caption" color="text.secondary">
                    {config?.symbol} • ID: {chain.id}
                  </Typography>
                }
              />
            </MenuItem>
          )
        })}

        <Divider />
        
        <Box px={2} py={1}>
          <Typography variant="caption" color="text.secondary">
            Switch between supported networks for multi-chain trading
          </Typography>
        </Box>
      </Menu>
    </Box>
  )
}

export default ChainSwitcher
