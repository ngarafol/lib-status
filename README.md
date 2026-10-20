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
               │                                │ button.*_produzi_sve           │
      POST /auth/loaut.php  (prijava)
      GET  /lib/korisnik.php?page=citam  ──────▶│ servis knjiznica_metelgrad.renew│
      GET  /lib/korisnik.php?page=prod          └────────────────────────────────┘
      POST /lib/korisnik.php?page=prod  (prod[]=MK…)
```

- Prijava: `POST https://library.foi.hr/auth/loaut.php` (polja `username`,
  `password`, `B`, `bookid`, `refURL`, `navo`) **uz `Referer` zaglavlje**: bez
  njega knjižnica vraća `403`, što je HA prikazivao kao "ne mogu se spojiti".
  Isto zaglavlje šalje se i na ostale zahtjeve.
- Posudbe: `GET https://library.foi.hr/lib/korisnik.php?page=citam&B=11&H=`
  (svaka posudba je `div.col-sm-12` s elementom "Rok vraćanja").
- Produženje: `GET ...page=prod` daje obrazac (`#formo`) s jednim
  `checkbox[name="prod[]"]` po primjerku (vrijednost `MK…`) i skrivenim poljima
  `H`, `B`, `zahtjev`. Produžuje se `POST`-om na akciju obrasca, s oznakom
  primjerka koji se produžuje. Akcija je na živoj stranici **relativna**
  (`korisnik.php?page=prod`) i razrješava se prema URL-u stranice — u
  spremljenoj snimci izgleda apsolutno jer ju browser prepiše pri spremanju.
  Integracija koristi točno ona polja koja nađe u obrascu.
- Svaka kartica ima **vlastitu HTTP sesiju i vlastiti cookie jar**: sesijski
  kolačić se zove `korisnik11` i identičan je za sve kartice iste knjižnice, pa
  bi zajednička sesija pomiješala dvije prijavljene kartice.
- Jedna provjera = dva GET zahtjeva (posudbe + obrazac za produženje).

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

> Minimalna verzija: Home Assistant 2024.12 (provjereno da svi korišteni API-ji
> postoje u toj verziji).

## Entiteti

Za karticu `Ana` (naziv koji upišeš pri dodavanju):

| Entitet | Značenje |
| --- | --- |
| `sensor.ana_posudbe` | broj trenutno posuđenih knjiga |
| `sensor.ana_rok_vracanja` | najbliži rok vraćanja (datum) |
| `button.ana_produzi_<knjiga>` | produžuje **samo tu** knjigu (po jedan gumb za svaku produživu posudbu) |
| `button.ana_produzi_sve` | produžuje sve posudbe koje knjižnica nudi kao produžive |

Gumbi po knjizi nastaju i nestaju sami: kad knjižnica neku posudbu prestane
nuditi za produženje (vraćena knjiga), njen gumb se ukloni i iz sučelja i iz
registra entiteta. Svaki gumb nosi i `due_on`/`days_left` kao atribute, pa se
datum vidi na klik (više informacija).

Za dashboard, kartica s gumbima po knjizi:

```yaml
type: entities
title: Posudbe – Ana
entities:
  - button.ana_produzi_mali_princ
  - button.ana_produzi_dnevnik
```

Senzor `sensor.ana_posudbe` nosi i atribute:

```yaml
loans:
  - title: "Mali princ"
    author: "Saint-Exupéry, Antoine de"
    due_on: "2026-10-18"
    days_left: 5
    renewable: true
```

Za automatizacije koristi `due_on` (apsolutni datum, ne zastarijeva između
provjera). `days_left` se osvježava samo pri provjeri.

## Notifikacije

Gotov blueprint: `blueprints/automation/knjiznica_metelgrad/podsjetnik_rok_vracanja.yaml`.

1. Kopiraj datoteku u `config/blueprints/automation/knjiznica_metelgrad/`.
2. **Postavke → Automatizacije → Novi → Blueprint** → odaberi
   *Knjižnica Metelgrad: podsjetnik na rok vraćanja*.
3. Odaberi senzor posudbi, broj dana prije roka (npr. 3), vrijeme provjere i
   notifikacijsku uslugu (npr. `notify.mobile_app_ana`).

Blueprint svaki dan u zadano vrijeme pogleda rokove i, ako neka knjiga ulazi u
zadani broj dana do roka, pošalje notifikaciju. Dani se računaju iz apsolutnog
datuma roka, pa podsjetnik ostaje točan i kad se posudbe provjeravaju jednom
tjedno.

**Što znači "prozor"?** Prozor je broj dana prije roka koji te zanima. Ako je rok
1.11. i postaviš 3 dana, prozor se otvara 29.10. Na izbor je što se dogodi dok je
knjiga u tom prozoru:

| Način | Kada stiže notifikacija | Primjer za rok 1.11. |
| --- | --- | --- |
| Ponavljaj svaki dan (zadano) | svaki dan dok je rok unutar prozora | 29.10., 30.10., 31.10., 1.11. |
| Samo jednom | samo točno zadani broj dana prije roka | 29.10. |

Ponavljanje je korisnije ako ti treba svakodnevni podsjetnik (i preživi dan kad
HA nije radio); "samo jednom" je mirnije, ali ako HA tog dana ne radi, podsjetnik
se preskoči.

Ako ti blueprint ne odgovara, uvjet računaj iz `due_on` (apsolutni datum), a ne
iz atributa `days_left` — taj se osvježava samo pri provjeri knjižnice, pa uz
rjeđi interval propusti trenutak prelaska praga.

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
          message: >-
            Poslano: {{ rezultat.submitted }}, potvrđeno: {{ rezultat.confirmed }},
            neuspješno: {{ rezultat.failed }}
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

