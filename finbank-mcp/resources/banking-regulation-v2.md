# LipariBank Banking Regulation Guide

**Version:** 2.0  
**Status:** Example reference resource  
**Last reviewed:** 2026-01-15

## Scope

This guide summarizes internal expectations for safe and compliant retail banking operations. It is intended to help teams interpret common control requirements during product and service reviews.

## Account and payment operations

- Maintain accurate customer and account records.
- Validate payment instructions before execution and reject incomplete or unauthorized requests.
- Preserve transaction integrity: debit and credit legs must be processed atomically.
- Provide customers with timely, understandable information about balances, fees, and payment status.
- Protect sensitive data through least-privilege access, encryption, and audit logging.

## Operational risk

Critical services should have documented owners, monitoring, incident procedures, and recovery objectives. Changes affecting payments, authentication, or customer data require peer review and a recorded approval. Material incidents must be escalated to the responsible risk and compliance functions.

## Governance and evidence

Business and technology owners are responsible for periodic control checks. Evidence should include access reviews, reconciliation results, incident records, change approvals, and exception decisions. Exceptions require a named owner, an expiry date, and a compensating control where practical.

## Customer protection

Complaints must be logged, investigated, and answered within the applicable service level. Marketing and product disclosures must be clear, accurate, and consistent with the actual service offered.

This document is a simplified example for testing the `policy://banking-regulation` MCP resource and does not replace applicable law, supervisory guidance, or professional advice.
