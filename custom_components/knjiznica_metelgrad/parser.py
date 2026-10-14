"""Parsiranje HTML-a korisničkih stranica Metelwin (Metelgrad).

Selektori su potvrđeni na snimkama stvarnih stranica (mapa `recon/`, izvan gita):

- `korisnik.php?page=citam` — svaka posudba je `div.col-sm-12` koji sadrži
  element s tekstom "Rok vraćanja: <datum>"; naslov je u `a.knaslink`, autor u
  `span.anaso`, a identifikator zapisa (`D…`) u poveznici naslova.
- `korisnik.php?page=prod` — posudbe se produžuju POST obrascem (`#formo`) s
  jednim `checkbox[name="prod[]"]` po primjerku (vrijednost `MK…`), plus skrivena
  polja `H`, `B` i `zahtjev`.

Modul je namjerno "glup": čisti HTML -> podatkovni model, bez mreže i bez Home
Assistant ovisnosti, pa se testira odvojeno od integracije (tests/test_parser.py).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from bs4 import BeautifulSoup, Tag

# Ovu poruku stranica vraća neprijavljenima (provjereno na živoj stranici).
LOGGED_OUT_MARKER = "samo za prijavljene korisnike"

# Hrvatski datum: 01.11.2026 / 1. 11. 2026.
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\.?")

# Oznaka retka "Rok vraćanja: 01.11.2026."
_DUE_LABEL_RE = re.compile(r"rok\s*vra[cć]anja", re.IGNORECASE)

# Identifikator zapisa (`sqlx` na citam, `item` na prod) u poveznici na knjigu.
_RECORD_KEY_RE = re.compile(r"[?&](?:sqlx|item)=([A-Za-z]{0,3}\d+)")

_BLOCK_CLASS = "col-sm-12"


@dataclass(frozen=True, slots=True)
class Loan:
    """Jedna posudba."""

    title: str
    author: str | None
    due_on: date
    record_key: str | None
    # Ispunjeno samo ako je knjižnica za tu posudbu ponudila produženje.
    renew_id: str | None = None

    @property
    def renewable(self) -> bool:
        """True ako je produženje ponuđeno na stranici za produženje."""
        return self.renew_id is not None

    def days_until(self, today: date) -> int:
        """Broj dana do roka vraćanja (negativno = rok je prošao)."""
        return (self.due_on - today).days

    def as_dict(self, today: date) -> dict[str, Any]:
        """Serijalizirani oblik za atribute senzora."""
        return {
            "title": self.title,
            "author": self.author,
            "due_on": self.due_on.isoformat(),
            "days_left": self.days_until(today),
            "renewable": self.renewable,
        }


@dataclass(frozen=True, slots=True)
class RenewOption:
    """Jedan primjerak ponuđen za produženje."""

    renew_id: str
    title: str
    due_on: date | None
    record_key: str | None


@dataclass(frozen=True, slots=True)
class RenewPage:
    """Obrazac za produženje i primjerci ponuđeni na njemu."""

    action: str
    checkbox_name: str
    hidden: dict[str, str]
    submit: tuple[tuple[str, str], ...]
    options: tuple[RenewOption, ...]

    def form_data(self, renew_ids: Iterable[str]) -> dict[str, Any]:
        """Podaci za POST kojima se produžuju navedeni primjerci."""
        data: dict[str, Any] = dict(self.hidden)
        data[self.checkbox_name] = list(renew_ids)
        data.update(self.submit)
        return data


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


def parse_loans(html: str) -> list[Loan]:
    """Izvuci posudbe sa stranice `page=citam`."""
    soup = BeautifulSoup(html, "html.parser")
    loans: list[Loan] = []
    for block in soup.find_all("div", class_=_BLOCK_CLASS):
        loan = _block_to_loan(block)
        if loan is not None:
            loans.append(loan)
    return loans


def parse_renew_page(html: str) -> RenewPage | None:
    """Izvuci obrazac za produženje sa stranice `page=prod`."""
    soup = BeautifulSoup(html, "html.parser")
    checkbox = _find_renew_checkbox(soup)
    if checkbox is None:
        return None
    form = checkbox.find_parent("form")
    if form is None:
        return None

    options: list[RenewOption] = []
    for block in form.find_all("div", class_=_BLOCK_CLASS):
        box = block.find("input", attrs={"name": checkbox["name"]})
        if box is None or not box.get("value"):
            continue
        title_element = _title_element(block)
        due_element = _label_element(block, _DUE_LABEL_RE)
        options.append(
            RenewOption(
                renew_id=box["value"],
                title=_text(title_element) if title_element else "",
                due_on=parse_date(_text(due_element)) if due_element else None,
                record_key=_record_key(title_element),
            )
        )

    return RenewPage(
        action=form.get("action", ""),
        checkbox_name=checkbox["name"],
        hidden={
            element["name"]: element.get("value", "")
            for element in form.find_all("input", attrs={"type": "hidden"})
            if element.get("name")
        },
        submit=tuple(
            (element["name"], element.get("value", ""))
            for element in form.find_all(["input", "button"], attrs={"type": "submit"})
            if element.get("name")
        ),
        options=tuple(options),
    )


def find_option(loan: Loan, page: RenewPage) -> RenewOption | None:
    """Pronađi primjerak koji odgovara posudbi.

    Prvo po identifikatoru zapisa (`D…`, isti na objema stranicama) i roku, zatim
    samo po identifikatoru, a na kraju po naslovu.
    """
    if loan.record_key:
        by_record = [option for option in page.options if option.record_key == loan.record_key]
        for option in by_record:
            if option.due_on == loan.due_on:
                return option
        if by_record:
            return by_record[0]

    normalized = _normalize(loan.title)
    for option in page.options:
        if _normalize(option.title) == normalized:
            return option
    return None


def with_renew_ids(loans: list[Loan], page: RenewPage | None) -> list[Loan]:
    """Zalijepi ponuđene identifikatore produženja na posudbe."""
    if page is None:
        return [replace(loan, renew_id=None) for loan in loans]

    used: set[str] = set()
    linked: list[Loan] = []
    for loan in loans:
        option = find_option(loan, page)
        if option is None or option.renew_id in used:
            linked.append(replace(loan, renew_id=None))
            continue
        used.add(option.renew_id)
        linked.append(replace(loan, renew_id=option.renew_id))
    return linked


def _block_to_loan(block: Tag) -> Loan | None:
    """Jedan blok posudbe -> Loan, ili None ako blok nije posudba."""
    due_element = _label_element(block, _DUE_LABEL_RE)
    if due_element is None:
        return None
    due_on = parse_date(_text(due_element))
    if due_on is None:
        return None

    title_element = _title_element(block)
    if title_element is None:
        return None
    title = _text(title_element)
    if not title:
        return None

    author_element = block.select_one("span.anaso")
    author = _text(author_element) if author_element else None

    return Loan(
        title=title,
        author=author or None,
        due_on=due_on,
        record_key=_record_key(title_element),
    )


def _label_element(block: Tag, pattern: re.Pattern[str]) -> Tag | None:
    """Najdublji element čiji tekst sadrži oznaku (npr. 'Rok vraćanja')."""
    candidates = [
        element
        for element in block.find_all(True)
        if pattern.search(element.get_text(" ", strip=True))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda element: len(element.find_all(True)))


def _title_element(block: Tag) -> Tag | None:
    """Element s naslovom knjige."""
    element = block.select_one("a.knaslink")
    if element is not None and element.get_text(strip=True):
        return element
    return None


def _record_key(element: Tag | None) -> str | None:
    """Identifikator zapisa iz poveznice na knjigu (npr. D21492)."""
    if element is None:
        return None
    match = _RECORD_KEY_RE.search(element.get("href", ""))
    return match.group(1) if match else None


def _find_renew_checkbox(soup: BeautifulSoup) -> Tag | None:
    """Prvi checkbox čije ime završava s `[]` (popis primjeraka za produženje)."""
    for element in soup.find_all("input", attrs={"type": "checkbox"}):
        name = element.get("name") or ""
        if name.endswith("[]"):
            return element
    return None


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _text(element: Tag) -> str:
    """Tekst elementa sa sažetim razmacima (HTML zna zalomiti naslov u više redaka)."""
    return " ".join(element.get_text(" ", strip=True).split())
