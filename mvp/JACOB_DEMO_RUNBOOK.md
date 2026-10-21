# Jacob's Shopify demo: quick checklist

Assumes Docker Desktop is running, images are built, and `.env`/published demo data are ready. Use **window A** for Compose and **window B** for Cloudflare. Never share credentials, `.env`, or OTP codes.

## 1. Start the demo (PowerShell)

In window A:

```powershell
cd "C:\Users\omidp\OneDrive\Documents\shopify-analytics-poc"
$env:REMOTE_DEMO_READ_ONLY = "true"
docker compose up -d --force-recreate --wait --wait-timeout 180 app streamlit
if ($LASTEXITCODE -ne 0) { throw "Startup failed; do not start Cloudflare." }
docker compose ps
```

All three services (`postgres`, `app`, `streamlit`) must be healthy. Normal startup reuses images; **add `--build` only after code changes**. The environment override applies only to this PowerShell window; set it again in any new window used to recreate services.

## 2. Verify locally

Check both actual containers before sharing:

```powershell
docker compose exec -T app python -c "from runtime_config import remote_demo_read_only; assert remote_demo_read_only(); print('Backend: read-only=true')"
if ($LASTEXITCODE -ne 0) { throw "Backend is not read-only; stop." }
docker compose exec -T streamlit python -c "from runtime_config import remote_demo_read_only; assert remote_demo_read_only(); print('Dashboard: read-only=true')"
if ($LASTEXITCODE -ne 0) { throw "Dashboard is not read-only; stop." }
```

Open **http://localhost:8501**. Confirm **Read-only demo**, no active **Run Pipeline & Refresh** button, and working dataset/date/currency filters, KPI cards and charts. Backend read-only mode rejects pipeline triggers with HTTP 403, including valid-token requests.

## 3. Start Cloudflare (PowerShell)

Stop any earlier demo connector before starting another; do not leave parallel public URLs active. In window B:

```powershell
docker run --rm --pull always `
  --name jacob-demo-tunnel `
  --network shopify-analytics-poc_default `
  cloudflare/cloudflared:latest `
  tunnel --url http://streamlit:8501 `
  --allowed-mail "datumsphere@gmail.com" `
  --allowed-mail "jacob.w.bedard@gmail.com"
```

Require startup output showing **One-Time PIN** authentication and **Allowed recipients: 2 addresses**. Otherwise stop immediately; **never remove email authentication**. Forward only Streamlit: do not publish PostgreSQL/backend ports, mount the Docker socket, or pass credentials to this container.

## 4. Share access with Jacob

- Copy the **new** `https://...trycloudflare.com` root URL. Test it in a private browser with `datumsphere@gmail.com` and its emailed OTP; confirm the public dashboard is still read-only.
- Send only that URL to Jacob via **WhatsApp**. Tell him to enter **jacob.w.bedard@gmail.com** and use the verification code emailed to his own mailbox. No installation is needed.
- Keep **Docker Desktop, window B, the laptop and Internet connection running**; prevent laptop sleep. A restarted tunnel gets a new URL.

## 5. Stop the demo

Press **Ctrl+C in window B**. In window A, check that the named connector stopped:

```powershell
if (docker ps -q --filter 'name=^/jacob-demo-tunnel$') {
    docker stop jacob-demo-tunnel
}
docker ps --filter 'name=^/jacob-demo-tunnel$' --format '{{.Names}} {{.Status}}'
```

No running row should remain. Closing the terminal alone is not proof of shutdown. Also stop any other connector you used for this demo.

Optionally stop the POC from window A:

```powershell
docker compose down
```

**Never add `-v`**: preserve the database volume. Keep read-only protection enabled for future demos.

## 6. Three quick troubleshooting tips

1. **Dashboard not loading:** check health and review logs locally; redact before sharing.

   ```powershell
   docker compose ps
   docker compose logs --tail 30 app streamlit
   ```

2. **Email verification problems:** use the correct email, check junk mail, and restart login from the current root URL in a fresh private window. Use the newest code; do not reuse callback links or remove the allowlist.

3. **Cloudflare not working:** verify the network and connector logs. Compose must be healthy and the origin must remain `http://streamlit:8501`.

   ```powershell
   docker network inspect shopify-analytics-poc_default --format '{{.Name}}'
   docker logs --tail 30 jacob-demo-tunnel
   ```
