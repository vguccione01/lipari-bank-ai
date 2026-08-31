---
name: compliance-aml-check
description: >
  Verifica compliance AML di un cambiamento di codice del LipariBank Spring. Da attivare
  automaticamente quando il task riguarda movimento di denaro, audit, transazioni,
  segnalazioni operazioni sospette (SOS), PEP, watchlist, o quando l'utente cita
  esplicitamente AML / antiriciclaggio / compliance bancaria.
---

# AML Compliance Check — LipariBank

Questa skill esegue una verifica strutturata della compliance AML del codice LipariBank
contro i requisiti della **Direttiva UE 2018/843 (5a AMLD)** e della normativa
**Banca d'Italia (CICR / Regolamento AML)**. Non modifica il codice: produce solo
una tabella di findings.

---

## 1. Audit Trail obbligatorio (4-tupla minima)

### Cosa verifica nel codice

Controlla che **ogni** operazione che muove denaro (transfer, deposit, withdraw, cancel)
generi un record contenente la 4-tupla minimale richiesta dalla normativa AML:

- `correlationId` — identificativo unico della richiesta (UUID v4), propagato dall'header
  HTTP `X-Correlation-Id` fino al record DB.
- `userId` — identificativo dell'utente autenticato che ha initiato l'operazione
  (estratto da `SecurityContextHolder` o equivalente).
- `ipAddress` — indirizzo IP del client (estratto da `X-Forwarded-For` o
  `HttpServletRequest.getRemoteAddr()`).
- `executedAt` — timestamp UTC dell'esecuzione (tipo `Instant` o `Timestamp`, non
  `LocalDateTime` senza timezone).

La skill cerca pattern mancanti: campi nullable senza `@Column(nullable = false)`,
metodi che creano `Movement` senza valorizzare tutti e 4 i campi, DTO di risposta
che omettono almeno uno dei 4.

### Criterio di accettazione

Ogni classe `Movement` (o equivalente) deve avere i 4 campi annotati come `NOT NULL`.
Ogni metodo del service che persiste un `Movement` deve valorizzarli **prima** della
chiamata a `repository.save()`. Il `correlationId` deve essere propagato via parametro
o via `RequestContextHolder`.

### Esempio positivo

```java
Movement m = new Movement();
m.setCorrelationId(correlationId);   // ← presente
m.setUserId(currentUserId);          // ← presente
m.setIpAddress(remoteAddr);          // ← presente
m.setExecutedAt(Instant.now(clock)); // ← presente, UTC
movementRepo.save(m);
```

### Esempio negativo

```java
Movement m = new Movement();
m.setAccountId(from.getId());
m.setType("TRANSFER_OUT");
m.setAmount(req.getAmount());
m.setExecutedAt(Instant.now()); // ← ipAddress e userId mancano
movementRepo.save(m);
```

### Severity in caso di violazione

**HIGH** — audit trail incompleto è un gap di compliance documentato nelle linee guida
Banca d'Italia (Circ. 169758/2017) e nell'art. 40 della 4a AMLD recepita.

### Output findings

| Severity | File:Line | Anti-pattern | Riferimento normativo | Recommendation |
|----------|-----------|-------------|----------------------|----------------|
| HIGH | `MovementService.java:49-56` | `Movement` creato senza `correlationId`, `userId`, `ipAddress` | Art. 40 D.Lgs. 231/2007; Circ. 169758/2017 | Aggiungere i 3 campi obbligatori con `@Column(nullable = false)` e valorizzarli prima del save |

---

## 2. Soglie operative e segnalazione UIF (SOS)

### Cosa verifica nel codice

Verifica che il codice contenga **logica dichiarata** (o punto di estensione documentato)
per:

- **Soglia 10.000 EUR cumulativa settimanale**: quando l'importo cumulativo dei
  trasferimenti dallo stesso `fromAccountId` nella stessa settimana calendario supera
  EUR 10.000, deve essere generata (o preparata) una segnalazione di operazione sospetta
  (SOS) alla UIF.
- **Frazionamento sospetto a 5.000 EUR**: quando 2 o più operazioni dallo stesso
  conto superano EUR 5.000 in un periodo ≤ 7 giorni con pattern di frazionamento
  (stessi beneficiary, importi simili, timing ravvicinato), deve essere attivato
  un allerta interna.
- La skill non implementa la logica: verifica che esista un **hook** (method, event
  listener, o scheduled job) con riferimento a una delle due soglie, oppure segnala
  l'assenza come gap.

La skill cerca nel codebase: classi o metodi che contengono riferimenti a 10000, 10_000,
5000, 5_000, `THRESHOLD`, `WEEKLY_LIMIT`, `SOS`, `UIF`, `segnalazione`,
`SuspiciousActivity`, `Structuring`, `frazionamento`.

### Criterio di accettazione

