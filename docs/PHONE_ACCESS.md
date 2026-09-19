# Phone access (Tailscale)

The Companion service listens only on `127.0.0.1:8787` — your phone cannot reach it directly.
Tailscale makes a private, encrypted link between your computer and your phone. Nobody
else can see it, and nothing is opened to the internet.

## One-time setup

1. Install **Tailscale** on the computer (<https://tailscale.com/download>) and sign in
   (Google, Microsoft, GitHub… any one account).
2. Install **Tailscale** on the phone (App Store / Play Store) and sign in with the **same account**.
3. On the computer, in an Administrator PowerShell inside the Companion folder:

   ```powershell
   tailscale serve --bg 8787
   ```

   The first time it may print a link “Serve is not enabled on your tailnet… visit https://login.tailscale.com/…”.
   Open that link in a browser, click **Enable**, then run the command again.

4. It prints your private address, like `https://<computer-name>.<something>.ts.net`.
   Register it with the Companion so passkeys and secure cookies work:

   ```powershell
   .\scripts\set-public-url.ps1 -Url https://<computer-name>.<something>.ts.net
   ```

   Then restart the service:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\reload-bridge.ps1
   ```

## On the phone

1. Open the Tailscale app → it must say **Connected**.
2. Open the `https://…ts.net` address in Safari (iPhone) or Chrome (Android).
3. Sign in with the email/password from the install. Leave **Server URL** (under Advanced) blank.
4. Share button → **Add to Home Screen**. Now it opens like a normal app.
5. On Home, the **Get set up** card walks you through: alerts (push notifications) and a passkey (Face ID / fingerprint sign-in).

## Checks

- Under the **Hermes** logo the app shows `v<version> · <build>`. That tells you which build you're running.
- If sign-in says *Can't reach the computer*: the phone's Tailscale is off, or the address is wrong.
- `tailscale serve status` on the computer shows what is being served.

## Turn it off

```powershell
tailscale serve --https=443 off
```

Never expose ports 8642 or 9119 (Hermes itself). Only 8787 goes through Tailscale.
