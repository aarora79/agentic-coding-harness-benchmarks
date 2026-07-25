# Low-Level Design: SSRF Hardening for Outbound URL Validation

*Created: 2026-07-25*
*Author: Claude*
*Status: Draft*

## Table of Contents
1. [Overview](#overview)
2. [Codebase Analysis](#codebase-analysis)
3. [Architecture](#architecture)
4. [Data Models](#data-models)
5. [API / CLI Design](#api--cli-design)
6. [Configuration Parameters](#configuration-parameters)
7. [New Dependencies](#new-dependencies)
8. [Implementation Details](#implementation-details)
9. [Observability](#observability)
10. [Scaling Considerations](#scaling-considerations)
11. [File Changes](#file-changes)
12. [Testing Strategy](#testing-strategy)
13. [Alternatives Considered](#alternatives-considered)
14. [Rollout Plan](#rollout-plan)

## Overview
### Problem Statement
The registry currently fetches user-supplied URLs (specifically for agent cards and server health checks) without any Server-Side Request Forgery (SSRF) protection on these pathways. While an `_is_safe_url()` guard already exists for SKILL.md fetches in the skill service, this protection is not applied to other outbound HTTP requests. This creates a potential security vulnerability where an attacker could potentially force the registry to make requests to internal services or other unintended destinations.

### Goals
- Promote the existing `_is_safe_url()` function into a shared utility module
- Apply URL validation to agent card fetch and server health check paths
- Add configuration support for an allowlist of trusted domains/IPs
- Maintain backward compatibility through feature flags
- Ensure comprehensive test coverage

### Non-Goals
- Modify the existing SKILL.md fetch implementation (it already has protection)
- Change the core registry architecture or data models
- Implement client-side URL validation

## Codebase Analysis

### Key Files Reviewed

| File/Directory | Purpose | Relevance to This Change |
|----------------|---------|--------------------------|
| `registry/services/skill_service.py` | Contains the existing `_is_safe_url()` function | Source of URL validation logic to promote |
| `registry/utils/url_utils.py` | URL handling utilities | Destination for promoted URL validation function |
| `registry/api/agent_routes.py` | Agent API endpoints | Contains agent card fetch endpoint needing protection |
| `registry/health/service.py` | Health check service | Contains server health check logic needing protection |
| `registry/core/config.py` | Application configuration | Will contain new configuration parameters |
| `tests/unit/services/test_skill_service_ssrf_allowlist.py` | SSRF tests | Model for testing the promoted function |

### Existing Patterns Identified
1. **Shared Utility Pattern**: The codebase follows a pattern of promoting common functionality to shared utility modules. The `registry/utils/` directory contains multiple utility modules.
   - Files: `url_utils.py`, `path_utils.py`, `request_utils.py`
   - How a future implementer should follow this: Place the promoted `_is_safe_url()` function in `registry/utils/url_utils.py` and import it where needed.

2. **Configuration Pattern**: The application uses Pydantic settings with environment variables for configuration.
   - Files: `registry/core/config.py`
   - How a future implementer should follow this: Add new configuration parameters to the Settings class following existing patterns.

3. **HTTP Client Pattern**: The codebase consistently uses `httpx.AsyncClient` for making HTTP requests with proper timeout handling.
   - Files: `registry/health/service.py`, `registry/services/skill_service.py`
   - How a future implementer should follow this: Apply URL validation before creating HTTP clients for outbound requests.

### Integration Points

| Component | Integration Type | Details |
|-----------|------------------|---------|
| Agent Card Fetch Endpoint | Uses | Located in `registry/api/agent_routes.py`, needs URL validation before making HTTP requests |
| Server Health Check Service | Uses | Located in `registry/health/service.py`, needs URL validation before making health check requests |
| Skill Service | Extends | Contains the original `_is_safe_url()` implementation that will be promoted |
| Settings | Depends on | Will need new configuration parameters for allowlist and feature flags |

### Constraints and Limitations Discovered
- **Backward Compatibility**: The change must be backward compatible and configurable, as existing deployments may rely on current behavior
- **Performance**: URL validation should not significantly impact the performance of health checks and agent card fetches
- **DNS Resolution**: The existing `_is_safe_url()` function performs DNS resolution which can be a performance bottleneck

## Architecture

### System Context Diagram
```
┌─────────────────┐        ┌─────────────────────┐        ┌────────────────────┐
│   User/MCP      │        │    Registry         │        │  External Servers  │
│    Client       │───────▶│                     │───────▶│   (Agent Cards,    │
│                 │        │ ┌─────────────────┐ │        │    Health Endpoints)│
└─────────────────┘        │ │Outbound URL     │ │        └────────────────────┘
                           │ │Validation       │ │
                           │ │(New Component)  │ │
                           │ └─────────────────┘ │
                           │          │          │
                           │          ▼          │
                           │ ┌─────────────────┐ │
                           │ │Agent Card Fetch │ │
                           │ │(Modified)       │ │
                           │ └─────────────────┘ │
                           │          │          │
                           │          ▼          │
                           │ ┌─────────────────┐ │
                           │ │Health Check     │ │
                           │ │Service (Modified)│ │
                           │ └─────────────────┘ │
                           └─────────────────────┘
```

### Sequence Diagram
```
User->Registry: Request agent health check
Registry->URL Validator: Validate agent URL
URL Validator-->Registry: URL is safe/unsafe
alt URL is safe
Registry->External Server: Fetch agent card / check health
External Server-->Registry: Response
Registry->User: Return health check result
else URL is unsafe
Registry->User: Return error (400 Bad Request)
end
```

### Component Diagram
```
┌─────────────────────────────────────────────────────────────────────┐
│                      Registry Application                           │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐ │
│  │ Agent Routes    │    │ Health Service  │    │ Skill Service   │ │
│  │ (Modified)      │    │ (Modified)      │    │ (Source of      │ │
│  └─────────────────┘    └─────────────────┘    │ _is_safe_url)   │ │
│           │                       │             └─────────────────┘ │
│           ▼                       ▼                      │          │
│  ┌─────────────────────────────────────────────────────┐  │          │
│  │           Shared URL Validation Utility             │  │          │
│  │         (Promoted from skill_service)               │◀─┘          │
│  └─────────────────────────────────────────────────────┘             │
│                                 │                                   │
│                                 ▼                                   │
│  ┌─────────────────────────────────────────────────────┐             │
│  │                   Settings (Modified)               │             │
│  │              (New allowlist configuration)          │             │
│  └─────────────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Models

### New Models
No new models needed for this change.

### Model Changes
No existing model changes required, but we'll be validating URL fields in existing models.

## API / CLI Design

### New Endpoints / Commands
No new endpoints or commands needed.

### Modified Endpoints
**Endpoint:** `POST /api/agents/{path:path}/health`
**Description:** Agent health check endpoint that fetches agent card from `/.well-known/agent-card.json`

**Changes:** Add URL validation before making outbound HTTP requests to fetch agent card.

**Error Cases:**
- 400 Bad Request: When the agent URL fails SSRF validation

**Endpoint:** Background health checks in `HealthService`
**Description:** Periodic health checks performed on registered MCP servers

**Changes:** Add URL validation before making outbound HTTP requests for server health checks.

**Error Cases:**
- Skipped health check: When a server URL fails SSRF validation (logged but doesn't return HTTP error)

## Configuration Parameters

### New Environment Variables

| Variable Name | Type | Default | Required | Description |
|---------------|------|---------|----------|-------------|
| `SSRF_PROTECTION_ENABLED` | bool | `True` | No | Enable/disable SSRF protection for agent card fetch and health check endpoints |
| `SSRF_ALLOWLIST_HOSTS` | str | `""` | No | Comma-separated list of additional trusted hosts that bypass SSRF checks |

### Settings / Config Class Updates
```python
ssrf_protection_enabled: bool = Field(
    default=True,
    description="Enable/disable SSRF protection for agent card fetch and health check endpoints"
)

ssrf_allowlist_hosts: str = Field(
    default="",
    description="Comma-separated list of additional trusted hosts that bypass SSRF checks"
)
```

### Deployment Surface Checklist
List every surface where this parameter must appear (`.env.example`, `docker-compose.yml`, Terraform vars, Helm values, etc.) so an implementer can tick them off later.
- [ ] `.env.example` - Add new environment variables
- [ ] `docker-compose.yml` - Add new environment variables to service definitions
- [ ] Helm charts - Add new values to values.yaml and templates
- [ ] Terraform configurations - Add new variables to module definitions

## New Dependencies

This change uses only existing dependencies.

## Implementation Details

### Step-by-Step Plan (for a future implementer)

#### Step 1: Promote `_is_safe_url` to shared utility
**File:** `registry/utils/url_utils.py`
**Lines:** New function additions

```python
import ipaddress
import logging
import socket
from functools import lru_cache
from urllib.parse import urlparse

from ..core.config import settings

logger = logging.getLogger(__name__)

# Built-in trusted domains that skip IP validation (SSRF protection allowlist).
# Additional hosts can be added via settings.ssrf_allowlist_hosts
_DEFAULT_SSRF_TRUSTED_DOMAINS: frozenset = frozenset({
    "github.com",
    "gitlab.com",
    "raw.githubusercontent.com",
    "bitbucket.org",
})

@lru_cache(maxsize=1)
def _ssrf_trusted_domains() -> frozenset[str]:
    """Return SSRF allowlist: built-in defaults plus configured hosts.

    Cached because settings are immutable per-process.
    """
    extra_raw = settings.ssrf_allowlist_hosts or ""
    extra = frozenset(h.strip().lower() for h in extra_raw.split(",") if h.strip())
    return _DEFAULT_SSRF_TRUSTED_DOMAINS | extra

def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, or link-local.

    Args:
        ip_str: IP address string to check

    Returns:
        True if the IP is private/loopback/link-local, False otherwise
    """
    try:
        ip = ipaddress.ip_address(ip_str)

        # Check for private, loopback, link-local, or reserved addresses
        if ip.is_private:
            return True
        if ip.is_loopback:
            return True
        if ip.is_link_local:
            return True
        if ip.is_reserved:
            return True

        # Check for cloud metadata endpoint (169.254.169.254)
        if ip_str == "169.254.169.254":
            return True

        return False
    except ValueError:
        # Invalid IP address format
        logger.warning(f"SSRF protection: Invalid IP address format '{ip_str}'")
        return False

def is_safe_url(url: str) -> bool:
    """Check if a URL is safe to fetch (SSRF protection).

    This function validates that a URL:
    1. Uses http or https scheme
    2. Does not resolve to a private/loopback/link-local IP address
    3. Does not target cloud metadata endpoints

    Trusted domains (built-in defaults plus any host configured via
    settings.ssrf_allowlist_hosts) skip the IP check.

    Args:
        url: URL to validate

    Returns:
        True if the URL is safe to fetch, False otherwise
    """
    # If SSRF protection is disabled, all URLs are considered safe
    if not settings.ssrf_protection_enabled:
        return True

    try:
        parsed = urlparse(url)

        # Check scheme - only allow http and https
        if parsed.scheme not in ("http", "https"):
            logger.warning(f"SSRF protection: Blocked URL with scheme '{parsed.scheme}'")
            return False

        hostname = parsed.hostname
        if not hostname:
            logger.warning("SSRF protection: URL has no hostname")
            return False

        # Check if hostname is in trusted domains allowlist
        hostname_lower = hostname.lower()
        if hostname_lower in _ssrf_trusted_domains():
            logger.debug(f"SSRF protection: Trusted domain '{hostname_lower}'")
            return True

        # Resolve hostname to IP addresses
        try:
            addr_info = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                proto=socket.IPPROTO_TCP,
            )
        except socket.gaierror as e:
            logger.warning(f"SSRF protection: Failed to resolve hostname '{hostname}': {e}")
            return False

        # Check all resolved IP addresses
        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip_address = sockaddr[0]
            if _is_private_ip(ip_address):
                logger.warning(
                    f"SSRF protection: Blocked URL resolving to private IP "
                    f"'{ip_address}' for hostname '{hostname}'"
                )
                return False

        return True

    except Exception as e:
        logger.warning(f"SSRF protection: Error validating URL: {e}")
        return False
```

#### Step 2: Update agent card fetch endpoint
**File:** `registry/api/agent_routes.py`
**Lines:** Around line 900+ in the `check_agent_health` function

Before making HTTP requests in the health check function, add URL validation:

```python
# Import at the top of the file
from ..utils.url_utils import is_safe_url

# In the check_agent_health function, before making HTTP requests:
for url in health_urls:
    # Validate URL before making request
    if not is_safe_url(url):
        logger.warning(f"SSRF protection: Blocked unsafe URL '{url}' in agent health check")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent URL failed SSRF validation",
        )

    health_check_url = url
    # ... rest of existing code
```

#### Step 3: Update server health check service
**File:** `registry/health/service.py`
**Lines:** In the `_check_server_endpoint_transport_aware` function

Before making HTTP requests in the server health check function, add URL validation:

```python
# Import at the top of the file
from ..utils.url_utils import is_safe_url

# In the _check_server_endpoint_transport_aware function, before making HTTP requests:
if not proxy_pass_url:
    return False, HealthStatus.UNHEALTHY_MISSING_PROXY_URL

# Validate URL before making request
if not is_safe_url(proxy_pass_url):
    logger.warning(f"SSRF protection: Blocked unsafe server URL '{proxy_pass_url}'")
    return False, "unhealthy: blocked by SSRF protection"

# ... rest of existing code
```

### Error Handling
- When a URL fails validation, log a warning with details about why it was blocked
- For agent health checks, return a 400 Bad Request error to the client
- For server health checks, mark the server as unhealthy with an appropriate status message
- Handle DNS resolution errors gracefully and treat them as unsafe URLs

### Logging
- Log URL validation failures at WARNING level with details about the blocked URL
- Log trusted domain accesses at DEBUG level
- Include contextual information such as agent path or server name when possible

## Observability
### Tracing / Metrics / Logging Points
1. **Log Events:**
   - URL validation failures (WARNING level)
   - Trusted domain accesses (DEBUG level)
   - Configuration changes (INFO level)

2. **Metrics:**
   - Counter for blocked URLs due to SSRF protection
   - Counter for successful URL validations
   - Histogram for URL validation duration

## Scaling Considerations
- **Current Load Assumptions:** The health check service processes servers in batches, and agent health checks are user-initiated
- **Performance Impact:** DNS resolution in `_is_safe_url` could be a bottleneck; consider caching IP resolutions
- **Horizontal Scaling:** URL validation doesn't introduce state, so it scales well with multiple instances
- **Caching Strategy:** The `_ssrf_trusted_domains` function is already cached, but IP resolution is not cached

## File Changes

### New Files
No new files needed.

### Modified Files

| File Path | Lines | Change Description |
|-----------|-------|--------------------|
| `registry/utils/url_utils.py` | New functions | Add `is_safe_url` and supporting functions |
| `registry/api/agent_routes.py` | ~900 | Add URL validation to agent health check endpoint |
| `registry/health/service.py` | Various | Add URL validation to server health check service |
| `registry/core/config.py` | New fields | Add SSRF configuration parameters |
| `tests/unit/test_agent_routes.py` | New tests | Add tests for URL validation in agent health checks |
| `tests/unit/health/test_service.py` | New tests | Add tests for URL validation in server health checks |

### Estimated Lines of Code

| Category | Lines |
|----------|-------|
| New code | ~150 |
| New tests | ~100 |
| Modified code | ~50 |
| **Total** | **~300** |

## Testing Strategy
See `testing.md` for the full testing plan.

## Alternatives Considered

### Alternative 1: Use a Third-Party SSRF Library
**Description:** Use an existing library like `ssrf-filter` or similar packages
**Pros:**
- Proven implementation
- Less code to maintain
**Cons:**
- Additional dependency
- May not fit existing code patterns
- Less control over validation logic
**Why Rejected:** The existing `_is_safe_url` implementation is already robust and fits the codebase patterns well.

### Alternative 2: Implement Validation at the HTTP Client Level
**Description:** Add validation directly to the HTTP client wrapper
**Pros:**
- Centralized protection
- Protects all HTTP requests automatically
**Cons:**
- Could break legitimate internal requests
- Harder to configure per-endpoint
**Why Rejected:** More targeted protection at specific endpoints provides better control and configurability.

### Comparison Matrix

| Criteria | Chosen Approach | Alt 1 (Third-Party) | Alt 2 (HTTP Client) |
|----------|----------------|---------------------|---------------------|
| Complexity | Low | Low | Medium |
| Control | High | Medium | High |
| Dependencies | None | Additional | None |
| Fit with Existing Code | Excellent | Good | Fair |

## Rollout Plan
- Phase 1: Implementation (out of scope for this skill)
- Phase 2: Testing
- Phase 3: Deployment with feature flag enabled by default

## Open Questions
- Should we cache IP address resolutions to improve performance?
- Do we need to support IPv6 private address ranges?

## References
- OWASP SSRF Prevention Cheat Sheet
- Existing `_is_safe_url` implementation in `registry/services/skill_service.py`
- A2A Agent Specification for health check endpoints