Deve esistere almeno uno dei seguenti:
1. Un metodo `checkThreshold(Long accountId, BigDecimal weeklyTotal)` invocato
   dopo ogni transfer, oppure
2. Un `@Scheduled` job che controlla cumulative settimanali, oppure
3. Un event/listener che delega a un servizio esterno di monitoring.

Se nessuno dei tre è presente → gap CRITICAL. Se esiste ma copre solo una delle due
soglie → HIGH.

### Esempio positivo

```java
@Transactional
public TransferResponse transfer(TransferRequest req, String correlationId) {
    TransferResponse resp = doTransfer(req, correlationId);
    thresholdService.checkWeeklyCumulative(req.getFromAccountId(), correlationId);
    return resp;
}
```

### Esempio negativo

```java
@Transactional
public TransferResponse transfer(TransferRequest req) {
    // ... transfer logic ...
    // Nessun check soglia, nessun hook verso UIF
    return new TransferResponse(out.getId(), from.getBalance(), to.getBalance(), "COMPLETED");
}
```

### Severity in caso di violazione

- **CRITICAL** — assenza totale di logica di segnalazione UIF/monitoring soglie.
- **HIGH** — logica presente ma incompleta (una sola soglia coperta).

### Output findings

| Severity | File:Line | Anti-pattern | Riferimento normativo | Recommendation |
|----------|-----------|-------------|----------------------|----------------|
| CRITICAL | `MovementService.java:30-68` | Nessun hook per soglia 10K EUR settimanale o frazionamento 5K EUR | Art. 35 D.Lgs. 231/2007; Reg. Banca d'Italia 2024/03 | Aggiungere `thresholdService.checkWeeklyCumulative()` dopo ogni transfer |

---

## 3. PEP Screening e Watchlist (OFAC/EU)

### Cosa verifica nel codice

Verifica che il codice contenga un **punto di interazione** (chiamata a servizio,
annotazione, o hook) con un sistema di screening PEP (Politically Exposed Persons)
e/o watchlist (OFAC, EU Consolidated List). La skill non richiede l'implementazione
dell'intero sistema, ma vuole trovare evidenza che il servizio di transfer si
**interfaccia** con esso.

Cerca nel codebase: classi o metodi con riferimenti a `PEP`, `PoliticallyExposed`,
`watchlist`, `OFAC`, `sanctions`, `screening`, `checkPep`, `checkSanctions`,
`isSanctioned`, `PoliticallyExposedPerson`.

La skill distingue tra:
- **Implementazione diretta** (servizio interno con DB o chiamata HTTP) → accettabile.
- **Delega a servizio esterno via interfaccia** (es. `PepScreeningService` interface
  con implementazione esterna) → accettabile con documentazione.
- **Nessun riferimento** → gap CRITICAL (compliance obbligatoria).

### Criterio di accettazione

Deve esistere almeno una delle seguenti evidenze:
1. Una chiamata a `pepScreeningService.isPep(userId)` o equivalente, invocata
   prima del transfer o in un listener post-transfer.
2. Una chiamata a `watchlistService.checkSanctions(toAccountId)` o equivalente.
3. Un'interfaccia `ScreeningService` documentata come esterna, con punto di
   integrazione nel transfer flow.

### Esempio positivo

```java
public TransferResponse transfer(TransferRequest req, String correlationId) {
    if (pepScreeningService.isPep(req.getFromAccountId())) {
        log.warn("PEP detected for account: {}", req.getFromAccountId());
        sosService.flagForReview(req.getFromAccountId(), "PEP_TRANSFER", correlationId);
    }
    // ... transfer logic ...
}
```

### Esempio negativo

```java
public TransferResponse transfer(TransferRequest req) {
    // Nessun check PEP, nessun check watchlist
    Account from = accountRepo.findById(req.getFromAccountId())...
    // ... transfer diretto ...
}
```

### Severity in caso di violazione

- **CRITICAL** — assenza totale di screening PEP/watchlist nel flow di transfer.
- **MEDIUM** — screening presente ma solo su una delle due liste (PEP o watchlist).

### Output findings

| Severity | File:Line | Anti-pattern | Riferimento normativo | Recommendation |
|----------|-----------|-------------|----------------------|----------------|
| CRITICAL | `MovementService.java:30-68` | Nessuna chiamata a servizio PEP screening o watchlist nel flow transfer | Art. 11 D.Lgs. 231/2007; Reg. UE 2018/843 Art. 18 | Aggiungere `pepScreeningService.isPep()` e `watchlistService.checkSanctions()` prima del transfer effettivo |

---

## 4. Identificazione dell'operatore e tracciabilità utente

### Cosa verifica nel codice

Verifica che ogni operazione finanziaria registri **chi** l'ha eseguita con:
- `userId` estratto dal contesto di sicurezza (non hardcoded, non passato come
  parametro libero dal client).
- Corretta utilizzazione di `SecurityContextHolder.getContext().getAuthentication()`
  o equivalente Spring Security.
