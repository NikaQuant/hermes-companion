# Hermes Companion web client

## Canonical release source

```text
standalone/   dependency-free PWA source used by v0.3
 dist/         generated production artifact
 src/          optional React/Vite prototype track
```

Build the shipped PWA:

```bash
python ../../scripts/build-web.py
```

The build hashes the JavaScript/CSS assets, injects a versioned service-worker cache, copies icons/manifest, and writes `dist/`.

The PWA never contains Hermes profile keys. It authenticates to the FastAPI Companion bridge with revocable Companion device tokens.

## Capacitor

`capacitor.config.ts` wraps `dist/` for Android. Install dependencies and run:

```bash
npm run android:add
npm run android:sync
npm run android:open
```

A real phone must use the private HTTPS bridge URL; its own `127.0.0.1` is not the Windows Hermes host.
