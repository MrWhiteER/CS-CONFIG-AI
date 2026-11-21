/* The change list: one card per change, with Keep and Put back.

   Shared by Settings -> Editing (the full history) and the review window that
   comes up after a game (only the changes still waiting). Plain DOM strings,
   no framework; icons come from assets/hardware/icons.js. */
(function () {
  "use strict";

  const STATE = { waiting: "Waiting for you", kept: "Kept", back: "Put back" };
  const AREA_ICON = { keys: "keyboard", game: "apply", picture: "picture",
                      profiles: "profiles", files: "config", nvidia: "nvidia" };
  const SHOWN = 4;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g,
      c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function icon(entry) {
    const key = entry.kind === "game" ? "ingame" : (AREA_ICON[entry.area] || "history");
    return typeof hwIcon === "function" ? hwIcon(key) : "";
  }

  function when(seconds) {
    const t = new Date(seconds * 1000), now = new Date();
    const mins = Math.round((now - t) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + " min ago";
    const time = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (t.toDateString() === now.toDateString()) return "today " + time;
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (t.toDateString() === y.toDateString()) return "yesterday " + time;
    return t.toLocaleDateString([], { month: "short", day: "numeric" }) + ", " + time;
  }

  function value(v) {
    return v === null || v === undefined || v === "" ? "nothing" : v;
  }

  function pick(id, status, canBack) {
    return '<div class="chg-pick" role="group" aria-label="Keep or put back">' +
      '<button type="button" data-chist-answer="keep" data-id="' + esc(id) + '" aria-pressed="' +
        (status === "kept") + '">Keep</button>' +
      (canBack
        ? '<button type="button" data-chist-answer="back" data-id="' + esc(id) + '" aria-pressed="' +
            (status === "back") + '">Put back</button>'
        : "") +
      "</div>";
  }

  function line(item, entry) {
    const perLine = entry.kind !== "app";
    const status = item.status || entry.status;
    return '<div class="chist-line ' + esc(status) + '">' +
      '<div class="w">' + esc(item.what) +
        (item.group && entry.kind === "nvidia" ? "<small>" + esc(item.group) + "</small>" : "") +
      "</div>" +
      '<div class="mv">' +
        (item.was !== undefined && item.was !== null
          ? '<span class="was" title="' + esc(item.was) + '">' + esc(value(item.was)) + "</span>" +
            '<b class="arrow">→</b>'
          : "") +
        '<span class="now" title="' + esc(value(item.now)) + '">' + esc(value(item.now)) + "</span>" +
      "</div>" +
      (perLine ? pick(item.id, status, item.can_put_back) : "") +
      "</div>";
  }

  function card(entry, opts) {
    const open = opts.open && opts.open[entry.id];
    const items = entry.items || [];
    const visible = open ? items : items.slice(0, SHOWN);
    const conflict = opts.conflicts && opts.conflicts[entry.id];
    const nvidiaOnly = entry.kind === "nvidia" && !entry.can_put_back;
    return '<article class="chist-entry ' + esc(entry.status) + '" data-entry="' + esc(entry.id) + '">' +
      '<div class="chist-top">' +
        '<span class="chist-ic">' + icon(entry) + "</span>" +
        '<div class="chist-what"><b>' + esc(entry.title) + "</b>" +
          "<span>" + esc(entry.origin) + " · " + esc(when(entry.at)) + "</span></div>" +
        '<span class="chist-state">' + esc(STATE[entry.status] || entry.status) + "</span>" +
        pick(entry.id, entry.status === "waiting" ? "" : entry.status, entry.can_put_back) +
      "</div>" +
      '<div class="chist-items">' + visible.map(i => line(i, entry)).join("") + "</div>" +
      (items.length > SHOWN
        ? '<button type="button" class="chist-more" data-chist-more="' + esc(entry.id) + '">' +
            (open ? "Show fewer" : "Show all " + items.length) + "</button>"
        : "") +
      (conflict
        ? '<div class="chist-note">' + esc(conflict) +
            '<button type="button" class="btn" data-chist-force="' + esc(entry.id) + '">' +
            "Put back anyway</button></div>"
        : "") +
      (nvidiaOnly && entry.status === "waiting"
        ? '<div class="chist-note">To undo these, change them back in the NVIDIA app. ' +
          "Keep just tells this app you meant it.</div>"
        : "") +
      "</article>";
  }

  function render(entries, opts) {
    opts = opts || {};
    if (!entries.length) {
      return '<div class="chist-empty">' + esc(opts.empty || "No changes yet.") + "</div>";
    }
    return '<div class="chist-list">' + entries.map(e => card(e, opts)).join("") + "</div>";
  }

  window.ChangeList = { render: render, when: when };
})();
