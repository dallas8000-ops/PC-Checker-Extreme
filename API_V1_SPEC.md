# PC Checker Extreme API v1 Spec (Hybrid Agent + Cloud)

This document defines the first production API contract for:

- Windows agent check-ins
- Rule-based incident generation
- AI incident enrichment
- Fleet digests and alert delivery

## 1) Principles

- Deterministic rules decide whether an incident exists.
- AI never decides alert truth; AI only explains and prioritizes.
- Every incident must include a concrete action plan.
- APIs are tenant-scoped and device-authenticated.

## 2) Auth and Security

- Agent auth: `X-Device-Token` (opaque rotating token per device).
- User auth: Django session today; JWT can be added later for API consumers.
- Request signing (recommended v1.1): `X-Signature` HMAC SHA256 over raw body.
- Replay protection: `X-Timestamp` + `X-Nonce` with 5 minute validity.
- Idempotency: `Idempotency-Key` required for check-ins.

## 3) Core Resources

- Account: customer workspace/tenant.
- Device: enrolled endpoint tied to an account.
- CheckIn: one telemetry upload from a device.
- Incident: rule trigger with severity, status, and actions.
- Digest: scheduled summary for account stakeholders.

## 4) Endpoints

### 4.1 Device Enrollment

`POST /api/v1/devices/enroll`

Request:

```json
{
  "device_name": "FrontDesk-PC-01",
  "hostname": "FRONTDESK01",
  "os": "Windows 11 Pro",
  "agent_version": "1.0.0",
  "fingerprint": "sha256:..."
}
```

Response:

```json
{
  "device_id": "dev_01J...",
  "device_token": "dtk_...",
  "account_id": "acct_01J...",
  "poll_interval_seconds": 900
}
```

### 4.2 Device Check-In

`POST /api/v1/devices/{device_id}/checkins`

Headers:

- `X-Device-Token`
- `Idempotency-Key`

Request (minimum telemetry contract):

```json
{
  "captured_at": "2026-06-03T22:30:00Z",
  "health_score": 78,
  "benchmark": {
    "cpu_score": 71,
    "disk_score": 62
  },
  "storage": {
    "volumes": [
      {"label": "C:", "free_gb": 14.2, "total_gb": 476.0, "percent_used": 97.0}
    ]
  },
  "security": {
    "defender_realtime": false,
    "firewall_enabled": true,
    "av_signature_age_days": 5
  },
  "updates": {
    "outdated_apps_count": 11,
    "pending_windows_updates_count": 3,
    "oldest_pending_update_days": 19
  },
  "startup": {
    "items_count": 34,
    "high_impact_count": 9
  },
  "drivers": {
    "duplicate_conflicts_count": 2,
    "old_drivers_count": 4
  },
  "hardware_health": {
    "smart_warnings_count": 1,
    "max_temp_c": 91,
    "repeated_thermal_spikes": true
  },
  "agent_meta": {
    "agent_version": "1.0.0",
    "scan_mode": "full"
  }
}
```

Response:

```json
{
  "checkin_id": "chk_01J...",
  "incident_ids_created": ["inc_01J...", "inc_01J..."],
  "next_checkin_after_seconds": 900
}
```

### 4.3 List Device Incidents

`GET /api/v1/devices/{device_id}/incidents?status=open&severity=critical`

### 4.4 List Fleet Incidents

`GET /api/v1/accounts/{account_id}/incidents?status=open`

### 4.5 Incident Detail

`GET /api/v1/incidents/{incident_id}`

### 4.6 AI Enrichment

`POST /api/v1/incidents/{incident_id}/explain`

Response includes:

- plain language explanation
- top 3 likely causes
- actionable remediation checklist
- estimated risk window

### 4.7 Weekly/Monthly Digest

`POST /api/v1/accounts/{account_id}/digests/run`

`GET /api/v1/accounts/{account_id}/digests?period=weekly`

## 5) Incident Types (v1)

- `low_disk_space`
- `security_posture_degraded`
- `patch_risk`
- `performance_regression`
- `startup_bloat`
- `driver_anomaly`
- `hardware_health_warning`
- `device_silent`
- `config_or_score_change`

## 6) Rule Thresholds (Initial Defaults)

- Low disk warning: system volume free `< 15%` or `< 25 GB`
- Low disk critical: system volume free `< 8%` or `< 10 GB`
- Security degraded: Defender RT off OR firewall off OR signatures `> 3 days`
- Patch risk warning: outdated apps `>= 10` OR pending updates age `>= 14 days`
- Patch risk critical: outdated apps `>= 20` OR pending updates age `>= 30 days`
- Performance regression: health score drop `>= 12` week-over-week
- Startup bloat warning: startup items `>= 25` OR high impact `>= 6`
- Driver anomaly: duplicate conflicts `>= 1` OR old drivers `>= 3`
- Hardware warning: SMART warnings `>= 1` OR max temp `>= 90C`
- Device silent warning: no check-in `> 24h`
- Device silent critical: no check-in `> 72h`

## 7) AI Capability Matrix

Good AI uses in v1:

- incident explanation in plain English
- likely-cause ranking from telemetry context
- remediation checklist generation
- executive digest summary
- before/after change narration

Do not use AI for v1:

- deciding if an incident should trigger
- final severity classification
- suppression/acknowledgement logic

## 8) Data Model Outline

- `Account(id, name, plan, created_at)`
- `Device(id, account_id, name, hostname, token_hash, last_checkin_at, status)`
- `CheckIn(id, device_id, captured_at, payload_json, health_score, benchmark_json)`
- `Incident(id, account_id, device_id, type, severity, status, first_seen_at, last_seen_at, rule_version, evidence_json)`
- `IncidentAction(id, incident_id, step_order, title, detail, safe_level)`
- `IncidentAiExplanation(id, incident_id, summary, causes_json, actions_json, generated_at, model)`
- `Digest(id, account_id, period, generated_at, content_json)`

## 9) Notification Channels

v1 channels:

- email
- webhook

v1.1 channels:

- Slack
- Teams

## 10) Rollout Plan

Phase 1 (2-3 weeks):

- device enrollment
- check-in endpoint
- incident rule engine for top 6 incidents
- fleet incident list UI

Phase 2 (2-3 weeks):

- AI enrichment endpoint
- weekly digest generation
- notification preferences per account

Phase 3 (2 weeks):

- device silent monitoring
- what changed report
- threshold tuning UI per account
