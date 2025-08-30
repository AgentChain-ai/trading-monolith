import React from 'react'
import { Button, Box, Chip } from '@mui/material'
import { AccountBalanceWallet } from '@mui/icons-material'
import { useAccount, useChainId, useDisconnect } from 'wagmi'
import { getChainConfig } from '../config/appkit'
import { modal } from '../config/appkit'

interface WalletButtonProps {
  variant?: 'contained' | 'outlined' | 'text'
  size?: 'small' | 'medium' | 'large'
  fullWidth?: boolean
}

export const WalletButton: React.FC<WalletButtonProps> = ({ 
  variant = 'contained', 
  size = 'medium',
  fullWidth = false 
}) => {
  const { address, isConnected } = useAccount()
  const { disconnect } = useDisconnect()
  const chainId = useChainId()

  const currentChain = getChainConfig(chainId)

  const formatAddress = (addr: string) => {
    return `${addr.slice(0, 6)}...${addr.slice(-4)}`
  }

  const openModal = () => {
    modal.open()
  }

  const handleDisconnect = () => {
    disconnect()
  }

  if (isConnected && address) {
    return (
      <Box display="flex" alignItems="center" gap={1}>
        {currentChain && (
          <Chip
            label={currentChain.name}
            size="small"
            sx={{
              bgcolor: currentChain.color || '#gray',
              color: 'white',
              fontWeight: 'bold'
            }}
          />
        )}
        
        <Button
          variant={variant}
          size={size}
          onClick={handleDisconnect}
          startIcon={<AccountBalanceWallet />}
          fullWidth={fullWidth}
          sx={{ color: 'white' }}
        >
          {formatAddress(address)}
        </Button>
      </Box>
    )
  }

  return (
    <Button
      variant={variant}
      size={size}
      fullWidth={fullWidth}
      onClick={openModal}
      startIcon={<AccountBalanceWallet />}
      sx={{ color: 'white' }}
    >
      Connect Wallet
    </Button>
  )
}

export default WalletButton
