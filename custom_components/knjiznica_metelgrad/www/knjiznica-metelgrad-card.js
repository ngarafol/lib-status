/**
 * Knjižnica Metelgrad — Lovelace kartica.
 *
 * Prikazuje sve podatke o svakoj posudbi (naslovnica, naslov, autor, šifra
 * zapisa, datum posudbe, rok) i gumb za produženje. Integracija ju poslužuje i
 * učitava sama, pa nema ručnog instaliranja resursa.
 *
 * Konfiguracija:
 *   type: custom:knjiznica-metelgrad-card
 *   entity: sensor.nika_posudbe
 */

const DOMAIN = "knjiznica_metelgrad";
const SERVICE = "renew";

const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]
  );

const formatDate = (iso) => {
  if (!iso) return "";
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  return `${Number(day)}. ${Number(month)}. ${year}.`;
};

const dueState = (days) => (days <= 0 ? "late" : days <= 7 ? "warn" : "ok");

const CSS = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .inner { padding: 16px; display: grid; gap: 16px; }

  .hero {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 18px 20px; border-radius: 18px; color: #fff;
    background:
      radial-gradient(120% 140% at 0% 0%, rgb(255 255 255 / .22), transparent 55%),
      linear-gradient(135deg, rgb(var(--rgb-primary-color)) 0%, rgb(var(--rgb-primary-color) / .72) 100%);
    box-shadow: 0 10px 30px rgb(var(--rgb-primary-color) / .28);
  }
  .hero .eyebrow { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; opacity: .85; }
  .hero .count { font-size: 2rem; font-weight: 700; line-height: 1.05; margin-top: 4px; }
  .hero .count small { font-size: .95rem; font-weight: 500; opacity: .9; margin-left: 4px; }
  .hero .right { text-align: right; display: grid; gap: 8px; justify-items: end; }
  .hero .next { font-size: .78rem; opacity: .9; }
  .hero .next b { display: block; font-size: 1rem; margin-top: 2px; opacity: 1; }

  .pill {
    border: 1px solid rgb(255 255 255 / .55); background: rgb(255 255 255 / .16);
    color: #fff; font: inherit; font-size: .82rem; font-weight: 600;
    padding: 7px 14px; border-radius: 999px; cursor: pointer;
    transition: background .18s ease, transform .18s ease;
  }
  .pill:hover:not(:disabled) { background: rgb(255 255 255 / .28); transform: translateY(-1px); }
  .pill:disabled { opacity: .55; cursor: default; }

  .grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }

  .book {
    display: flex; gap: 14px; padding: 12px; border-radius: 18px;
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--divider-color);
    transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
  }
  .book:hover { transform: translateY(-2px); box-shadow: 0 10px 26px rgb(0 0 0 / .14); border-color: rgb(var(--rgb-primary-color) / .45); }

  .cover {
    flex: 0 0 86px; width: 86px; aspect-ratio: 2 / 3; border-radius: 12px; overflow: hidden;
    background: linear-gradient(160deg, rgb(var(--rgb-primary-color) / .22), rgb(var(--rgb-primary-color) / .06));
    display: grid; place-items: center; box-shadow: 0 4px 12px rgb(0 0 0 / .16);
  }
  .cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .cover svg { width: 54%; height: auto; opacity: .55; }

  .body { min-width: 0; display: grid; gap: 6px; align-content: start; }
  .title { font-size: .95rem; font-weight: 650; line-height: 1.25; color: var(--primary-text-color); }
  .author { font-size: .8rem; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    font-size: .68rem; padding: 2px 8px; border-radius: 999px; color: var(--secondary-text-color);
    background: rgb(var(--rgb-primary-color) / .1); border: 1px solid rgb(var(--rgb-primary-color) / .16);
    font-variant-numeric: tabular-nums;
  }

  .due { display: flex; align-items: center; gap: 7px; font-size: .82rem; color: var(--primary-text-color); }
  .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
  .dot.ok { background: #2e9e5b; box-shadow: 0 0 0 3px rgb(46 158 91 / .18); }
  .dot.warn { background: #d9930a; box-shadow: 0 0 0 3px rgb(217 147 10 / .18); }
  .dot.late { background: #d33b3b; box-shadow: 0 0 0 3px rgb(211 59 59 / .18); animation: pulse 1.8s ease-in-out infinite; }
  .due em { font-style: normal; color: var(--secondary-text-color); }
  .due .dleft { margin-left: auto; font-weight: 600; font-variant-numeric: tabular-nums; }
  .dleft.late { color: #d33b3b; }
  .dleft.warn { color: #b87c05; }

  .renew {
    border: 0; border-radius: 10px; padding: 7px 12px; font: inherit; font-size: .78rem; font-weight: 650;
    color: var(--text-primary-color, #fff); background: rgb(var(--rgb-primary-color)); cursor: pointer;
    transition: filter .18s ease, transform .18s ease;
  }
  .renew:hover:not(:disabled) { filter: brightness(1.08); transform: translateY(-1px); }
  .renew:disabled { background: var(--divider-color); color: var(--secondary-text-color); cursor: default; }
  .renew.busy { color: transparent; position: relative; }
  .renew.busy::after {
    content: ""; position: absolute; inset: 0; margin: auto; width: 14px; height: 14px;
    border: 2px solid rgb(255 255 255 / .45); border-top-color: #fff; border-radius: 50%;
    animation: spin .7s linear infinite;
  }

  .status { font-size: .74rem; min-height: 1em; }
  .status.ok { color: #2e9e5b; }
  .status.warn { color: #b87c05; }
  .status.err { color: #d33b3b; }

  .empty { text-align: center; padding: 26px 12px; color: var(--secondary-text-color); }
  .empty .big { font-size: 2rem; margin-bottom: 6px; }
  .footer { display: flex; justify-content: space-between; gap: 10px; font-size: .7rem; color: var(--secondary-text-color); }
  .footer a { color: inherit; }

  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes pulse { 50% { opacity: .45; } }
  @media (prefers-reduced-motion: reduce) {
    .book, .pill, .renew { transition: none; }
    .dot.late, .renew.busy::after { animation: none; }
  }
`;

const COVER_FALLBACK = `
  <svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
    <path d="M4 3.5A1.5 1.5 0 0 1 5.5 2H18a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H5.5A1.5 1.5 0 0 1 4 20.5Zm2 .5v16h12V4Zm2.5 3h7v1.6h-7Zm0 3.4h7v1.6h-7Z"/>
  </svg>`;

class KnjiznicaMetelgradCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._loans = [];
    this._pending = null;
    this._status = null;
    this._signature = "";
  }

  static async getConfigElement() {
    return document.createElement("knjiznica-metelgrad-card-editor");
  }

  static getStubConfig(hass) {
    const sensor = Object.keys(hass?.states ?? {}).find(
      (id) => id.endsWith("_posudbe") && Array.isArray(hass.states[id].attributes?.loans)
    );
    return { entity: sensor ?? "sensor.knjiznica_metelgrad_posudbe" };
  }

  setConfig(config) {
    if (!config?.entity) throw new Error("Postavi 'entity' na senzor 'Posudbe'.");
    this._config = { title: "Knjižnica", ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass?.states?.[this._config.entity];
    const loans = state?.attributes?.loans ?? [];
    const signature = JSON.stringify([loans, state?.last_updated]);
    if (signature !== this._signature) {
      this._signature = signature;
      this._loans = loans;
      this._render();
    }
  }

  getCardSize() {
    return 2 + Math.ceil(this._loans.length / 2) * 2;
  }

  _render() {
    if (!this.shadowRoot) return;
    const mounted = this.shadowRoot.querySelector(".inner");
    const scrollY = mounted ? this.shadowRoot.querySelector(".grid")?.scrollTop ?? 0 : 0;

    this.shadowRoot.innerHTML = `<style>${CSS}</style>${this._template()}`;

    const grid = this.shadowRoot.querySelector(".grid");
    if (grid) grid.scrollTop = scrollY;
    this._bind();
  }

  _template() {
    const state = this._hass?.states?.[this._config.entity];
    const title = this._config.title ?? "Knjižnica";
    if (!state) {
      return `<ha-card><div class="inner"><div class="empty"><div class="big">🔌</div>
        Entitet <b>${escape(this._config.entity)}</b> ne postoji.</div></div></ha-card>`;
    }

    const loans = this._loans;
    const nearest = loans.reduce((acc, loan) => (!acc || loan.due_on < acc ? loan.due_on : acc), null);
    const canRenewAll = loans.some((loan) => loan.renewable);
    const fetched = state.last_updated
      ? new Date(state.last_updated).toLocaleString("hr-HR", {
          day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
        })
      : "";

    return `
      <ha-card>
        <div class="inner">
          <div class="hero">
            <div>
              <div class="eyebrow">${escape(title)}</div>
              <div class="count">${loans.length}<small>${loans.length === 1 ? "knjiga" : "knjige"}</small></div>
            </div>
            <div class="right">
              ${
                nearest
                  ? `<div class="next">najbliži rok<b>${formatDate(nearest)}</b></div>`
                  : `<div class="next">nema rokova</div>`
              }
              <button class="pill" data-action="all" ${canRenewAll ? "" : "disabled"}>
                ${this._pending === "*" ? "Šaljem…" : "Produži sve"}
              </button>
            </div>
          </div>
          ${
            loans.length
              ? `<div class="grid">${loans.map((loan) => this._book(loan)).join("")}</div>`
              : `<div class="empty"><div class="big">🎉</div>Nema posuđenih knjiga.</div>`
          }
          <div class="footer">
            <span>${fetched ? `podaci od ${escape(fetched)}` : ""}</span>
            <a href="https://library.foi.hr/lib/korisnik.php?page=citam&amp;B=11" target="_blank" rel="noreferrer">otvori knjižnicu ↗</a>
          </div>
        </div>
      </ha-card>`;
  }

  _book(loan) {
    const status = dueState(loan.days_left);
    const busy = this._pending === loan.title;
    const statusText = this._status?.title === loan.title ? this._status : null;
    const days =
      loan.days_left === 0 ? "danas" : loan.days_left < 0 ? `${-loan.days_left} d kasni` : `${loan.days_left} d`;

    return `
      <article class="book">
        <div class="cover">
          ${
            loan.cover
              ? `<img src="${escape(loan.cover)}" alt="Naslovnica: ${escape(loan.title)}" loading="lazy">`
              : COVER_FALLBACK
          }
        </div>
        <div class="body">
          <div class="title">${escape(loan.title)}</div>
          ${loan.author ? `<div class="author">${escape(loan.author)}</div>` : ""}
          <div class="chips">
            ${loan.code ? `<span class="chip">${escape(loan.code)}</span>` : ""}
            ${loan.borrowed_on ? `<span class="chip">posuđeno ${formatDate(loan.borrowed_on)}</span>` : ""}
          </div>
          <div class="due">
            <span class="dot ${status}"></span>
            <span>rok ${formatDate(loan.due_on)}</span>
            <span class="dleft ${status}">${days}</span>
          </div>
          <button class="renew ${busy ? "busy" : ""}" data-action="one" data-title="${escape(loan.title)}"
            ${loan.renewable && !this._pending ? "" : "disabled"}>
            ${busy ? "Šaljem…" : loan.renewable ? "Produži" : "produženo"}
          </button>
          <div class="status ${statusText?.kind ?? ""}">${escape(statusText?.text ?? "")}</div>
        </div>
      </article>`;
  }

  _bind() {
    // Ako naslovnica ne učita (npr. traži prijavu), zamijeni ju rezervnom slikom.
    this.shadowRoot.querySelectorAll(".cover img").forEach((image) => {
      image.addEventListener("error", () => {
        image.parentNode.innerHTML = COVER_FALLBACK;
      });
    });
    this.shadowRoot.querySelector('[data-action="all"]')?.addEventListener("click", () => this._renew());
    this.shadowRoot.querySelectorAll('[data-action="one"]').forEach((button) => {
      button.addEventListener("click", () => this._renew(button.dataset.title));
    });
  }

  async _renew(loanTitle) {
    if (!this._hass || this._pending) return;
    this._pending = loanTitle ?? "*";
    this._status = null;
    this._render();
    try {
      const call = await this._hass.callService(
        DOMAIN,
        SERVICE,
        loanTitle ? { loan: loanTitle } : {},
        undefined,
        false,
        true
      );
      const result = call?.response ?? {};
      const failed = result.failed ?? 0;
      this._status = loanTitle
        ? failed
          ? { title: loanTitle, kind: "err", text: "Knjižnica nije prihvatila zahtjev." }
          : { title: loanTitle, kind: "ok", text: "Zahtjev poslan ✓" }
        : {
            kind: failed ? "err" : "ok",
            text: failed ? `Nije poslano za ${failed} knjiga.` : `Zahtjev poslan za ${result.submitted ?? 0} knjiga ✓`,
          };
    } catch (error) {
      this._status = { title: loanTitle, kind: "err", text: error?.message ?? "Greška pri slanju." };
    } finally {
      this._pending = null;
      this._render();
    }
  }
}

class KnjiznicaMetelgradCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const sensors = Object.keys(this._hass?.states ?? {})
      .filter((id) => Array.isArray(this._hass.states[id].attributes?.loans))
      .sort();
    this.shadowRoot.innerHTML = `
      <div style="display:grid;gap:12px;padding:8px 0">
        <label style="display:grid;gap:4px;font-size:.9rem">
          Senzor posudbi
          <select id="entity" style="padding:8px">
            ${sensors
              .map(
                (id) =>
                  `<option value="${escape(id)}" ${id === this._config?.entity ? "selected" : ""}>${escape(id)}</option>`
              )
              .join("")}
          </select>
        </label>
        <label style="display:grid;gap:4px;font-size:.9rem">
          Naslov kartice
          <input id="title" style="padding:8px" value="${escape(this._config?.title ?? "Knjižnica")}">
        </label>
      </div>`;
    const update = () => {
      const entity = this.shadowRoot.querySelector("#entity").value;
      const title = this.shadowRoot.querySelector("#title").value;
      this.dispatchEvent(
        new CustomEvent("config-changed", { detail: { config: { ...this._config, entity, title } } })
      );
    };
    this.shadowRoot.querySelectorAll("select,input").forEach((el) => el.addEventListener("change", update));
  }
}

if (!customElements.get("knjiznica-metelgrad-card")) {
  customElements.define("knjiznica-metelgrad-card", KnjiznicaMetelgradCard);
}
if (!customElements.get("knjiznica-metelgrad-card-editor")) {
  customElements.define("knjiznica-metelgrad-card-editor", KnjiznicaMetelgradCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "knjiznica-metelgrad-card")) {
  window.customCards.push({
    type: "knjiznica-metelgrad-card",
    name: "Knjižnica Metelgrad",
    description: "Posudbe s naslovnicama, rokovima i produženjem.",
    preview: true,
    documentationURL: "https://github.com/ngarafol/lib-status#dashboard",
  });
}
