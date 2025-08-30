# MCP Server Troubleshooting Guide

This guide helps diagnose and resolve issues with the Search-Scrape MCP Server integration in the NTM Trading Engine.

## Quick Diagnostics

### Check System Status
```bash
# Check circuit breaker status
curl http://localhost:8000/admin/circuit-breakers

# Test MCP connection
curl http://localhost:8000/admin/test-mcp

# Get service health
curl http://localhost:8000/admin/service-health
```

### Reset Circuit Breakers
```bash
# Reset all circuit breakers
curl -X POST http://localhost:8000/admin/circuit-breakers/reset-all

# Reset specific circuit breaker
curl -X POST http://localhost:8000/admin/circuit-breakers/mcp_scrape/reset
```

## Common Issues and Solutions

### 1. Circuit Breaker in OPEN State

**Symptoms:**
- Logs showing "Circuit breaker is now OPEN (failures: X)"
- MCP operations failing immediately without attempting connection
- Error messages about circuit breaker being open

**Causes:**
- Multiple consecutive failures to MCP server
- Network connectivity issues
- MCP server overloaded or returning errors

**Solutions:**
1. **Immediate Fix:** Reset circuit breaker manually
   ```bash
   curl -X POST http://localhost:8000/admin/circuit-breakers/reset-all
   ```

2. **Root Cause Analysis:** Check MCP server status
   ```bash
   # Test direct connection to MCP server
   curl -X POST https://scraper.agentchain.trade//search \
     -H "Content-Type: application/json" \
     -d '{"query": "test"}'
   ```

3. **Long-term Fix:** Monitor circuit breaker settings in [`backend/app/services/mcp_client.py`](backend/app/services/mcp_client.py:65-85)

### 2. Scrape Operations Timing Out

**Symptoms:**
- Scrape operations taking >90 seconds
- "Server disconnected without sending a response" errors
- Large response payloads (>2MB) failing

**Root Cause:**
The MCP server's scrape endpoint returns very large responses (2.8MB+) and can take 5-10 seconds.

**Solutions Applied:**
- ✅ Increased scrape timeout to 90 seconds
- ✅ Separate circuit breakers for search vs scrape operations
- ✅ More tolerant failure threshold for scrape operations (8 failures vs 5)
- ✅ Longer recovery timeout for scrape circuit breaker (3 minutes vs 1 minute)

**Configuration in [`backend/app/services/mcp_client.py`](backend/app/services/mcp_client.py:70-90):**
```python
self.scrape_timeout = 90.0  # 90 seconds for large responses
self.scrape_circuit_breaker = get_circuit_breaker(
    "mcp_scrape", 
    CircuitBreakerConfig(
        failure_threshold=8,  # More tolerant
        timeout=180,  # 3 minutes recovery time
    )
)
```

### 3. Empty Health Check Response

**Symptoms:**
- Health endpoint `/health` returns empty response or HTTP 52 error
- "Empty reply from server" messages

**Root Cause:**
The MCP server may not implement a proper health endpoint.

**Workaround:**
Use the search endpoint for health checks since it's more reliable:
```python
async def health_check(self) -> bool:
    try:
        results = await self.search("health check")
        return True  # If we get any response, server is alive
    except:
        return False
```

### 4. Rate Limiting Issues

**Symptoms:**
- 429 Too Many Requests errors
- Delayed responses from MCP server

**Current Rate Limits:**
- MCP service: 5 requests/second, burst of 10
- Search operations: More frequent, smaller responses
- Scrape operations: Less frequent, larger responses

**Solutions:**
1. **Monitor rate limiting:** Check [`backend/app/utils/resilience.py`](backend/app/utils/resilience.py:328-332)
2. **Adjust if needed:** Modify rate limits based on server capacity
3. **Use cache effectively:** Leverage L1/L2/L3 caching strategy

### 5. Network Connectivity Issues

**Symptoms:**
- Connection refused errors
- DNS resolution failures
- Intermittent connectivity

**Diagnostics:**
```bash
# Test network connectivity
ping 3.110.206.240

# Test port connectivity
telnet 3.110.206.240 5001

# Test HTTP connectivity
curl -v https://scraper.agentchain.trade//health
```

**Solutions:**
1. **Check firewall rules**
2. **Verify DNS resolution**
3. **Test from different network locations**

## Monitoring and Alerting

### Key Metrics to Watch
1. **Circuit Breaker State Changes**
   - CLOSED → OPEN: Service degradation
   - OPEN → HALF_OPEN: Recovery attempt
   - HALF_OPEN → CLOSED: Full recovery

2. **Response Times**
   - Search: Should be <5 seconds
   - Scrape: Can be up to 90 seconds
   - Trend increases indicate server stress

