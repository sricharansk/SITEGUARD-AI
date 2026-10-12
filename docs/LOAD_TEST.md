# Site Guard AI: load test and capacity

Measured on 12 October 2026 with `scripts/load_test.py` against the production image (`backend/Dockerfile`, one
container running one uvicorn process, rules provider) on PostgreSQL 16 + pgvector. The load generator, the API
container and PostgreSQL shared one 4 vCPU (Intel Xeon 2.1 GHz), 16 GB Linux host, so the numbers are a floor for a
dedicated deployment, not a promise for one. All data is the synthetic demo seed plus the synthetic incidents the
load test reports.

## How the load is made

- **Readers** (project manager, HSE manager, QA/QC engineer, auditor, signed in once each) repeat a weighted mix:
  dashboard 3, incident list 3, incident workspace 4, action queue 2, notifications 2, knowledge search 2, `/me` 1.
- **Writers** (safety engineer) report a synthetic incident and run the full multi-agent investigation on it
  (triage, safety, risk, RCA, compliance, CAPA, approval stage), the heaviest request the API serves.
- **Think time** is the pause between one user's requests. 0 ms finds the saturation point; 2 s is closer to people
  clicking through the web app.
- Every non-2xx response or network failure counts as an error.

## Results

| Run | Readers | Writers | Think | Requests/s | Error rate | Read p50 | Read p95 | Read p99 | Investigation p50 |
|---|---|---|---|---|---|---|---|---|---|
| Single user | 1 | 0 | 0 ms | 53 | 0% | 20 ms | 28 ms | 33 ms | |
| Saturation | 10 | 0 | 0 ms | 57 | 0% | 166 ms | 319 ms | 377 ms | |
| Saturation | 25 | 0 | 0 ms | 56 | 0% | 424 ms | 745 ms | 927 ms | |
| Realistic mix | 100 | 2 | 2 s | 39 | 0% | 332 ms | 802 ms | 1055 ms | 2.3 s |
| Concurrent reporting | 1 | 8 | 0 ms | 11 | 0% | 213 ms | 718 ms | 940 ms | 2.0 s |

Per-endpoint tables for every run are in the appendix.

## Findings

1. **One API process serves about 55 requests per second.** A single user with no think time already reaches 53
   req/s; adding users raises latency, not throughput. The API is CPU-bound in one Python process, so the other cores
   are idle. With users pausing 2 s between clicks, 100 concurrent readers plus 2 people reporting and investigating
   ran at 39 req/s with a read p95 of 0.80 s and no errors.
2. **Investigations cost about 2–2.5 s of API time each** with the rules provider and slow reads while they run (read
   p95 0.72 s with 8 investigations in flight). 8 parallel reporters completed 113 report-and-investigate cycles in
   30 s (3.7 per second) without a single reference collision.
3. **Concurrent reports failed before this change (fixed).** Incident references (`SG-2026-0042`) were numbered by
   counting existing incidents, so two reports submitted at the same moment got the same number and the second
   failed with HTTP 500 on the unique key: 1 of 25 reports in the first realistic run on PostgreSQL, 3 of 15 in a
   20 s run on SQLite with 4 reporters. Numbering is now serialised with a transaction-scoped advisory lock on PostgreSQL, and the API renumbers
   and retries (at most 5 times) when a reference is already taken, which covers SQLite. Covered by
   `test_concurrent_incident_reports_get_unique_references` (PostgreSQL, 8 threads) and
   `test_report_retries_a_reference_taken_by_a_concurrent_report`.
4. **The dashboard, action queue and incident list slow down as a project grows.** They load every incident,
   action and agent run of the project and aggregate in Python. After the runs above grew the project from 20 to
   155 incidents (873 actions, 746 agent runs), single-user p50 latency changed as follows:

   | Endpoint | 20 incidents | 155 incidents |
   |---|---|---|
   | `GET /dashboard` | 20 ms | 82 ms |
   | `GET /capa` | 20 ms | 43 ms |
   | `GET /projects/{id}/incidents` | 13 ms | 26 ms |
   | `GET /incidents/{id}` | 25 ms | 27 ms |
   | `GET /search` | 23 ms | 24 ms |

   Growth is roughly linear, so a project with a few thousand incidents would have a dashboard near one second
   before any load. This is the main scaling risk found; it is not fixed in this change.

## Capacity guidance

