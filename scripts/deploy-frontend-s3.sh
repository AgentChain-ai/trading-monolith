#!/bin/bash

# AgentChain.Trade - S3 Frontend Deployment Script
# This script builds and deploys the frontend to AWS S3 + CloudFront

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (set these environment variables)
S3_BUCKET="${S3_BUCKET:-agentchain-trade-frontend}"
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID}"
AWS_REGION="${AWS_REGION:-us-east-1}"
DOMAIN_NAME="${DOMAIN_NAME:-demo.agentchain.trade}"

echo -e "${BLUE}🚀 AgentChain.Trade - S3 Frontend Deployment${NC}"
echo -e "${BLUE}================================================${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed. Please install it first.${NC}"
    echo "Visit: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured. Please run 'aws configure'${NC}"
    exit 1
fi

echo -e "${GREEN}✅ AWS CLI configured${NC}"

# Check if S3 bucket exists
if ! aws s3 ls "s3://$S3_BUCKET" &> /dev/null; then
    echo -e "${YELLOW}⚠️  S3 bucket doesn't exist. Creating bucket: $S3_BUCKET${NC}"
    
    # Create bucket
    if [ "$AWS_REGION" = "us-east-1" ]; then
        aws s3 mb "s3://$S3_BUCKET"
    else
        aws s3 mb "s3://$S3_BUCKET" --region "$AWS_REGION"
    fi
    
    # Configure bucket for static website hosting
    aws s3 website "s3://$S3_BUCKET" --index-document index.html --error-document index.html
    
    # Set bucket policy for public read access
    cat > /tmp/bucket-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::$S3_BUCKET/*"
        }
    ]
}
EOF
    
    aws s3api put-bucket-policy --bucket "$S3_BUCKET" --policy file:///tmp/bucket-policy.json
    rm /tmp/bucket-policy.json
    
    echo -e "${GREEN}✅ S3 bucket created and configured${NC}"
else
    echo -e "${GREEN}✅ S3 bucket exists: $S3_BUCKET${NC}"
fi

# Navigate to frontend directory
cd "$(dirname "$0")/../frontend"

echo -e "${YELLOW}📦 Installing dependencies...${NC}"
npm ci

echo -e "${YELLOW}🏗️  Building frontend for production...${NC}"

# Set production environment variables for build
export REACT_APP_API_URL="https://api.${DOMAIN_NAME}/api/v1"
export REACT_APP_MICROSERVICE_URL="https://gasless.${DOMAIN_NAME}"

npm run build

echo -e "${GREEN}✅ Frontend built successfully${NC}"

echo -e "${YELLOW}📤 Uploading to S3...${NC}"

# Sync build to S3 with proper cache headers
aws s3 sync dist/ "s3://$S3_BUCKET" \
    --delete \
    --cache-control "public, max-age=31536000" \
    --exclude "*.html" \
    --exclude "service-worker.js"

# Upload HTML files with no cache
aws s3 sync dist/ "s3://$S3_BUCKET" \
    --cache-control "no-cache, no-store, must-revalidate" \
    --include "*.html" \
    --include "service-worker.js"

echo -e "${GREEN}✅ Files uploaded to S3${NC}"

# Invalidate CloudFront if distribution ID is provided
if [ -n "$CLOUDFRONT_DISTRIBUTION_ID" ]; then
    echo -e "${YELLOW}🔄 Invalidating CloudFront cache...${NC}"
    aws cloudfront create-invalidation \
        --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
        --paths "/*" > /dev/null
    echo -e "${GREEN}✅ CloudFront cache invalidated${NC}"
fi

echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}🎉 Frontend deployment complete!${NC}"
echo -e "${BLUE}S3 Website URL:${NC} http://$S3_BUCKET.s3-website-$AWS_REGION.amazonaws.com"

if [ -n "$DOMAIN_NAME" ]; then
    echo -e "${BLUE}Custom Domain:${NC} https://$DOMAIN_NAME"
fi

echo -e "${YELLOW}📝 Note: Make sure your backend API allows CORS from the frontend domain${NC}"
