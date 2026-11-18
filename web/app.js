import { toBibtex } from "./bibtex.js";
import { load, save } from "./store.js";

const FEED_URL = "https://raw.githubusercontent.com/RazvanZapodeanu/paperfeed/data/feed.json";
const REFRESH_AFTER = 60 * 60 * 1000;

const TIER = { thesis: "Pentru licență", field: "Din domeniu" };
const ACTION = { read: "de citit integral", skim: "merită răsfoit", note: "ajunge cardul" };

const main = document.querySelector("main");
const actions = document.querySelector(".actions");
const notice = document.querySelector(".notice");
const toastBox = document.querySelector(".toast");
const touch = matchMedia("(pointer: coarse)");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

const state = load();
let status = state.feed ? "ok" : "loading";
let lastAction = null;
let toastTimer;

// Builds DOM nodes. Strings become text nodes, so card text is never parsed as HTML.
function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (name.startsWith("on")) el.addEventListener(name.slice(2), value);
    else if (value != null && value !== false) el.setAttribute(name, value);
  }
  el.append(...children.flat().filter((child) => child != null && child !== false));
  return el;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#icon-${name}`);
  svg.setAttribute("aria-hidden", "true");
  svg.append(use);
  return svg;
}

function button(label, iconName, onclick, extra = {}) {
  return h("button", { type: "button", class: "act", onclick, ...extra }, icon(iconName), label);
}

function arxivLink(paper) {
  return h(
    "a",
    { class: "act quiet", href: arxivUrl(paper), target: "_blank", rel: "noopener" },
    icon("open"),
    "arXiv",
  );
}

// The feed is generated from untrusted abstracts, so only ever link to arXiv.
function arxivUrl(paper) {
  return `https://arxiv.org/abs/${paper.id.replace(/[^\w./-]/g, "")}`;
}

function authors(names) {
  if (names.length <= 2) return names.join(" și ");
  if (names.length === 3) return `${names[0]}, ${names[1]} și ${names[2]}`;
  return `${names.slice(0, 3).join(", ")} și alții`;
}

