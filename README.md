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
uvicorn main:app
```

Keep the same secret across restarts. Changing it logs everyone out and breaks old tracker
links. Never commit it.

Open http://127.0.0.1:8000. The first start creates `sliceflow.db` with a demo menu and staff.

## Settings

| Environment variable | Meaning |
| --- | --- |
| `SLICEFLOW_SECRET` | Signs login sessions and tracker links. Required outside dev mode. |
| `SLICEFLOW_DEV` | `1`, `true`, `yes` or `on` allows the public default secret. Development only. |
| `SLICEFLOW_TZ` | Time zone for daily reports. Default: `America/New_York`. |

## Demo logins

| Name | Role | PIN |
| --- | --- | --- |
| Sita | Cashier | 1111 |
| Ram | Kitchen | 2222 |
| Pawan | Manager | 9999 |

Change these PINs before any real use. Five wrong PINs in a row lock an account for one minute.

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

## Test

```powershell
python -m pytest
```
