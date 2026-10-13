"""Parsiranje HTML-a korisničkih stranica Metelwin (Metelgrad).

Modul je namjerno "glup": samo čisti HTML -> podatkovni model, bez mreže i bez
Home Assistant ovisnosti, pa se može testirati običnim Pythonom (tests/test_parser.py).

STATUS VERIFIKACIJE
-------------------
Struktura stranice `korisnik.php?page=citam` još NIJE potvrđena na stvarnom HTML-u
prijavljene sesije. Oblik koji ovaj modul očekuje (tablica posudbi s retkom po knjizi,
datumom u formatu d.m.yyyy i poveznicom `page=prod` za produženje) pokriven je
sintetičkim testom. Nakon što stigne pravi snimak, prilagoditi `_due_column_index`
i `_row_to_loan` — ostatak integracije ne ovisi o HTML-u.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

# Ovu poruku stranica vraća neprijavljenima (provjereno na živoj stranici).
LOGGED_OUT_MARKER = "samo za prijavljene korisnike"

# Hrvatski datum: 5.10.2026. / 05. 10. 2026
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\.?")

# Poveznica za produženje produženja u Metelwinu ide na stranicu "prod".
_RENEW_HREF = "page=prod"

# Naslovi stupaca koji označavaju rok vraćanja.
_DUE_HEADER_RE = re.compile(r"rok|vra[cć]|povrat", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Loan:
    """Jedna posudba."""

    title: str
    author: str | None
    due_on: date | None
    renew_url: str | None

    @property
    def renewable(self) -> bool:
        """True ako je za ovu posudbu na stranici ponuđeno produženje."""
        return self.renew_url is not None

    def days_until(self, today: date) -> int | None:
        """Broj dana do roka vraćanja (negativno = rok je prošao)."""
        if self.due_on is None:
            return None
        return (self.due_on - today).days

    def as_dict(self, today: date | None = None) -> dict[str, Any]:
        """Serijalizirani oblik za atribute senzora."""
        return {
            "title": self.title,
            "author": self.author,
            "due_on": self.due_on.isoformat() if self.due_on else None,
            "days_left": self.days_until(today) if today else None,
            "renewable": self.renewable,
        }


def is_logged_out(html: str) -> bool:
    """True ako je odgovor stranica 'prijavite se' umjesto podataka."""
    return LOGGED_OUT_MARKER in html.casefold()


def parse_date(text: str) -> date | None:
    """Prvi hrvatski datum iz teksta, ili None."""
    match = _DATE_RE.search(text or "")
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_loans(html: str, base_url: str) -> list[Loan]:
    """Izvuci posudbe iz HTML-a stranice `page=citam`."""
    soup = BeautifulSoup(html, "html.parser")
    loans: list[Loan] = []
    for table in soup.find_all("table"):
        due_column = _due_column_index(table)
        for row in table.find_all("tr"):
            loan = _row_to_loan(row, base_url, due_column)
            if loan is not None:
                loans.append(loan)
    return loans


def _due_column_index(table: Tag) -> int | None:
    """Indeks stupca s rokom vraćanja, iz zaglavlja tablice."""
    for row in table.find_all("tr"):
        headers = row.find_all("th")
        if not headers:
            continue
        for index, header in enumerate(headers):
            if _DUE_HEADER_RE.search(header.get_text(" ", strip=True)):
                return index
        return None
    return None


def _row_to_loan(row: Tag, base_url: str, due_column: int | None) -> Loan | None:
    """Jedan redak tablice -> Loan, ili None ako redak nije posudba."""
    cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
    if len(cells) < 2:
        return None

    renew_url = _renew_url(row, base_url)
    due_on = _due_date(cells, due_column)
    if due_on is None and renew_url is None:
        return None

    title = cells[0]
    if not title:
        return None

    author = cells[1] if len(cells) > 2 and parse_date(cells[1]) is None else None
    return Loan(title=title, author=author, due_on=due_on, renew_url=renew_url)


def _due_date(cells: list[str], due_column: int | None) -> date | None:
    """Rok vraćanja iz retka; ako zaglavlje nije prepoznalo stupac, uzmi zadnji datum."""
    if due_column is not None and due_column < len(cells):
        due_on = parse_date(cells[due_column])
        if due_on is not None:
            return due_on
    dates = [parsed for cell in cells for parsed in [parse_date(cell)] if parsed is not None]
    return dates[-1] if dates else None


def _renew_url(row: Tag, base_url: str) -> str | None:
    """Apsolutni URL za produženje ove posudbe, ako postoji."""
    for anchor in row.find_all("a", href=True):
        if _RENEW_HREF in anchor["href"]:
            return urljoin(base_url, anchor["href"])
    return None
