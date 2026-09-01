# Code Review Suite — Run `5cced9f2-bb6f-4fca-8237-7771f851a3f0`

**Elapsed**: 205.4s · **Tokens**: 0 · **Cost**: $0.000

---

## code-reviewer-banking-domain
_Review di dominio banking_

- **[HIGH]** `src/main/java/com/lipari/bank/movement/MovementController.java:19` — Breaking API change: endpoint path changed from `/transfer` to `/transfers` without versioning strategy. Existing clients calling the old URL will receive 404. For banking APIs this is critical — payment integrations may fail silently.
  - **Fix**: Use path versioning (`/api/v1/transfers`) or maintain backward compatibility with both paths during deprecation period. Add `@Deprecated` on old endpoint and log warnings when it's hit.

## security-reviewer
_OWASP + Spring Security_

✅ OK no findings

## performance-reviewer
_N+1, blocking I/O, pool tuning_

✅ OK no findings

## rest-contract-reviewer
_DTO + status code + OpenAPI_

- **[HIGH]** `src/main/java/com/lipari/bank/movement/MovementController.java:19` — POST /transfer returns 200 instead of 201. Resource creation (transfer) should return 201 Created with Location header pointing to the new resource.
  - **Fix**: Return ResponseEntity.status(HttpStatus.CREATED).location(URI.create('/api/movements/' + response.getTransferId())).body(response)
- **[HIGH]** `src/main/java/com/lipari/bank/movement/MovementController.java:24` — GET /api/movements returns unbounded list with no pagination. Anti-pattern: entire account history returned in a single response. Large accounts will cause OOM / slow response.
  - **Fix**: Accept Pageable parameters (@PageableDefault(size=20) Pageable pageable), return Page<Movement> instead of List<Movement>.
- **[HIGH]** `src/main/java/com/lipari/bank/movement/MovementController.java:19` — POST /transfer lacks idempotency support. Money transfer endpoint without Idempotency-Key header risks double-debit on client retry after network timeout.
  - **Fix**: Accept @RequestHeader(required=false) String idempotencyKey, persist + check uniqueness before executing transfer.
- **[HIGH]** `src/main/java/com/lipari/bank/movement/MovementController.java:17` — No versioning in API path. Base path is /api/movements with no version prefix. Breaking changes will be indistinguishiable from non-breaking.
  - **Fix**: Change @RequestMapping to /api/v1/movements (path-based versioning).
- **[HIGH]** `src/main/java/com/lipari/bank/movement/MovementController.java:17` — No OpenAPI annotations on any endpoint. Missing @Operation, @ApiResponse, @Parameter — no auto-generated API documentation.
  - **Fix**: Add @Tag(name='Movements'), @Operation(summary='...'), @ApiResponse(responseCode='201', description='...'), @ApiResponse(responseCode='400', description='...') to all methods.
- **[MEDIUM]** `src/main/java/com/lipari/bank/common/GlobalExceptionHandler.java:10` — Error response body is untyped Map<String, Object> instead of a structured ErrorResponse DTO or RFC 7807 ProblemDetails. Not covered by OpenAPI schema, consumer cannot codegen against it.
  - **Fix**: Create ErrorResponse DTO (or use spring-boot-starter-actuator ProblemDetail). Map @ExceptionHandler to return typed ErrorResponse with fields: type, title, status, detail, instance, correlationId.
- **[MEDIUM]** `src/main/java/com/lipari/bank/movement/MovementController.java:24` — GET /api/movements exposes raw Movement entity directly in response body. Entity leakage couples client to internal DB schema.
  - **Fix**: Create MovementResponse DTO with only the fields the client needs. Map entity to DTO in controller or service layer.
- **[MEDIUM]** `src/main/java/com/lipari/bank/movement/MovementController.java:17` — Controller injects MovementRepository directly (line 18) in addition to MovementService. Violates layering — controller should only depend on service layer.
  - **Fix**: Remove MovementRepository injection from controller. Move the list query into MovementService.
- **[MEDIUM]** `src/main/java/com/lipari/bank/movement/MovementService.java:44` — Service throws IllegalArgumentException for all business errors (not found, insufficient funds, same account). These map to 400 Bad Request — but 'account not found' should be 404, 'insufficient funds' should be 409 or 422, 'same account' is 400.
  - **Fix**: Throw domain-specific exceptions (e.g. AccountNotFoundException → 404, InsufficientFundsException → 409) and handle them with correct status codes in GlobalExceptionHandler.
- **[LOW]** `src/main/java/com/lipari/bank/movement/MovementController.java:19` — Endpoint path /transfer is a verb. REST convention prefers noun-based paths. POST /transfers (plural) is more conventional — the diff partially addresses this but inconsistently across project copies.
  - **Fix**: Standardize on POST /api/v1/movements/transfers (noun, plural) across all project copies.
- **[LOW]** `src/main/java/com/lipari/bank/common/GlobalExceptionHandler.java:27` — Generic RuntimeException handler returns 'internal error' message with 500 status — no distinction between expected and unexpected errors. BusinessException or similar should be mapped separately.
  - **Fix**: Add @ExceptionHandler for specific business exceptions. Keep RuntimeException handler but log the full exception for debugging.

---

## Summary

- CRITICAL: 0
- HIGH: 6
- MEDIUM: 4
- LOW: 2
