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
      GET  /lib/korisnik.php?page=prod          └────────────────────────────────┘
      POST /lib/korisnik.php?page=prod  (prod[]=MK…)
```

- Prijava: `POST https://library.foi.hr/auth/loaut.php` (polja `username`,
  `password`, `B`, `bookid`, `refURL`, `navo`).
- Posudbe: `GET https://library.foi.hr/lib/korisnik.php?page=citam&B=11&H=`
  (svaka posudba je `div.col-sm-12` s elementom "Rok vraćanja").
- Produženje: `GET ...page=prod` daje obrazac (`#formo`) s jednim
  `checkbox[name="prod[]"]` po primjerku (vrijednost `MK…`) i skrivenim poljima
  `H`, `B`, `zahtjev`. Produžuje se `POST`-om na isti URL, s oznakom primjerka
  koji se produžuje. Integracija koristi točno ona polja koja nađe u obrascu.
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

Bez blueprinta može i ručno — uvjet se računa iz `due_on`, a ne iz senzora
`dana_do_roka` (taj se osvježava samo pri provjeri knjižnice):

```yaml
automation:
  - alias: "Knjižnica – podsjetnik na rok vraćanja"
    triggers:
      - trigger: time
        at: "09:00:00"
    conditions:
      - condition: template
        value_template: >-
          {% set today = now().date().isoformat() %}
          {% set limit = (now() + timedelta(days=3)).date().isoformat() %}
          {{ state_attr('sensor.ana_posudbe', 'loans')
             | selectattr('due_on', 'ge', today)
             | selectattr('due_on', 'le', limit) | list | count > 0 }}
    actions:
      - action: notify.mobile_app_ana
        data:
          title: "📚 Rok vraćanja"
          message: >-
            {{ state_attr('sensor.ana_posudbe', 'loans')
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

- **Gumb** `button.ana_produzi_sve` — produžuje sve što stranica nudi.
- **Servis** `knjiznica_metelgrad.renew`:

  ```yaml
  action: knjiznica_metelgrad.renew
  data:
    config_entry_id: "..."   # neobavezno; prazno = sve kartice
    loan: "Mali princ"       # neobavezno; dio naslova ili oznaka primjerka (MK…)
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
  prilagoditi `parser.py` (jedno mjesto). Selektori su potvrđeni na snimkama
  stvarnih stranica, a test `RealSnapshotTest` to može ponovno provjeriti na
  svježoj snimci.
- Ako knjižnica uvede dodatnu zaštitu obrasca (npr. CSRF token), treba ga
  prenijeti iz obrasca — trenutno ga nema.
- Nema 2FA ni CAPTCHA-e u toku prijave (provjereno na stranici prijave).
- Produženje je *zahtjev*: knjižnica ga može odbiti (npr. ako je knjiga
  rezervirana), pa `confirmed` zna biti `false` i kad je sve prošlo u redu.
- Službena aplikacija **metLib** pristupa istim podacima, ali **ne šalje
  podsjetnike** na rok vraćanja (provjerio korisnik) — upravo zato postoji ova
  integracija.

## Razvoj

Testovi parsera ne trebaju Home Assistant (samo `beautifulsoup4`):

```bash
python3 -m venv .venv
.venv/bin/pip install beautifulsoup4 ruff

.venv/bin/python -m unittest discover -s tests -t .   # testovi parsera
.venv/bin/ruff check . && .venv/bin/ruff format --check .
pre-commit run --all-files
```

`parser.py` je čisti Python (bez HA i bez mreže) i učitava se izravno iz putanje.
Ako u mapi `recon/` postoje snimke stvarnih stranica (`citam.html`,
`prod.html`), testovi se pokreću i na njima; inače se ti testovi preskaču. Snimke
ostaju izvan gita.

Integracijski testovi (`tests/test_integration.py`) dižu **pravi Home Assistant**
i provjeravaju config flow, entitete, više kartica, servis i gumb, a
`tests/test_blueprint.py` renderira logiku podsjetnika pravim HA template
engineom. Trebaju Python 3.13:

```bash
python3.13 -m venv .venv-ha
.venv-ha/bin/pip install -r requirements_test.txt
.venv-ha/bin/pytest tests/
```

Bez tog okruženja se ti testovi preskaču, pa `unittest` i dalje radi.

## Licencija

MIT — vidi [LICENSE](LICENSE).

## Status

| Dio | Stanje |
| --- | --- |
| Prijava (`loaut.php`) i prepoznavanje neprijavljenog odgovora | provjereno na živoj stranici |
| Parser posudbi (`page=citam`) | provjeren na stvarnoj snimci prijavljene stranice |
| Parser obrasca za produženje (`page=prod`) | provjeren na stvarnoj snimci; uparivanje posudbi s primjercima testirano |
| Slanje zahtjeva za produženje (POST) | implementirano prema stvarnom obrascu; **zahtjev još nije poslan na server** |
| Učitavanje integracije, config flow, entiteti, gumb i servis | provjereno u pravom Home Assistantu (testni harness, HA 2026.2.3) |
| Logika podsjetnika (prozor i "samo jednom") | provjereno renderiranjem blueprinta u HA template engineu |
| Sam blueprint u HA (odabir entiteta i notifikacija) | nije pokrenut u pravom HA; provjereno mu je samo YAML i logika |
| Testovi | 34 testa (21 parser + 8 HA + 5 blueprint), svi prolaze |
| Minimalna verzija 2024.12 | API-ji provjereni u izvorima te verzije; testovi se vrte na 2026.2.3 |
