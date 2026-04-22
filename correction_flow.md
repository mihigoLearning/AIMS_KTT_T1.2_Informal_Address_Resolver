# Correction Flow — Offline Motorcycle Rider Address Correction

**Challenge:** T1.2 · Informal Address Resolver  
**Artifact type:** Product & Business Adaptation

---

## The Problem

A motorcycle rider (moto) arrives at the resolved coordinate and finds the pin is wrong — the package destination is 80 metres away behind a red gate, not at the pharmacy the resolver matched. The rider is semi-literate, may have only a basic Android phone, and will be offline for up to 6 hours while completing other deliveries.

---

## User Profile

| Attribute | Reality |
|-----------|---------|
| Device | Entry-level Android (Tecno/Itel), 2G/3G intermittent |
| Literacy | Can read SMS-length text; struggles with forms |
| Connectivity | Online at depot (7 am, 6 pm); offline 6–10 hours mid-day |
| Language | Kinyarwanda primary; basic French numerals |
| Data budget | ~100 MB/month (MTN Rwanda prepaid) |

---

## Input Modality — 3 Button-Presses

We deliberately avoid voice (noisy street, privacy) and photo (file size, upload cost). The correction UI is **3 taps + 1 optional free-text note**:

```
┌──────────────────────────────────┐
│  Wrong pin?                      │
│                                  │
│  [1] A bit off  (< 100 m)        │
│  [2] Very wrong (> 100 m)        │
│  [3] No such place               │
│                                  │
│  [Optional note in Kinyarwanda]  │
│  [SUBMIT — saves offline]        │
└──────────────────────────────────┘
```

Button 1 triggers a drag-pin map view (cached OpenStreetMap tiles, 0 data cost).  
Button 2 opens a "describe in your words" voice-to-text field (single sentence).  
Button 3 marks the description as unresolvable → automatic dispatcher escalation on re-sync.

---

## Step-by-Step Correction Workflow

### Phase A — At the delivery location (offline)

1. **Rider notices wrong pin** during delivery run.
2. Rider taps **"Wrong pin?"** button in the delivery app.
3. Rider selects severity (1/2/3) — 2 taps total.
4. If button 1: rider drags map pin to correct location. New (lat, lon) stored locally.
5. If button 2: rider speaks one sentence; app stores audio + timestamp.
6. If button 3: app sets `status = unresolvable`, stores description_id + timestamp.
7. All corrections written to **local SQLite queue** (`corrections.db`) — no network needed.
8. Each correction record: `{description_id, correction_type, new_lat, new_lon, note, rider_id, timestamp_utc, device_id}` ≈ **200 bytes**.

### Phase B — On re-sync (rider returns to depot or hits 3G signal)

9. App detects connectivity → triggers background sync of `corrections.db`.
10. Corrections uploaded to backend via REST endpoint (`POST /corrections/batch`).
11. **Conflict resolution rule:** Last-write-wins per description_id, with dispatcher review flag if ≥ 2 riders disagree on the same address (lat/lon delta > 50 m).
12. Backend updates `gold.csv` equivalent and re-trains the resolver's confidence thresholds nightly.
13. Rider receives silent push notification: *"3 corrections synced. Thank you."*

### Phase C — Dispatcher review (office, connected)

14. Dispatcher dashboard shows flagged descriptions (confidence < 0.45, or rider-flagged).
15. Dispatcher reviews correction map, confirms or overrides the new pin.
16. Confirmed corrections feed back into gazetteer as new landmark aliases.

---

## Offline Storage & Conflict Resolution

| Scenario | Resolution |
|----------|-----------|
| 1 rider corrects, syncs | Accepted immediately |
| 2 riders submit different pins for same address | Both stored; flagged for dispatcher if delta > 50 m |
| Rider corrects, then dispatcher overrides | Dispatcher wins; rider correction archived |
| Rider offline > 24 h | Queue held locally; no data loss; syncs on next connection |

**Storage estimate per rider per month:**  
- Average 30 deliveries/day × 30 days = 900 deliveries  
- Correction rate ≈ 8% = ~72 corrections/month  
- 72 × 200 bytes = **~14 KB/month** (negligible — within free MTN data bundles)

---

## Why This Is Cheaper Than Paper Bug Reports

Paper bug reports in Rwandan logistics today cost approximately **RWF 350 per correction** when you account for: rider time to write the report (~3 min), office staff time to transcribe it (~5 min at RWF 1,200/hr), and the 48-hour lag before the gazetteer is updated.

This 3-button digital flow costs approximately **RWF 50 per correction**: 30 seconds of rider time, zero transcription, instant queue storage, and automated sync. The gazetteer is updated within 24 hours. At scale (500 riders), the annual saving exceeds **RWF 43 million** (≈ USD 30,000) while cutting the address error feedback loop from 48 hours to under 24 hours.

---

## Stretch: Cold-Start for a New District

When a new district has 0 gazetteer entries:
1. Dispatcher seeds 5–10 anchor landmarks from OpenStreetMap (automated import script).
2. First 50 successful deliveries are treated as gold — rider confirmations auto-expand the gazetteer.
3. Confidence threshold for the new district is set to 0.35 (more permissive) until ≥ 100 confirmed resolutions exist.
