"""HTTP klijent za korisničke stranice Metelwin (library.foi.hr).

Klijent drži vlastitu aiohttp sesiju s vlastitim cookie jarom: sesijski kolačić se
zove `korisnik<B>` (npr. `korisnik11`) i isti je za sve kartice iste knjižnice, pa
zajednička HA sesija ne bi mogla istovremeno držati dvije prijavljene kartice.
"""

from __future__ import annotations

import aiohttp

from .const import BASE_URL, DEFAULT_LIBRARY_ID, LOANS_PATH, LOGIN_PATH, USER_AGENT
from .parser import (
    Loan,
    RenewPage,
    find_option,
    is_logged_out,
    parse_loans,
    parse_renew_page,
    with_renew_ids,
)


class MetelgradError(Exception):
    """Greška u komunikaciji s knjižnicom."""


class MetelgradAuthError(MetelgradError):
    """Prijava nije uspjela ili je sesija odbijena."""


class MetelgradClient:
    """Prijava, dohvat posudbi i produženje."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        library_id: str = DEFAULT_LIBRARY_ID,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._library_id = library_id

    def _page_url(self, page: str) -> str:
        return f"{BASE_URL}{LOANS_PATH}?page={page}&B={self._library_id}&H="

    async def async_login(self) -> None:
        """Prijavi se i pusti da sesija zapamti kolačić."""
        data = {
            "username": self._email,
            "password": self._password,
            "B": self._library_id,
            "bookid": "",
            "refURL": f"{BASE_URL}/lib/",
            "navo": "1",
        }
        async with self._session.post(
            f"{BASE_URL}{LOGIN_PATH}",
            data=data,
            headers={"User-Agent": USER_AGENT},
        ) as response:
            response.raise_for_status()

    async def async_fetch_loans(self) -> list[Loan]:
        """Trenutne posudbe, s oznakom je li produženje ponuđeno."""
        html = await self._async_get_authenticated(self._page_url("citam"))
        return with_renew_ids(parse_loans(html), await self.async_renew_page())

    async def async_renew_page(self) -> RenewPage | None:
        """Obrazac za produženje i primjerci ponuđeni na njemu."""
        html = await self._async_get_authenticated(self._page_url("prod"))
        return parse_renew_page(html)

    async def async_renew(self, loan: Loan) -> None:
        """Pošalji zahtjev za produženje za jednu posudbu."""
        page = await self.async_renew_page()
        if page is None:
            raise MetelgradError("Stranica za produženje nije dostupna.")

        option = find_option(loan, page)
        if option is None:
            raise MetelgradError(f"'{loan.title}' nije ponuđena za produženje.")

        async with self._session.post(
            page.action,
            data=page.form_data([option.renew_id]),
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            body = await response.text()
        if is_logged_out(body):
            raise MetelgradAuthError("Sesija je istekla tijekom produženja.")

    async def _async_get_authenticated(self, url: str) -> str:
        """GET koji se sam prijavi ako sesija više ne vrijedi."""
        html = await self._async_get_text(url)
        if not is_logged_out(html):
            return html

        await self.async_login()
        html = await self._async_get_text(url)
        if is_logged_out(html):
            raise MetelgradAuthError(
                "Prijava nije uspjela. Provjeri e-mail, lozinku i oznaku knjižnice."
            )
        return html

    async def _async_get_text(self, url: str) -> str:
        async with self._session.get(url, headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            return await response.text()
