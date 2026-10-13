"""HTTP klijent za korisničke stranice Metelwin (library.foi.hr).

Klijent drži vlastitu aiohttp sesiju s vlastitim cookie jarom: sesijski kolačić se
zove `korisnik<B>` (npr. `korisnik11`) i isti je za sve kartice iste knjižnice, pa
zajednička HA sesija ne bi mogla istovremeno držati dvije prijavljene kartice.
"""

from __future__ import annotations

import aiohttp

from .const import BASE_URL, DEFAULT_LIBRARY_ID, LOANS_PATH, LOGIN_PATH, USER_AGENT
from .parser import Loan, is_logged_out, parse_loans


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

    @property
    def loans_url(self) -> str:
        """URL korisničke stranice s posudbama."""
        return f"{BASE_URL}{LOANS_PATH}?page=citam&B={self._library_id}&H="

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
        """Vrati trenutne posudbe; po potrebi se prvo (ponovno) prijavi."""
        html = await self._async_loans_html()
        if is_logged_out(html):
            await self.async_login()
            html = await self._async_loans_html()
            if is_logged_out(html):
                raise MetelgradAuthError(
                    "Prijava nije uspjela. Provjeri e-mail, lozinku i oznaku knjižnice."
                )
        return parse_loans(html, BASE_URL)

    async def async_renew(self, loan: Loan) -> None:
        """Produži posudbu preko poveznice koju je ponudila sama stranica."""
        if loan.renew_url is None:
            raise MetelgradError(f"'{loan.title}' nije moguće produžiti.")
        async with self._session.get(
            loan.renew_url,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            body = await response.text()
        if is_logged_out(body):
            raise MetelgradAuthError("Sesija je istekla tijekom produženja.")

    async def _async_loans_html(self) -> str:
        async with self._session.get(
            self.loans_url,
            headers={"User-Agent": USER_AGENT},
        ) as response:
            response.raise_for_status()
            return await response.text()