Tri načina, svi šalju isti zahtjev knjižnici (koji knjižničar odobrava ručno):

- **Gumb po knjizi** `button.ana_produzi_<knjiga>` — produžuje samo tu posudbu.
  To je najbliže onome što radiš na stranici knjižnice: knjigu po knjigu.
- **Gumb** `button.ana_produzi_sve` — jedan zahtjev sa **svim** primjercima koje
  knjižnica nudi za produženje (sve knjige odjednom).
- **Servis** `knjiznica_metelgrad.renew`:

  ```yaml
  action: knjiznica_metelgrad.renew
  data:
    config_entry_id: "..."   # neobavezno; prazno = sve kartice
    loan: "Mali princ"       # neobavezno; dio naslova knjige
  response_variable: rezultat
  ```

  Vraća `submitted`, `confirmed`, `failed` i `results` (po knjizi: `submitted`,
  `confirmed`, `due_on`, `error`).

Produženje se **nikad ne izvodi automatski**. Gumb na stranici knjižnice zove se
"Pošalji zahtjev za produljenje", i to je doslovno to: integracija pošalje
**zahtjev**, a knjižničar ga mora vidjeti i ručno odobriti. Zato razlikujem dva
ishoda:

- `submitted` — zahtjev je poslan knjižnici.
- `confirmed` — rok vraćanja se pri nekoj od sljedećih provjera stvarno pomaknuo.

Uobičajen slijed: klikneš "Produži sve", dobiješ `submitted: 1`, a `confirmed`
postane `true` tek nakon što knjižničar odobri zahtjev (dakle pri sljedećoj
provjeri, ovisno o intervalu). Ako zahtjev ostane nepotvrđen, to se **ne**
prijavljuje kao greška — knjižnica ga može obraditi kasnije ili odbiti (npr. ako
je knjiga rezervirana). Greška je samo ako zahtjev nije ni poslan.

## Privatnost i sigurnost

- Lozinka se sprema **samo u Home Assistant** (config entry u
  `config/.storage/core.config_entries`), nikad u git.
- `.gitignore` isključuje `.env`, `secrets/` i mapu `recon/` (snimke
  prijavljenih stranica sadrže osobne podatke).
- `pre-commit` s [gitleaks](https://github.com/gitleaks/gitleaks) blokira commit
  ako u promjenama prepozna tajnu. Uključi ga jednom:

  ```bash
  pre-commit install
  ```

- Snimke stvarnih stranica koristi samo lokalno (mapa `recon/`); u repozitorij
  idu isključivo sintetički testni podaci.

## Ograničenja

- Integracija **parsira HTML**; ako knjižnica promijeni izgled stranice, treba
  prilagoditi `parser.py` (jedno mjesto). Selektori su potvrđeni na snimkama
  stvarnih stranica, a test `RealSnapshotTest` to može ponovno provjeriti na
  svježoj snimci.
- Ako knjižnica uvede dodatnu zaštitu obrasca (npr. CSRF token), treba ga
  prenijeti iz obrasca — trenutno ga nema.
- Nema 2FA ni CAPTCHA-e u toku prijave (provjereno na stranici prijave).
- Službena aplikacija **metLib** pristupa istim podacima, ali **ne šalje
  podsjetnike** na rok vraćanja (provjerio korisnik) — upravo zato postoji ova
  integracija.

## Razvoj

Sve se vrti u jednom okruženju (Python 3.13), jer testovi dižu **pravi Home
Assistant**:

```bash
python3.13 -m venv .venv-ha
.venv-ha/bin/pip install -r requirements_test.txt

.venv-ha/bin/pytest tests/                        # svi testovi
.venv-ha/bin/ruff check . && .venv-ha/bin/ruff format --check .
pre-commit run --all-files
```

- `tests/test_parser.py` — parsiranje stranica (sintetički HTML + snimke iz `recon/`)
- `tests/test_integration.py` — config flow, entiteti, više kartica, servis, gumb
- `tests/test_blueprint.py` — logika podsjetnika kroz HA template engine
- `tests/test_api.py` — HTTP klijent bez mreže (Referer, polja obrasca)

Ako u mapi `recon/` postoje snimke stvarnih stranica (`citam.html`, `prod.html`),
parser testovi se vrte i na njima; inače se preskaču. Snimke ostaju izvan gita.

## Licencija

MIT — vidi [LICENSE](LICENSE).

## Status

| Dio | Stanje |
| --- | --- |
| Prijava (`loaut.php`) i prepoznavanje neprijavljenog odgovora | provjereno na živoj stranici, uključujući obavezni `Referer` |
| Parser posudbi (`page=citam`) | provjeren na stvarnoj snimci prijavljene stranice |
| Parser obrasca za produženje (`page=prod`) | provjeren na stvarnoj snimci; uparivanje posudbi s primjercima testirano |
| Slanje zahtjeva za produženje (POST) | prvi pravi zahtjev pokušan iz HA: pao je zbog relativne akcije obrasca, ispravljeno i pokriveno testom; **uspješan zahtjev još nije potvrđen** |
| Učitavanje integracije, config flow, entiteti, gumb i servis | provjereno u pravom Home Assistantu (testni harness, HA 2026.2.3) |
| Logika podsjetnika (prozor i "samo jednom") | provjereno renderiranjem blueprinta u HA template engineu |
| Sam blueprint u HA (odabir entiteta i notifikacija) | nije pokrenut u pravom HA; provjereno mu je samo YAML i logika |
| Testovi | 38 testova (19 parser + 11 HA + 5 blueprint + 3 klijent), svi prolaze |
| Minimalna verzija 2024.12 | API-ji provjereni u izvorima te verzije; testovi se vrte na 2026.2.3 |