3. **Error Rates**
   - <5% error rate is normal
   - >20% indicates serious issues
   - 100% means service is down

4. **Cache Hit Rates**
   - High cache hits reduce server load
   - Low hits may indicate cache expiry issues

### Log Patterns to Monitor

**Success Patterns:**
```
INFO: Search successful for query: [query]
INFO: Scrape successful for URL: [url] (content length: X, response size: Y chars)
INFO: Using cached [search_results|scrape_result] for [identifier]
```

**Warning Patterns:**
```
WARNING: [Operation] attempt [N] failed for [identifier]: [error]
WARNING: Circuit breaker is now OPEN (failures: N)
WARNING: No fallback available for [operation]: [identifier]
```

**Error Patterns:**
```
ERROR: All [search|scrape] attempts failed for [identifier]
ERROR: [Operation] failed for [identifier]: [error]
ERROR: Circuit breaker error: [details]
```

## Configuration Tuning

### Circuit Breaker Settings

**Conservative (Production):**
```python
# For critical production systems
CircuitBreakerConfig(
    failure_threshold=10,  # Allow more failures
    timeout=300,          # 5 minute recovery
)
```

**Aggressive (Development):**
```python
# For faster iteration in development
CircuitBreakerConfig(
    failure_threshold=3,   # Fail fast
    timeout=60,           # 1 minute recovery
)
```

### Timeout Settings

**For Slow Networks:**
```python
self.search_timeout = 45.0   # Increase from 30s
self.scrape_timeout = 120.0  # Increase from 90s
```

**For Fast Networks:**
```python
self.search_timeout = 15.0   # Decrease from 30s
self.scrape_timeout = 60.0   # Decrease from 90s
```

### Retry Configuration

**For High Availability:**
```python
RetryConfig(
    max_attempts=5,      # More attempts
    base_delay=2.0,      # Longer delays
    max_delay=30.0,      # Higher max delay
)
```

**For Fast Failure:**
```python
RetryConfig(
    max_attempts=2,      # Fewer attempts
    base_delay=0.5,      # Shorter delays
    max_delay=5.0,       # Lower max delay
)
```

## Emergency Procedures

### Complete MCP Server Failure

1. **Immediate Response:**
   ```bash
   # Reset all circuit breakers
   curl -X POST http://localhost:8000/admin/circuit-breakers/reset-all
   
   # Clear cache to force fresh attempts
   curl -X POST http://localhost:8000/admin/cache/clear
   ```

2. **Verify Cache Coverage:**
   ```bash
   # Check what's available in cache
   curl http://localhost:8000/admin/cache-status
   ```

3. **Enable Cache-Only Mode** (if implemented):
   - System will serve from L1/L2/L3 cache
   - New requests will fail but existing data remains accessible

### Partial Service Degradation

1. **Check Circuit Breaker Status:**
   ```bash
   curl http://localhost:8000/admin/circuit-breakers
   ```

2. **Reset Specific Service:**
   ```bash
   # If only scrape is failing
   curl -X POST http://localhost:8000/admin/circuit-breakers/mcp_scrape/reset
   
   # If only search is failing  
   curl -X POST http://localhost:8000/admin/circuit-breakers/mcp_search/reset
   ```

3. **Test Individual Operations:**
   ```bash
   curl http://localhost:8000/admin/test-mcp
   ```

## Best Practices

### Development
- Always test with realistic data volumes
- Monitor circuit breaker state during development
- Use debug logging to understand retry patterns
- Test both success and failure scenarios

### Production
- Set up monitoring for circuit breaker state changes
- Configure alerts for extended OPEN states
- Regularly review cache hit rates and expiry policies
- Monitor response times and adjust timeouts accordingly

### Deployment
- Gradually increase traffic after deployments
- Monitor error rates for 24 hours after changes
- Keep rollback procedures ready for circuit breaker configuration
- Test MCP connectivity before full deployment

## Support and Escalation

### Internal Steps
1. Check circuit breaker status
2. Review recent logs for error patterns
3. Test MCP server connectivity directly
4. Reset circuit breakers if appropriate
5. Monitor recovery progress

### External Escalation
If MCP server issues persist:
1. Document error patterns and timing
2. Capture network diagnostics
3. Contact MCP server infrastructure team
4. Provide specific endpoint and response details

### Recovery Verification
After resolving issues:
1. ✅ Circuit breakers return to CLOSED state
2. ✅ Response times return to normal ranges
3. ✅ Error rates drop below 5%
4. ✅ Cache hit rates stabilize
5. ✅ End-to-end ingestion pipeline works
6. ✅ Trading thesis generation resumes normal operation

---

This troubleshooting guide should be updated as new issues are discovered and resolved. For questions or updates, refer to the development team.