# Money is always in CENTS (whole numbers). No floats anywhere.


def parse_dollars(text: str) -> int:
    """Turn what the cashier typed, like "20" or "22.66" or "$30.5", into cents."""
    cleaned = text.strip().replace("$", "").replace(",", "")
    if cleaned == "":
        raise ValueError("Enter an amount")
    if cleaned.count(".") > 1:
        raise ValueError(f"Not a valid amount: {text}")

    dollars, _, cents = cleaned.partition(".")
    if dollars == "":
        dollars = "0"
    if not dollars.isdigit() or (cents and not cents.isdigit()) or len(cents) > 2:
        raise ValueError(f"Not a valid amount: {text}")

    cents = cents.ljust(2, "0")          # "5" -> "50", "" -> "00"
    return int(dollars) * 100 + int(cents)


def cash_change(total: int, tendered: int) -> int:
    """INV-4: amount given >= total, and change = amount given - total."""
    if total < 0 or tendered < 0:
        raise ValueError("Money cannot be negative")
    if tendered < total:
        raise ValueError("Not enough cash")
    return tendered - total


def quick_cash_options(total: int) -> list[int]:
    """Buttons for the cashier: exact amount, next $5, next $10, $20, $50, $100."""
    next_5 = (total + 499) // 500 * 500
    next_10 = (total + 999) // 1000 * 1000
    candidates = [total, next_5, next_10, 2000, 5000, 10000]
    options = sorted({c for c in candidates if c >= total and c > 0})
    return options[:5]