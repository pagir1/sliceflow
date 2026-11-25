# SliceFlow

A pizza shop point-of-sale web app: cashier screen, kitchen display, customer board,
QR order tracking and a manager screen. Built with FastAPI, SQLModel (SQLite) and HTMX.

## Set up (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

For local development:

```powershell
$env:SLICEFLOW_DEV = "1"
uvicorn main:app --reload
```

For real use, set a private secret instead. The app refuses to start without one.

```powershell
python -c "import secrets; print(secrets.token_hex(32))"    # make one, once
$env:SLICEFLOW_SECRET = "<the value printed above>"
$env:SLICEFLOW_PIN_CASHIER = "<4 digits>"     # the PINs are needed on the first start only
$env:SLICEFLOW_PIN_KITCHEN = "<4 digits>"
$env:SLICEFLOW_PIN_MANAGER = "<4 digits>"
uvicorn main:app
```

Keep the same secret across restarts. Changing it logs everyone out and breaks old tracker
links. Never commit it.

Outside dev mode the login cookie is HTTPS-only, so staff on other devices need an `https://`
address. Plain `http://` over a local network works only in dev mode.

Open http://127.0.0.1:8000. The first start creates `sliceflow.db` with a demo menu and staff.

## Settings

| Environment variable | Meaning |
| --- | --- |
| `SLICEFLOW_SECRET` | Signs login sessions and tracker links. Required outside dev mode. |
| `SLICEFLOW_DEV` | `1`, `true`, `yes` or `on` allows the public default secret. Development only. |
| `DATABASE_URL` | Where the database is. Default: `sqlite:///sliceflow.db`. |
| `SLICEFLOW_PIN_CASHIER`, `SLICEFLOW_PIN_KITCHEN`, `SLICEFLOW_PIN_MANAGER` | 4-digit staff PINs, used when the staff are first created. Required then outside dev mode, where the demo PINs are refused. |
| `SLICEFLOW_TZ` | Time zone for daily reports. Default: `America/New_York`. |

## Demo logins (dev mode only)

| Name | Role | PIN |
| --- | --- | --- |
| Sita | Cashier | 1111 |
| Ram | Kitchen | 2222 |
| Pawan | Manager | 9999 |

Outside dev mode the same people are created with the PINs from the settings above. Changing
those settings later does not change the PINs of staff already in the database. A database
that was created with the demo PINs keeps them, so never deploy one.

Five wrong PINs in a row lock an account for one minute.

## Screens

| Path | Who | What |
| --- | --- | --- |
| `/login` | Everyone | Choose a name and enter a PIN |
| `/` | Cashier, manager | Take orders, payment and pickup |
| `/kitchen` | Kitchen, manager | Cook orders and mark them ready |
| `/manager` | Manager | Daily sales, paid but unsent orders, voids, menu |
| `/board` | Public | Orders being prepared and ready |
| `/track/{order}/{token}` | Customer | Live order tracker, opened from the QR code |

Each login has its own cart. Logging out is blocked while that cart is paid but not sent to
the kitchen. Card payments are simulated; no card data is handled.

## Deploy to Render

1. Push this repository to GitHub.
2. In Render choose **New > Blueprint** and pick the repository. Render reads `render.yaml`.
3. Fill in the values Render asks for: `SLICEFLOW_SECRET` (make one with the command under
   [Run](#run)) and three 4-digit PINs. The demo PINs are refused.
4. After the deploy, open the `https://....onrender.com` address and log in.

The start command trusts Render's proxy headers, so QR tracker links use `https://`.
Do not set `SLICEFLOW_DEV` on Render.

**The free plan does not keep data.** Its disk is wiped on every deploy, restart and spin-down
(after 15 minutes without visitors), and the app starts again with a fresh menu and no orders.
Use it for demos only. To keep data, move to a paid plan, attach a persistent disk at
`/var/data` and set `DATABASE_URL` to `sqlite:////var/data/sliceflow.db` (four slashes).

**Railway (later):** use the same environment variables and start command as in `render.yaml`,
attach a volume, and point `DATABASE_URL` at a file on it.

## Test

```powershell
python -m pytest
```
