# inboxctl

Clean up a cluttered Outlook.com / Hotmail / Live mailbox from your own computer. inboxctl lists every sender in your inbox, tells you how each one can be unsubscribed, and acts only on the senders you tick.

- **Unsubscribe** for real: one-click (RFC 8058) requests, or the sender's `mailto:` address, sent from your own mailbox. Senders that only offer a web link are opened for you to finish by hand.
- **Block** future mail with an inbox rule per sender (mail goes straight to Deleted Items).
- **Sweep** existing mail from a sender into Deleted Items. Nothing is permanently deleted.
- **Keep** list for senders you never want touched.

Everything runs locally. There is no server, no account, no data collection. The only outbound traffic is to Microsoft Graph (your own mailbox) and to the unsubscribe endpoints you explicitly approve.

## For users: download and run

1. Download the latest build from the **Releases** page: `inboxctl.exe` (Windows) or `inboxctl-macos.zip` (macOS).
2. Double-click it. A browser tab opens with the inboxctl screen.
   - Windows will show **"Windows protected your PC"** the first time, because the app is not code-signed. Click **More info**, then **Run anyway**. This is the standard warning for any small program that does not pay for a signing certificate.
   - macOS: right-click the app, **Open**, confirm.
3. Click **Connect Microsoft account**. Sign in on the Microsoft page that opens and accept the permissions. If that page does not open, use the **Use a code instead** link.
4. The first scan starts by itself. A mailbox with 50,000 messages takes about 20 minutes; the progress shows in the log panel.
5. Tick senders, choose the actions (Unsubscribe, Block, Sweep), click **Apply to selected**, confirm.

Tips:

- Sort by **Msgs** and start with the biggest senders. Use the **3+ / 10+ / 25+ messages** filter.
- Old senders that stopped writing years ago do not need Unsubscribe; Sweep is enough.
- Banks, payment providers and airlines send transactional mail from the same addresses as marketing. Unsubscribe them, but think twice before Block.
- Mark anything important as **keep** so it disappears from the list and "select all" never picks it.
- Everything the app did is in the log file (see below). The block rules it created all start with `inboxctl block:` and can be removed in Outlook under Settings > Mail > Rules.

Where the app keeps its data (sign-in token, scan results, action log):

- Windows: `%LOCALAPPDATA%\inboxctl`
- macOS: `~/Library/Application Support/inboxctl`

Delete that folder to forget everything, or use **Sign out** in the app.

## For developers: run from source

Requires Python 3.10+.

```bash
git clone <repo> inboxctl && cd inboxctl
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m inboxctl            # starts the UI and opens the browser
python -m inboxctl scan       # scan from the terminal (after signing in once in the UI)
python -m inboxctl logout     # remove the cached token
```

Optional `config.json` (next to the executable, or in the data folder):

```json
{
  "client_id": "your-own-app-registration-id",
  "authority_tenant": "consumers",
  "folders": ["inbox"],
  "max_messages_per_folder": 0,
  "port": 8765
}
```

- `folders`: well-known names (`inbox`, `archive`) or display names. Junk is deliberately excluded.
- `max_messages_per_folder`: cap for a quick run; `0` scans everything.
- `authority_tenant`: `consumers` for personal accounts, `common` to also allow work/school accounts.

### About the client id

By default inboxctl authenticates with the public client id of **Microsoft Graph Command Line Tools**, the same application behind `Connect-MgGraph`. It supports personal Microsoft accounts, needs no app registration, and shows Microsoft's own consent screen. For a wider public release you should register your own application in Microsoft Entra (requires a tenant, for example an Azure free account) and set `client_id` in `config.json`.

### Build the executables

Builds are produced by GitHub Actions (`.github/workflows/build.yml`) on every push to `main`, and attached to a GitHub Release when you push a tag:

```bash
git tag v0.2.0 && git push --tags
```

Local build: `pip install pyinstaller && pyinstaller inboxctl.spec` (produces `dist/inboxctl.exe` on Windows, `dist/inboxctl.app` on macOS). PyInstaller does not cross-compile, so the Windows build must run on Windows or in CI.

## What "unsubscribe method" means

| Badge | Meaning | What inboxctl does |
|---|---|---|
| `one-click` | Sender ships `List-Unsubscribe` + `List-Unsubscribe-Post` headers (RFC 8058). Mandatory for bulk senders to Gmail/Yahoo since 2024. | Sends the HTTPS POST. Reliable, instant. |
| `mailto` | Sender offers a `mailto:` unsubscribe address. | Sends the e-mail from your mailbox via Graph (not saved to Sent Items). |
| `link` | Only a web URL, no one-click header. Usually needs a confirmation page. | Lists the URL for you to open. Nothing is fetched automatically. |
| `none` | No unsubscribe header at all. | Only Block and Sweep are meaningful. "body link?" means the message body mentions unsubscribe: open one message and click it. |

Senders have up to 48 hours to honor a request under the RFC 8058 rules. Combine Unsubscribe with Block if you want silence immediately.

## Project layout

```
inboxctl/
  config.py     defaults, data folder, PyInstaller-aware paths
  auth.py       MSAL sign-in (browser redirect or device code), token cache, AuthManager
  graph.py      Graph client: paging, retry on 429, $batch
  scanner.py    scan folders, aggregate per sender, parse List-Unsubscribe headers
  actions.py    unsubscribe / sweep / block / keep, action log
  server.py     FastAPI endpoints, background jobs
  static/index.html   the UI
  __main__.py   entry point
run.py          PyInstaller entry
inboxctl.spec   PyInstaller spec (one-file, windowed)
```

## Roadmap

- Gmail adapter (Google OAuth app in Testing mode: free, up to 100 users, no CASA audit)
- Domain-level block (whole `@domain`)
- Scheduled re-scan with a digest of new senders
- Code signing for Windows and macOS to remove the first-run warnings