- **Pilot sizing:** one container (Decision 016; one replica because the login throttle is in process) comfortably
  serves a pilot of tens of active users and a few hundred incidents per project. Watch `GET /dashboard` p95 and keep
  it under 1 s; every request is logged with its duration (`ms`) and correlation id, and the logs go to Log
  Analytics.
- **Before scaling out or growing past ~1,000 incidents per project:**
  1. Compute dashboard figures with SQL aggregates and paginate the incident list and action queue (finding 4).
  2. Move the login throttle and vision rate limit to a shared store, then run several uvicorn workers or replicas
     (finding 1); seeding and migrations already run before the app starts serving, but should then run once as a
     job rather than per replica.
  3. Run investigations as a background job so they do not compete with page loads (finding 2). With the Claude
     provider an investigation is dominated by model latency rather than CPU; that profile is not measured here.
- Re-run this test against Azure staging once it exists, from a separate machine, and record the results here.

## How to run

```bash
# against a local stack with demo data (make up, or the image as in CI); never against production
python scripts/load_test.py --base-url http://localhost:8000 --users 25 --duration 60
python scripts/load_test.py --base-url http://localhost:8000 --users 100 --writers 2 --think-ms 2000 --ramp 10 \
    --duration 60 --out docs/LOAD_TEST.md --json load.json
```

Writers create incidents, so `--writers` is 0 unless set, and the script refuses a deployment whose `/health`
reports `production`. The demo password comes from `SITEGUARD_LOAD_PASSWORD` (default: the demo password).
`--max-error-rate` and `--max-p95-ms` make it exit 1 for use as a gate. CI runs a 20 s check after the browser
tests in the `docker` job (10 readers, 4 writers, SQLite, error rate must be 0, read p95 under 5 s).

## Appendix: per-endpoint results

### 1 reader, 0 writers, think time 0 ms

1584 requests in 30.0 s (52.79 req/s), error rate 0.00%. Read latency p50 19.7 ms, p95 28.3 ms, p99 33.2 ms. Incidents reported and investigated: 0.

| Endpoint | Requests | req/s | p50 ms | p95 ms | p99 ms | max ms | Errors |
|---|---|---|---|---|---|---|---|
| `GET /capa` | 178 | 5.93 | 20.3 | 24.7 | 31.4 | 38.6 | 0 |
| `GET /dashboard` | 293 | 9.76 | 20.0 | 26.3 | 132.4 | 155.7 | 0 |
| `GET /incidents/{id}` | 394 | 13.13 | 24.7 | 30.8 | 35.3 | 41.6 | 0 |
| `GET /me` | 87 | 2.9 | 8.3 | 10.1 | 11.3 | 11.3 | 0 |
| `GET /notifications` | 177 | 5.9 | 8.9 | 11.0 | 13.7 | 14.4 | 0 |
| `GET /projects/{id}/incidents` | 292 | 9.73 | 12.9 | 16.3 | 19.6 | 23.0 | 0 |
| `GET /search` | 163 | 5.43 | 23.4 | 29.8 | 32.6 | 32.9 | 0 |

### 10 readers, 0 writers, think time 0 ms

1717 requests in 30.2 s (56.83 req/s), error rate 0.00%. Read latency p50 166.3 ms, p95 318.9 ms, p99 377.3 ms. Incidents reported and investigated: 0.

| Endpoint | Requests | req/s | p50 ms | p95 ms | p99 ms | max ms | Errors |
|---|---|---|---|---|---|---|---|
| `GET /capa` | 207 | 6.85 | 142.3 | 270.7 | 320.5 | 369.3 | 0 |
| `GET /dashboard` | 323 | 10.69 | 194.5 | 333.1 | 365.5 | 381.8 | 0 |
| `GET /incidents/{id}` | 418 | 13.84 | 219.2 | 368.5 | 403.1 | 429.1 | 0 |
| `GET /me` | 78 | 2.58 | 88.5 | 207.1 | 312.8 | 312.8 | 0 |
| `GET /notifications` | 189 | 6.26 | 92.5 | 196.1 | 294.6 | 301.2 | 0 |
| `GET /projects/{id}/incidents` | 299 | 9.9 | 123.8 | 235.7 | 307.9 | 313.5 | 0 |
| `GET /search` | 203 | 6.72 | 170.4 | 315.0 | 365.7 | 398.8 | 0 |

### 25 readers, 0 writers, think time 0 ms