// Same line arXiv prints down the margin of every PDF.
function stamp(paper) {
  const date = new Date(`${paper.published}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  return `arXiv:${paper.id} [${paper.categories[0]}] ${date}`;
}

function paragraph(head, text) {
  return text && h("p", {}, h("b", {}, `${head}.`), " ", text);
}

function page(paper) {
  const { card } = paper;
  const source = paper.seed ? "Din lista ta de lectură" : TIER[paper.tier];
  return h(
    "article",
    { class: "page" },
    h(
      "a",
      { class: "stamp", href: arxivUrl(paper), target: "_blank", rel: "noopener" },
      stamp(paper),
    ),
    h("h1", { class: "title" }, paper.title),
    h("p", { class: "authors" }, authors(paper.authors)),
    h("p", { class: "verdict" }, `${source}, ${ACTION[card.action]}.`),
    paragraph("Pe scurt", card.summary),
    paragraph("Evaluare", card.evaluation),
    paragraph("Ce faci cu el", card.use),
    h(
      "div",
      { class: "concept" },
      h("p", {}, h("b", {}, "Concept"), ` (${card.concept.name}). `, card.concept.explanation),
    ),
    card.terms.length > 0 &&
      h(
        "ul",
        { class: "terms" },
        card.terms.map((t) => h("li", {}, h("i", {}, t.term), `: ${t.meaning}`)),
      ),
  );
}

function endPage(title, text, ...extra) {
  return h(
    "div",
    { class: "deck" },
    h("section", { class: "page end" }, h("h1", {}, title), h("p", {}, text), ...extra),
  );
}

function unread() {
  const done = new Set(state.done);
  const saved = new Set(state.saved.map((p) => p.id));
  const rank = (paper) => (paper.tier === "thesis" ? 0 : 1);
  return (state.feed?.cards ?? [])
    .filter((paper) => !done.has(paper.id) && !saved.has(paper.id))
    .sort((a, b) => rank(a) - rank(b) || a.added.localeCompare(b.added));
}

function route() {
  const [tab, id] = location.hash.slice(1).split("/");
  return tab === "salvate" ? { tab: "saved", id: id && decodeURIComponent(id) } : { tab: "deck" };
}

function render() {
  const { tab, id } = route();
  const cards = unread();

  for (const link of document.querySelectorAll(".tabs a")) {
    if (link.dataset.tab === tab) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.querySelector('[data-count="deck"]').textContent = cards.length || "";
  document.querySelector('[data-count="saved"]').textContent = state.saved.length || "";

  let text = "";
  if (status === "offline" && state.feed) {
    const when = new Date(state.feed.updated).toLocaleString("ro-RO", {
      day: "numeric",
      month: "long",
      hour: "2-digit",
      minute: "2-digit",
    });
    text = `Ești offline. Cardurile sunt de la ultima actualizare, ${when}.`;
  } else if (tab === "deck" && cards.length > 0 && !state.hinted && touch.matches) {
    text = "Glisează spre dreapta ca să salvezi și spre stânga după ce ai citit.";
  }
  notice.textContent = text;
  notice.hidden = !text;

  if (tab === "deck") renderDeck(cards);
  else if (id) renderSavedPaper(id);
  else renderSaved();
}

function renderDeck(cards) {
  if (!state.feed) {
    main.replaceChildren(
      status === "loading"
        ? endPage("Se încarcă feed-ul.", "Durează doar prima dată.")
        : endPage("Feed-ul nu s-a încărcat.", "Verifică conexiunea și deschide din nou aplicația."),
    );
    actions.replaceChildren();
    return;
  }

  const [paper] = cards;
  if (!paper) {
    const saved = state.saved.length;
    main.replaceChildren(
      endPage(
        "Ai terminat pentru azi.",
        "Cardurile noi apar în fiecare dimineață.",
        saved > 0 && h("a", { class: "act", href: "#salvate" }, `Vezi salvatele (${saved})`),
      ),
    );
    actions.replaceChildren();
    return;
  }

  const card = h(
    "div",
    { class: "card" },
    h("span", { class: "swipe save", "aria-hidden": "true" }, "Salvează"),
    h("span", { class: "swipe read", "aria-hidden": "true" }, "Citit"),
    page(paper),
  );
  main.replaceChildren(
    h("div", { class: "deck", "data-left": Math.min(cards.length - 1, 2) }, card),
  );
  swipeable(card, paper);

  actions.replaceChildren(
    h(
      "div",
      { class: "row" },
      button("Citit", "check", () => fling(card, "read", paper), { title: "Citit (C)" }),
      arxivLink(paper),
      button("Salvează", "save", () => fling(card, "save", paper), {
        title: "Salvează (S)",
        class: "act primary",
      }),
    ),
  );
}

function renderSaved() {
  const papers = [...state.saved].sort((a, b) => b.savedAt.localeCompare(a.savedAt));
  const day = (iso) => new Date(iso).toLocaleDateString("ro-RO", { day: "numeric", month: "long" });

  const content = papers.length
    ? h(
        "ol",
        {},
        papers.map((paper) =>
          h(
            "li",
            {},
            h(
              "a",
              { href: `#salvate/${encodeURIComponent(paper.id)}` },
              h("span", { class: "title" }, paper.title),
              h("span", { class: "authors" }, authors(paper.authors)),
              h("span", { class: "meta" }, `arXiv:${paper.id}, salvat pe ${day(paper.savedAt)}`),
            ),
          ),
        ),
      )
    : h("p", { class: "meta" }, "Lucrările pe care le salvezi apar aici.");

  main.replaceChildren(h("div", { class: "deck" }, h("section", { class: "page list" }, content)));
  actions.replaceChildren(
    ...(papers.length
      ? [h("div", { class: "row single" }, button("Descarcă BibTeX", "download", download))]
      : []),
  );
}

function renderSavedPaper(id) {
  const paper = state.saved.find((p) => p.id === id);
  if (!paper) {
    history.replaceState(null, "", "#salvate");
    renderSaved();
    return;
  }
  main.replaceChildren(h("div", { class: "deck" }, h("div", { class: "card" }, page(paper))));
  actions.replaceChildren(
    h(
      "div",
      { class: "row" },
      button("Scoate", "remove", () => remove(paper), { title: "Scoate din salvate" }),
      arxivLink(paper),
      button("BibTeX", "copy", () => copy(paper), {
        title: "Copiază BibTeX",
        "aria-label": "Copiază BibTeX",
      }),
    ),
  );
}

function act(kind, paper) {
  if (kind === "save") {
    state.saved = [{ ...paper, savedAt: new Date().toISOString() }, ...state.saved];
    navigator.storage?.persist?.();
  } else {
    state.done = [...state.done, paper.id];
  }
  state.hinted = true;
  lastAction = { kind, paper };
  save(state);
  render();
  toast(kind === "save" ? "Salvat." : "Marcat ca citit.", undo);
}

function remove(paper) {
  state.saved = state.saved.filter((p) => p.id !== paper.id);
  lastAction = { kind: "remove", paper };
  save(state);
  history.replaceState(null, "", "#salvate");
  render();
  toast("Scos din salvate.", undo);
}

