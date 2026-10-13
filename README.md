# Knjižnica Metelgrad → Home Assistant

Home Assistant integracija za korisnički račun knjižnice **Metelgrad**
(`library.foi.hr`, dječji odjel): popis trenutno posuđenih knjiga, rok vraćanja,
produženje i podsjetnici preko Home Assistant automatizacija.

Namjena: roditelj koji redovno kasni s vraćanjem dječjih knjiga dobije
notifikaciju na mobitel prije roka i može produžiti bez traženja po webu.

> **Osobna upotreba.** Integracija se prijavljuje na tvoj vlastiti korisnički
> račun i čita tvoje vlastite podatke. Stranica knjižnice eksplicitno zabranjuje
> automatizirano izvlačenje podataka (`noai` meta oznaka + tekst u podnožju), pa
> je polling namjerno rijedak (zadano jednom dnevno). Prije širenja dalje od
> vlastitog kućanstva provjeri uvjete korištenja knjižnice.

## Kako radi

```
HA config entry (kartica)                       Home Assistant
┌─────────────────────────────┐                 ┌────────────────────────────────┐
│ e-mail + lozinka + B=11     │                 │ sensor.*_posudbe               │
└──────────────┬──────────────┘                 │ sensor.*_rok_vracanja          │
               │                                │ sensor.*_dana_do_roka          │
      POST /auth/loaut.php  (prijava)           │ button.*_produzi_sve           │
      GET  /lib/korisnik.php?page=citam  ──────▶│ servis knjiznica_metelgrad.renew│
      GET  .../korisnik.php?page=prod (produži) └────────────────────────────────┘
```

- Prijava: `POST https://library.foi.hr/auth/loaut.php` (polja `username`,
  `password`, `B`, `bookid`, `refURL`, `navo`).
- Posudbe: `GET https://library.foi.hr/lib/korisnik.php?page=citam&B=11&H=`
- Produženje: poveznica na `...page=prod...` koju sama stranica nudi za pojedinu
  posudbu (integracija ne izmišlja parametre).
- Svaka kartica ima **vlastitu HTTP sesiju i vlastiti cookie jar**: sesijski
  kolačić se zove `korisnik11` i identičan je za sve kartice iste knjižnice, pa
  bi zajednička sesija pomiješala dvije prijavljene kartice.

## Instalacija (Home Assistant u Dockeru)

1. Kopiraj mapu `custom_components/knjiznica_metelgrad` u svoj HA config:

   ```bash
   cp -r custom_components/knjiznica_metelgrad /putanja/do/ha/config/custom_components/
   ```

   Ako `custom_components` ne postoji u configu, stvori ga.

2. Restartaj Home Assistant.

3. **Postavke → Uređaji i usluge → Dodaj integraciju → Knjižnica Metelgrad** i
   upiši:
   - naziv kartice (npr. ime djeteta — koristi se u nazivima entiteta),
   - e-mail i lozinku s kojima se prijavljuješ na `library.foi.hr`,
   - oznaku knjižnice `B` (za Metelgrad dječji odjel: `11`).

   Za svako dijete dodaj integraciju ponovno — svaka kartica je zaseban unos.

4. U opcijama integracije podesi interval provjere (zadano 24 h).

> Minimalna verzija: Home Assistant 2025.1.

## Entiteti

Za karticu `Ana` (naziv koji upišeš pri dodavanju):

| Entitet | Značenje |
| --- | --- |
| `sensor.ana_posudbe` | broj trenutno posuđenih knjiga |
| `sensor.ana_rok_vracanja` | najbliži rok vraćanja (datum) |
| `sensor.ana_dana_do_roka` | broj dana do najbližeg roka (negativno = rok je prošao) |
| `button.ana_produzi_sve` | produžuje sve posudbe koje knjižnica nudi kao produžive |

Senzor `sensor.ana_posudbe` nosi i atribute:

```yaml
loans:
  - title: "Mali princ"
    author: "Saint-Exupéry, Antoine de"
    due_on: "2026-10-18"
    days_left: 5
    renewable: true
renewable_count: 2
overdue_count: 0
```

Za automatizacije koristi `due_on` (apsolutni datum, ne zastarijeva između
provjera). `days_left` se osvježava samo pri provjeri.

## Notifikacije

Gotov blueprint: `blueprints/automation/knjiznica_metelgrad/podsjetnik_rok_vracanja.yaml`.

1. Kopiraj datoteku u `config/blueprints/automation/knjiznica_metelgrad/`.
2. **Postavke → Automatizacije → Novi → Blueprint** → odaberi
   *Knjižnica Metelgrad: podsjetnik na rok vraćanja*.
3. Odaberi senzor posudbi, broj dana prije roka (npr. 3) i notifikacijsku
   uslugu (npr. `notify.mobile_app_ana`).

