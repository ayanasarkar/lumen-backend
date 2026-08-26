# lumen-backend

Unified Go ingestion CLI for the LUMEN demo pipeline. Pulls all 5 required
datasets (PRADAN, ODE, DEM, SPICE, Robbins Crater DB — Tier 1 + Tier 2 from
the dataset access guide) into a local `data/` folder, with resumable,
retrying, checksum-verifiable downloads shared across every connector.

## Status of each connector

| Connector | Status | Notes |
|---|---|---|
| **ODE** | Real REST client | `oderest.rsl.wustl.edu` has a documented public API. Query params (`ihid`/`iid`/`pt`) are wired up for LRO NAC/WAC; verify the JSON response shape against a live call and adjust `internal/ode/ode.go`'s structs if ODE's schema differs from what's assumed here. |
| **PRADAN** | Scaffold only | ISSDC's PRADAN portal has no documented public API as of this writing. `internal/pradan/pradan.go` explains why and gives you two paths: (a) reverse-engineer the portal's login/query requests via browser dev tools and fill in `Login`/`Query`, or (b) the pragmatic unblock — manually download files via the website, paste the direct URLs into `manifests/pradan_manifest.txt`, and let `ManifestDownload` handle the rest. |
| **DEM** | Manifest-driven | SLDEM2015 + PGDA are static tile downloads — put tile URLs in `manifests/dem_manifest.txt`. Kaguya TC DTM no-auth S3 fallback available via `dem.KaguyaFallback()` (needs the `aws` CLI). |
| **SPICE** | Real, mostly automatic | Generic kernels (leapseconds, planetary ephemeris) download automatically from NAIF. LRO-specific kernels go in `manifests/spice_lro_manifest.txt` — pick the ones covering your imagery's acquisition dates. |
| **Robbins Crater DB** | Real, one-time | Single static ZIP from USGS Astropedia, no per-site logic needed. |

## Setup

Requires Go 1.22+.

```bash
cp sites.example.json sites.json
# edit sites.json: fill in your one equatorial + one polar site bbox
```

`sites.json` is gitignored — your real coordinates stay local.

## Usage

```bash
go build -o lumen-backend .

./lumen-backend all        # run every connector in order
./lumen-backend ode        # ODE only
./lumen-backend pradan     # PRADAN only (manifest-driven)
./lumen-backend dem        # DEM only (manifest-driven)
./lumen-backend spice      # SPICE kernels
./lumen-backend robbins    # Robbins Crater DB
```

Flags (any command):

```
-sites string   path to sites.json (default "sites.json")
-data string    output data directory (default "data")
```

`all` keeps going even if one connector errors (e.g. an empty PRADAN
manifest) so a single missing piece doesn't block the rest.

## Project layout

```
lumen-backend/
├── main.go                      CLI entrypoint, wires all connectors together
├── sites.example.json           Template — copy to sites.json and fill in
├── internal/
│   ├── downloader/               Shared resumable + retrying + checksummed fetch
│   ├── config/                   sites.json loading/validation
│   ├── ode/                      ODE REST client (real)
│   ├── pradan/                   PRADAN scaffold (manifest fallback works today)
│   ├── dem/                      DEM manifest downloader + Kaguya S3 fallback
│   ├── spice/                    NAIF generic kernels + LRO kernel manifest
│   └── robbins/                  Robbins Crater DB one-time download
└── manifests/
    ├── pradan_manifest.txt       Paste PRADAN file URLs here
    ├── dem_manifest.txt          Paste SLDEM2015/PGDA tile URLs here
    └── spice_lro_manifest.txt    Paste LRO SPICE kernel URLs here
```

## Why the shared downloader matters

Every connector routes through `internal/downloader.Fetch`, which gives all
of them, for free:

- **Resume**: partial downloads (`.part` files) pick up where they left off
  via HTTP Range requests instead of restarting from zero.
- **Retry with backoff**: transient network failures get retried (default 5x)
  with exponential backoff instead of failing the whole run.
- **Idempotency**: re-running any command skips files that already exist
  (and, if a checksum was provided, verifies them first).

## Known gaps / next steps

1. **PRADAN auth** — the biggest open item. Once you can see PRADAN's real
   login/query network requests, port them into `internal/pradan/pradan.go`.
2. **ODE response shape** — the JSON structs in `internal/ode/ode.go` are
   built from ODE's documented schema but not verified against a live
   response in this environment (this sandbox's network egress is
   restricted to a small domain allowlist that doesn't include ODE). Run a
   real query early and adjust the structs if fields don't match.
3. **Checksums** — none of the manifests include SHA-256 hashes yet. Add
   them where the source publishes one (Robbins DB, NAIF kernels often do)
   to get automatic corruption detection for free.
