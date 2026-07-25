# GitHub Issue: SSRF Hardening for Outbound URL Validation

## Title
Implement SSRF Protection for Agent Card Fetch and Health Check Endpoints

## Labels
- security
- enhancement
- backend

## Description

### Problem Statement
The registry currently fetches user-supplied URLs (specifically for agent cards and server health checks) without any Server-Side Request Forgery (SSRF) protection. While an `_is_safe_url()` guard already exists for SKILL.md fetches, this protection is not applied to other outbound HTTP requests. This creates a potential security vulnerability where an attacker could potentially force the registry to make requests to internal services or other unintended destinations.

### Proposed Solution
1. Promote the existing `_is_safe_url()` function into a shared utility
2. Apply this URL validation to agent card fetch and server health check paths
3. Add configuration support for an allowlist of trusted domains/IPs
4. Ensure backward compatibility by making the validation configurable

### User Stories
- As an operator running the gateway, I want to prevent SSRF attacks so that internal services remain protected
- As a downstream team registering MCP servers, I want to ensure my service integrations don't accidentally expose internal systems to potential abuse

### Acceptance Criteria
- [ ] Existing `_is_safe_url()` function is moved to a shared utilities module
- [ ] Agent card fetch endpoint validates URLs using the shared utility
- [ ] Server health check endpoint validates URLs using the shared utility
- [ ] Configuration supports an allowlist of trusted domains/IPs
- [ ] Backward compatibility is maintained through feature flags
- [ ] Comprehensive tests cover both positive and negative validation cases

### Out of Scope
- Modifying the existing SKILL.md fetch implementation (it already has protection)
- Changing the core registry architecture or data models
- Implementing client-side URL validation

### Dependencies
- Existing URL validation logic in the codebase

### Related Issues
- #1282