function undo() {
  if (!lastAction) return;
  const { kind, paper } = lastAction;
  if (kind === "save") state.saved = state.saved.filter((p) => p.id !== paper.id);
  if (kind === "read") state.done = state.done.filter((id) => id !== paper.id);
  if (kind === "remove") state.saved = [paper, ...state.saved];
  lastAction = null;
  save(state);
  toastBox.hidden = true;
  render();
}

async function copy(paper) {
  try {
    await navigator.clipboard.writeText(toBibtex([paper]));
    toast("BibTeX copiat.");
  } catch {
    toast("Nu am putut copia. Descarcă BibTeX din lista de salvate.");
  }
}

function download() {
  const blob = new Blob([toBibtex(state.saved)], { type: "text/plain;charset=utf-8" });
  const link = h("a", { href: URL.createObjectURL(blob), download: "paperfeed.bib" });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function toast(message, onUndo) {
  clearTimeout(toastTimer);
  toastBox.replaceChildren(
    h("span", {}, message),
    onUndo && h("button", { type: "button", onclick: onUndo }, "Anulează"),
  );
  toastBox.hidden = false;
  toastTimer = setTimeout(() => (toastBox.hidden = true), 5000);
}

function drag(card, dx) {
  const strength = Math.min(Math.abs(dx) / (card.offsetWidth * 0.3), 1);
  card.style.transform = dx ? `translateX(${dx}px) rotate(${dx / 30}deg)` : "";
  card.querySelector(".swipe.save").style.opacity = dx > 0 ? strength : 0;
  card.querySelector(".swipe.read").style.opacity = dx < 0 ? strength : 0;
}

// Sends the card off screen in the direction of the action, then records it.
function fling(card, kind, paper) {
  if (card.dataset.gone) return;
  card.dataset.gone = "true";
  if (reducedMotion.matches) {
    act(kind, paper);
    return;
  }
  let finished = false;
  const finish = () => {
    if (!finished) {
      finished = true;
      act(kind, paper);
    }
  };
  const direction = kind === "save" ? 1 : -1;
  drag(card, direction * card.offsetWidth * 0.3);
  card.style.transition = "transform 0.18s ease-in";
  card.style.transform = `translateX(${direction * innerWidth}px) rotate(${direction * 12}deg)`;
  card.addEventListener("transitionend", finish, { once: true });
  setTimeout(finish, 300);
}

function swipeable(card, paper) {
  let start = null;
  let dx = 0;

  card.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" || event.target.closest("a, button")) return;
    start = { x: event.clientX, y: event.clientY, pointer: event.pointerId, dragging: false };
  });

  card.addEventListener("pointermove", (event) => {
    if (!start || event.pointerId !== start.pointer) return;
    dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!start.dragging) {
      // Mostly vertical movement is scrolling, not a swipe.
      if (Math.abs(dx) < 12 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
      start.dragging = true;
      card.setPointerCapture(event.pointerId);
      card.style.transition = "none";
    }
    drag(card, dx);
  });

  const release = (event) => {
    if (!start || event.pointerId !== start.pointer) return;
    const swiped = start.dragging && Math.abs(dx) > card.offsetWidth * 0.3;
    start = null;
    if (swiped) {
      fling(card, dx > 0 ? "save" : "read", paper);
    } else {
      card.style.transition = "transform 0.2s ease";
      drag(card, 0);
    }
    dx = 0;
  };
  card.addEventListener("pointerup", release);
  card.addEventListener("pointercancel", release);
}

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === "z") {
    undo();
    return;
  }
  const card = main.querySelector(".card");
  const [paper] = unread();
  if (route().tab !== "deck" || !card || !paper) return;
  if (key === "s" || key === "arrowright") fling(card, "save", paper);
  else if (key === "c" || key === "arrowleft") fling(card, "read", paper);
  else if (key === "o") window.open(arxivUrl(paper), "_blank", "noopener");
});

async function refresh() {
  try {
    const response = await fetch(FEED_URL, { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const feed = await response.json();
    if (!Array.isArray(feed.cards)) throw new Error("unexpected feed format");

    const changed = feed.updated !== state.feed?.updated;
    const ids = new Set(feed.cards.map((paper) => paper.id));
    state.feed = feed;
    state.done = state.done.filter((id) => ids.has(id));
    state.fetchedAt = Date.now();
    save(state);
    if (changed || status !== "ok") {
      status = "ok";
      render();
    }
  } catch {
    if (status !== "offline") {
      status = "offline";
      render();
    }
  }
}

addEventListener("hashchange", render);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - state.fetchedAt > REFRESH_AFTER)
    refresh();
});

render();
refresh();
navigator.serviceWorker?.register("sw.js").catch(() => {});
