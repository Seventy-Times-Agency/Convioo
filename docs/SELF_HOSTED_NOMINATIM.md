# Self-hosted Nominatim + Overpass

The public OpenStreetMap endpoints (`nominatim.openstreetmap.org`,
`overpass-api.de`) work great in development and at low traffic, but
they share a soft rate limit across our entire IP. With more than a
handful of concurrent users — or one power user grinding 500
leads/day — searches start timing out and we get 429s back. Pointing
the OSM collectors at our own instances removes that ceiling.

This is purely an infra swap. No code changes — flip
`NOMINATIM_BASE_URL` / `OVERPASS_BASE_URL` and the running app
picks them up.

## What you need

| Component  | Recommended box                          | Approx cost   |
| ---------- | ---------------------------------------- | ------------- |
| Nominatim  | Hetzner CX22 (2 vCPU / 4 GB RAM / 80 GB) | ~€4.5 / month |
| Overpass   | Hetzner CX32 (4 vCPU / 8 GB RAM / 80 GB) | ~€8 / month   |

Disk usage is dominated by the OSM dump for the regions you import.
Europe + North America together fit comfortably in 80 GB; the whole
planet wants closer to 200 GB.

## 1. Nominatim (geocoding)

The maintained image is `mediagis/nominatim`. Spin up with a single
Compose file and an OSM extract URL:

```yaml
# docker-compose.nominatim.yml
services:
  nominatim:
    image: mediagis/nominatim:4.4
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      PBF_URL: https://download.geofabrik.de/europe-latest.osm.pbf
      REPLICATION_URL: https://download.geofabrik.de/europe-updates/
      IMPORT_WIKIPEDIA: "false"
      THREADS: 4
    volumes:
      - nominatim_data:/var/lib/postgresql/14/main

volumes:
  nominatim_data:
```

```bash
docker compose -f docker-compose.nominatim.yml up -d
# Initial import of europe-latest takes ~3-6h on a CX22.
# Watch progress:
docker compose -f docker-compose.nominatim.yml logs -f nominatim
```

Once `Setup finished.` appears in the logs, point Convioo at it:

```env
NOMINATIM_BASE_URL=https://nominatim.your-domain.com
```

Front it with Caddy / Traefik for HTTPS. No auth needed — Convioo
sends a `User-Agent: Convioo/...` header so you can rate-limit by
that if the host gets crawled.

## 2. Overpass (POI queries)

Same pattern with `wiktorn/overpass-api`:

```yaml
# docker-compose.overpass.yml
services:
  overpass:
    image: wiktorn/overpass-api:latest
    restart: unless-stopped
    ports:
      - "12345:80"
    environment:
      OVERPASS_META: "yes"
      OVERPASS_MODE: init
      OVERPASS_PLANET_URL: https://download.geofabrik.de/europe-latest.osm.bz2
      OVERPASS_DIFF_URL: https://download.geofabrik.de/europe-updates/
      OVERPASS_RULES_LOAD: 10
    volumes:
      - overpass_db:/db

volumes:
  overpass_db:
```

After import (~6-12h):

```env
OVERPASS_BASE_URL=https://overpass.your-domain.com/api/interpreter
```

## Verify

```bash
# Geocode test
curl "$NOMINATIM_BASE_URL/search?q=Berlin&format=json&limit=1"

# Overpass test (count cafes around 52.52,13.40)
curl -X POST "$OVERPASS_BASE_URL" \
  --data-urlencode 'data=[out:json];node["amenity"="cafe"](around:1000,52.52,13.40);out count;'
```

Both should return JSON within a second. If they do, set the env vars
on Railway and ship — the next search picks them up automatically.

## When to revert

- Disk full: shrink the import region or upgrade the box. The PBF
  importer is destructive — restoring the public default is just
  unsetting the env vars; Convioo falls back instantly with no
  redeploy needed.
- The host gets DDOSed: same — unset the env vars. Don't try to
  patch a public OSM mirror on a fire.