1714 requests in 30.5 s (56.25 req/s), error rate 0.00%. Read latency p50 424.3 ms, p95 744.6 ms, p99 926.8 ms. Incidents reported and investigated: 0.

| Endpoint | Requests | req/s | p50 ms | p95 ms | p99 ms | max ms | Errors |
|---|---|---|---|---|---|---|---|
| `GET /capa` | 220 | 7.22 | 396.5 | 655.7 | 787.8 | 1066.6 | 0 |
| `GET /dashboard` | 318 | 10.44 | 471.2 | 818.4 | 926.8 | 967.2 | 0 |
| `GET /incidents/{id}` | 395 | 12.96 | 518.6 | 786.2 | 1027.4 | 1379.4 | 0 |
| `GET /me` | 91 | 2.99 | 329.8 | 680.4 | 1454.3 | 1454.3 | 0 |
| `GET /notifications` | 198 | 6.5 | 325.1 | 552.7 | 811.4 | 967.4 | 0 |
| `GET /projects/{id}/incidents` | 285 | 9.35 | 356.7 | 606.6 | 824.5 | 836.4 | 0 |
| `GET /search` | 207 | 6.79 | 420.1 | 747.6 | 935.9 | 1067.5 | 0 |

### 100 readers, 2 writers, think time 2000 ms

2443 requests in 62.5 s (39.08 req/s), error rate 0.00%. Read latency p50 332.0 ms, p95 801.7 ms, p99 1054.8 ms. Incidents reported and investigated: 22.

| Endpoint | Requests | req/s | p50 ms | p95 ms | p99 ms | max ms | Errors |
|---|---|---|---|---|---|---|---|
| `GET /capa` | 297 | 4.75 | 379.1 | 819.8 | 1031.3 | 1392.7 | 0 |
| `GET /dashboard` | 434 | 6.94 | 456.9 | 930.7 | 1230.5 | 1613.4 | 0 |
| `GET /incidents/{id}` | 544 | 8.7 | 393.4 | 780.1 | 1108.0 | 1592.1 | 0 |
| `GET /me` | 133 | 2.13 | 184.3 | 560.6 | 713.1 | 805.7 | 0 |
| `GET /notifications` | 269 | 4.3 | 183.7 | 555.6 | 813.9 | 953.6 | 0 |
| `GET /projects/{id}/incidents` | 432 | 6.91 | 229.4 | 624.7 | 1028.7 | 1394.5 | 0 |
| `GET /search` | 290 | 4.64 | 335.6 | 733.6 | 999.8 | 1126.0 | 0 |
| `POST /incidents/{id}/investigate` | 22 | 0.35 | 2253.5 | 3538.8 | 4044.3 | 4044.3 | 0 |
| `POST /projects/{id}/incidents` | 22 | 0.35 | 254.0 | 591.0 | 892.1 | 892.1 | 0 |

### 1 reader, 8 writers, think time 0 ms

333 requests in 31.1 s (10.7 req/s), error rate 0.00%. Read latency p50 213.3 ms, p95 717.9 ms, p99 940.3 ms. Incidents reported and investigated: 113.

| Endpoint | Requests | req/s | p50 ms | p95 ms | p99 ms | max ms | Errors |
|---|---|---|---|---|---|---|---|
| `GET /capa` | 11 | 0.35 | 232.4 | 361.7 | 361.7 | 361.7 | 0 |
| `GET /dashboard` | 29 | 0.93 | 508.7 | 940.3 | 991.0 | 991.0 | 0 |
| `GET /incidents/{id}` | 29 | 0.93 | 222.4 | 310.4 | 642.2 | 642.2 | 0 |
| `GET /me` | 5 | 0.16 | 89.0 | 112.9 | 112.9 | 112.9 | 0 |
| `GET /notifications` | 6 | 0.19 | 89.7 | 167.8 | 167.8 | 167.8 | 0 |
| `GET /projects/{id}/incidents` | 20 | 0.64 | 138.9 | 286.7 | 369.8 | 369.8 | 0 |
| `GET /search` | 7 | 0.22 | 138.1 | 209.9 | 209.9 | 209.9 | 0 |
| `POST /incidents/{id}/investigate` | 113 | 3.63 | 1985.7 | 2340.9 | 2384.3 | 2445.4 | 0 |
| `POST /projects/{id}/incidents` | 113 | 3.63 | 172.8 | 363.7 | 408.0 | 435.2 | 0 |