- Il `userId` deve essere un identificativo stabile (ID numerico o UUID), non un
  username mutable.

Cerca: uso di `SecurityContextHolder`, `@AuthenticationPrincipal`, `Principal`,
`getCurrentUser()`, `currentUser.getId()`. Segnala se il servizio accetta un
`userId` come campo del request body (spoofing possibile).

### Criterio di accettazione

Il `userId` deve essere:
1. Estratto dal contesto di sicurezza server-side (mai dal request body).
2. Salvato nel record `Movement` con `@Column(nullable = false)`.
3. Non sovrascrivibile dal client (nessun campo `userId` nel DTO di input del
   transfer).

### Esempio positivo

```java
String userId = SecurityContextHolder.getContext()
    .getAuthentication()
    .getName();
movement.setUserId(userId); // ← estratto dal SecurityContext
```

### Esempio negativo

```java
// Nel DTO
public class TransferRequest {
    private String userId; // ← il client può falsificarlo
}

// Nel servizio
movement.setUserId(req.getUserId()); // ← spoofing!
```

### Severity in caso di violazione

**HIGH** — tracciabilità utente compromessa. In caso di indagine UIF, il log
non sarebbe attendibile.

### Output findings

| Severity | File:Line | Anti-pattern | Riferimento normativo | Recommendation |
|----------|-----------|-------------|----------------------|----------------|
| HIGH | `MovementService.java` | `userId` non estratto da SecurityContext o accettato dal client | Art. 3 D.Lgs. 231/2007; Circ. 169758/2017 | Estrarre `userId` da `SecurityContextHolder` e salvare nel Movement con vincolo NOT NULL |

---

## 5. Segnalazione Operazione Sospetta (SOS) — tempistiche e persistence

### Cosa verifica nel codice

Verifica che il sistema preveda un meccanismo per:
- **Segnalare** operazioni sospette alla UIF interna entro 24 ore dall'evento
  (art. 35 D.Lgs. 231/2007).
- **Persistere** la segnalazione SOS in DB con stato (`PENDING`, `SUBMITTED`,
  `ACKNOWLEDGED`) e timestamp di creazione.
- **Notificare** (log, evento, o chiamata) l'operatore compliance incaricato.

La skill cerca: classi `SuspiciousActivityReport`, `SAR`, `SOS`, `UiF`,
`segnalazione`, metodi `reportSuspicious()`, `flagSos()`, `submitToUif()`,
annotazioni `@Async` o `@Scheduled` relative a controlli periodici.

Se il codice non ha alcun riferimento a SOS/UIF, segnala come CRITICAL.
Se ha la struttura ma non garantisce la tempistica 24h (nessun deadline check,
nessun scheduler), segnala come HIGH.

### Criterio di accettazione

Deve esistere almeno uno dei seguenti:
1. Una classe `SuspiciousActivityReport` con campi: `accountId`, `reason`,
   `createdAt`, `reportedAt`, `status`, e metodo `submitToUif()`.
2. Un `@Scheduled` job che controlla SOS pending e le sottomette entro 24h.
3. Un integration point documentato con il sistema UIF esterno, con deadline
   enforcement.

### Esempio positivo

```java
@Service
public class UifReportingService {

    @Async
    public void reportSuspicious(SuspiciousActivityReport sar) {
        sar.setStatus("PENDING");
        sar.setCreatedAt(Instant.now());
        sarRepo.save(sar);
        scheduleDeadlineCheck(sar); // ← garantisce 24h
    }

    @Scheduled(cron = "0 0 * * * *")
    public void checkPendingReports() {
        List<SuspiciousActivityReport> overdue = sarRepo
            .findByStatusAndCreatedAtBefore("PENDING", Instant.now().minus(Duration.ofHours(24)));
        overdue.forEach(sar -> {
            sar.setStatus("OVERDUE");
            notifyComplianceOfficer(sar);
        });
    }
}
```

### Esempio negativo

```java
// Nessuna classe SOS, nessun servizio UIF, nessun scheduler
// Il codice ha solo Movement e Transfer — nessun riferimento a segnalazioni
```

### Severity in caso di violazione

- **CRITICAL** — assenza totale di meccanismo SOS/UIF.
- **HIGH** — meccanismo presente ma senza enforcement della tempistica 24h.

### Output findings

| Severity | File:Line | Anti-pattern | Riferimento normativo | Recommendation |
|----------|-----------|-------------|----------------------|----------------|
| CRITICAL | `MovementService.java` | Nessuna segnalazione SOS UIF dopo operazione sospetta | Art. 35 D.Lgs. 231/2007; Reg. Banca d'Italia 2024/03 | Implementare `UifReportingService` con audit trail completo e deadline 24h |

Al termine crea un file markdown nominato `opencode_output/AML_check_YYYYMMDDHHmmSS.md` contenente l'output della skill.