Blueprint šalje jednu notifikaciju u trenutku kad najbliži rok uđe u zadani
prozor. Bez blueprints može i ručno:

```yaml
automation:
  - alias: "Knjižnica – podsjetnik 3 dana prije roka"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.ana_dana_do_roka
        below: 3
    actions:
      - action: notify.mobile_app_ana
        data:
          title: "📚 Rok vraćanja"
          message: >-
            {{ state_attr('sensor.ana_posudbe', 'loans')
               | selectattr('due_on', 'ne', None)
               | map(attribute='title') | join(', ') }}
```

### Produženje iz notifikacije (akcijski gumb)

Mobilna aplikacija može poslati notifikaciju s gumbom koji poziva servis:

```yaml
automation:
  - alias: "Knjižnica – akcija iz notifikacije"
    triggers:
      - trigger: event
        event_type: mobile_app_notification_action
        event_data:
          action: RENEW_LIBRARY_BOOKS
    actions:
      - action: knjiznica_metelgrad.renew
        data:
          loan: "Mali princ" # ili bez `loan` za sve produžive
        response_variable: rezultat
      - action: notify.mobile_app_ana
        data:
          message: "Produženo: {{ rezultat.renewed }}, neuspješno: {{ rezultat.failed }}"
```

Notifikacija koja nudi taj gumb:

```yaml
      - action: notify.mobile_app_ana
        data:
          title: "📚 Rok vraćanja"
          message: "Mali princ – vraćanje 18.10.2026."
          data:
            actions:
              - action: RENEW_LIBRARY_BOOKS
                title: "Produži"
```

## Produženje

- **Gumb** `button.ana_produzi_sve` — produžuje sve što stranica nudi.
- **Servis** `knjiznica_metelgrad.renew`:

  ```yaml
  action: knjiznica_metelgrad.renew
  data:
    config_entry_id: "..."   # neobavezno; prazno = sve kartice
    loan: "Mali princ"       # neobavezno; dio naslova ili točan URL produženja
  response_variable: rezultat
  ```

  Vraća `renewed`, `failed` i `results` (po knjizi: `ok`, `due_on`, `error`).

Produženje se **nikad ne izvodi automatski**. Uspjeh se potvrđuje usporedbom
roka vraćanja prije i poslije produženja — ako se rok nije pomaknuo, prijavljuje
se kao neuspjeh (knjižnica je vjerojatno odbila produženje, npr. zbog
rezervacije).

## Privatnost i sigurnost

- Lozinka se sprema **samo u Home Assistant** (config entry u
  `config/.storage/core.config_entries`), nikad u git.
- `.gitignore` isključuje `.env`, `secrets/`, `config/`, `.storage/` i mapu
  `recon/` (snimke prijavljenih stranica sadrže osobne podatke).
- `pre-commit` s [gitleaks](https://github.com/gitleaks/gitleaks) blokira commit
  ako u promjenama prepozna tajnu. Uključi ga jednom:

  ```bash
  pre-commit install
  ```

- Snimke stvarnih stranica koristi samo lokalno (mapa `recon/`); u repozitorij
  idu isključivo sintetički testni podaci.

## Ograničenja

- Integracija **parsira HTML**; ako knjižnica promijeni izgled stranice, treba
  prilagoditi `parser.py` (jedno mjesto).
- Selektori su pisani prema očekivanom obliku Metelwinove tablice posudbi i
  pokriveni sintetičkim testom; **još nisu potvrđeni na stvarnom HTML-u**
  prijavljene sesije (vidi *Status*).
- Nema 2FA ni CAPTCHA-e u toku prijave (provjereno na stranici prijave).
- Službena mobilna aplikacija **metLib** također pristupa istim podacima — ako
  ti njeni podsjetnici budu dovoljni, ova integracija možda nije potrebna.

## Razvoj

```bash
python3 -m venv .venv
.venv/bin/pip install beautifulsoup4 ruff

.venv/bin/python -m unittest discover -s tests -t .   # testovi parsera
.venv/bin/ruff check . && .venv/bin/ruff format --check .
pre-commit run --all-files
```

Testovi ne trebaju Home Assistant: `parser.py` je čisti Python (bez HA i bez
mreže) i učitava se izravno iz putanje.

## Status

| Dio | Stanje |
| --- | --- |
| Prijava (`loaut.php`) i prepoznavanje neprijavljenog odgovora | provjereno na živoj stranici |
| Čitanje posudbi i produženje s potvrdom | implementirano, čeka prvi pravi HTML |
| Parser (`page=citam`) | implementiran prema očekivanom obliku; **nije potvrđen na stvarnom HTML-u** |
| Senzori, gumb, servis, blueprint | implementirano |
| Testovi parsera | 12 testova, prolaze |
| Provjera na stvarnom Home Assistantu | nije izvedena (nema HA u razvojnom okruženju) |
