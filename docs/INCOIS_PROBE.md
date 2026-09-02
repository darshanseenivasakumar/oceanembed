# D2 — INCOIS Live Access Server probe

**Probed:** 2026-09-02, 00:13–00:35 IST (server clock `Tue, 01 Sep 2026 18:43:57 GMT`)
**Host:** `las.incois.gov.in`
**Verdict:** **catalogue reachable and exactly right; data layer dead.**

The master plan recorded LAS availability as UNKNOWN and pre-authorised falling back to argopy.
That fallback is still needed, but the reason is now specific and narrow, and it is very likely
temporary — so this should be re-probed before the freeze rather than written off.

---

## 1. What works

| probe | result |
|---|---|
| `https://las.incois.gov.in/` | 302 → `/las`, Apache, HSTS |
| `https://las.incois.gov.in/thredds/catalog.html` | **200 in 0.19 s** |
| `https://las.incois.gov.in/las/getCategories.do` | 200, JSON, 13 categories |
| `https://las.incois.gov.in/las/getDatasets.do` | 200, **17,007,907 bytes**, 52 datasets |

Port **80 is closed** (`Failed to connect ... after 21 s`) — HTTPS only. Certificate chain
validated with stock curl; no `certifi` override was needed.

The very first category returned is `ARGO DATA PRODUCTS`
(`942F0A82EED38D08763754130C47ECB5`), with four children:

- `Argo SST Weekly`
- `Argo Value Added Products`
- **`Gridded Product based on Kessler-McCreary Methodology`**
- **`Gridded Product based on Variational Analysis Methodology`**

Both gridded products are exactly the class of product the PS names.

## 2. The two gridded Argo datasets

| | Kessler-McCreary | Variational Analysis (VAM) |
|---|---|---|
| catid | `id-a292ce89c6` | `id-76d076139f` |
| server file | `/home/las/datasets/argo/argo_10d.nc` | `/home/las/datasets/argo/argo_10dv.nc` |
| grid | 1° × 1° | 1° × 1° |
| x | 30.5–119.5 °E (90 pts, step 1) | same |
| y | 29.5 °S – 29.5 °N (60 pts, step 1) | same |
| depths | 24 levels (below) | 24 levels (identical) |
| time | 10-Jan-2001 → 30-Jul-2026, 10-day, 921 steps | 10-Jan-2004 → 30-Jul-2026, 10-day |
| variables | `T_ANALYZED` (degs), `S_ANALYZED` (psu), `*_RMSE`, `*_STDEV`, obs counts — 12 total | `TEMP` (degs), `SAL` (PSU), `TERR`, `SERR` — 4 total |

Depth levels, both products:

```
5 10 20 30 50 75 100 125 150 200 250 300 400 500 600 700 800 900 1000 1200 1400 1600 1800 2000
```

OPeNDAP endpoint (confirmed as the catalogue's declared access URL):

```
https://las.incois.gov.in/thredds/dodsC/las/id-76d076139f/data_home_las_datasets_argo_argo_10dv.nc.jnl
```

## 3. What does not work

Three independent retrieval routes, all failing in the same place:

| route | result |
|---|---|
| `dodsC/.../argo_10dv.nc.jnl.dds` | **hang, 0 bytes at 240 s** |
| `dodsC/.../argo_10dv.nc.jnl.html` | **hang, 0 bytes at 75 s** |
| `dodsC/.../argo_10d.nc.jnl.dds` (Kessler-McCreary) | **hang, 0 bytes at 75 s** |
| `ftds_url` as advertised in `getDatasets.do` | **404** |
| `las/ProductServer.do` with a valid `Data_Extract_netCDF` request | 200 in 1.2 s, HTML: *"An error occurred in the service that was creating your product."* |

The catalogue answers in 0.19 s while every data request hangs or errors, and the `.jnl` files
are 44-byte Ferret journal stubs (mtime `2026-08-31T04:40:51Z`). So this is **the Ferret /
F-TDS materialisation backend being down, not the host, not the network, and not us.** Nothing
about the request path is wrong — `ProductServer.do` accepted our XML and got as far as trying
to build the product.

## 4. Why this matters more than it looks

The metadata alone settles three questions that were open:

1. **Depths line up almost perfectly.** 14 of our 15 `config.DEPTHS` are *exact* INCOIS levels.
   Only depth **0 m** is absent — INCOIS starts at 5 m. Validation therefore needs **no vertical
   interpolation** at 14 of 15 depths, and depth 0 simply cannot be scored against INCOIS.

2. **Spatial overlap is ~98 %.** Our `REGION` is lat 5–30 °N, lon 45–105 °E. Longitude sits
   entirely inside 30.5–119.5 °E. Latitude is covered to 29.5 °N, so only the **29.5–30 °N strip
   (0.5° of 25°) falls outside** the INCOIS grid.

3. **VAM carries salinity.** `SAL` (PSU) alongside `TEMP`. All four local Argo parquets are
   temperature-only, which is why stage-2 S and ρ are unscored. This product would fix that.

Two mismatches must be handled explicitly when it does come back:

- **Resolution.** INCOIS is 1°, we are 0.25° — 4× coarser. Our field must be aggregated to their
  1° boxes, not the reverse; interpolating a 1° analysis onto 0.25° would invent structure.
- **Time.** INCOIS is a 10-day mean, we are daily. Our daily output must be averaged into their
  10-day windows before any RMSE is computed. Comparing a daily field to a 10-day mean would
  charge us for variance the product does not resolve.

## 5. Consequence for the plan

- **Req 16 is achievable in principle** — the right product exists, at the right depths, covering
  our window. It is not a wrong-product problem, as §8 of the master plan feared. It is an outage.
- **A8 proceeds on argopy now**, with this deviation documented, per contract §12 and §51.
- **Re-probe before the freeze.** `scripts/phase2/probe_incois_las.py` reproduces every check
  above and exits non-zero while the data layer is down. If Ferret recovers, the OPeNDAP URL and
  variable names in §2 are all a downloader needs.
- `tscast_output_schema.md:93` declares `"argopy" | "incois_las"`. `incois_las` stays unproduced,
  and should stay that way until real bytes have been read from the endpoint.

**No downloader was written.** The plan says "downloader if reachable"; the data is not reachable,
and a downloader that has never once retrieved a byte is not evidence of anything.
