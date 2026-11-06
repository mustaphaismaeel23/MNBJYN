(function () {
  "use strict";

  var root = document.documentElement;
  root.classList.add("js");

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Mobile menu ---------- */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  var desktop = window.matchMedia("(min-width: 980px)");

  function setMenu(open, returnFocus) {
    if (!toggle || !nav) return;
    nav.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (!open && returnFocus) toggle.focus();
  }

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      setMenu(toggle.getAttribute("aria-expanded") !== "true");
    });
    // Close when a link is chosen
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a")) setMenu(false);
    });
    // Esc closes and returns focus to the toggle
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") setMenu(false, true);
    });
    // Tap outside closes
    document.addEventListener("click", function (e) {
      if (toggle.getAttribute("aria-expanded") === "true" && !e.target.closest(".site-header")) setMenu(false);
    });
    // Reset when growing to the desktop layout
    var onChange = function (e) { if (e.matches) setMenu(false); };
    if (desktop.addEventListener) desktop.addEventListener("change", onChange);
    else if (desktop.addListener) desktop.addListener(onChange);
  }

  /* ---------- Animated counters (hero stats) ---------- */
  function runCounter(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    if (isNaN(target)) return;
    if (reduceMotion) { el.textContent = target; return; }
    var from = 0;
    var duration = 1400;
    var start = null;
    function step(ts) {
      if (start === null) start = ts;
      var t = Math.min((ts - start) / duration, 1);
      var eased = 1 - Math.pow(1 - t, 3); // ease-out
      el.textContent = Math.round(from + (target - from) * eased);
      if (t < 1) requestAnimationFrame(step);
      else el.textContent = target;
    }
    requestAnimationFrame(step);
  }

  /* ---------- Scroll reveal + flag wipes ---------- */
  var reveals = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  var flags = Array.prototype.slice.call(document.querySelectorAll(".flag"));
  var counters = Array.prototype.slice.call(document.querySelectorAll("[data-count]"));

  // Stagger siblings that share a parent (cards in a grid, list items)
  var seen = new Map();
  reveals.forEach(function (el) {
    var p = el.parentElement;
    var n = seen.get(p) || 0;
    seen.set(p, n + 1);
    el.style.setProperty("--d", Math.min(n, 5) * 80 + "ms");
  });

  // Once an element has finished revealing, drop the reveal state so the
  // staggered delay never affects later hover transitions.
  function settle(el) {
    var done = false;
    function finish() {
      if (done) return;
      done = true;
      el.classList.remove("reveal", "in");
      el.style.removeProperty("--d");
    }
    el.addEventListener("transitionend", function (e) {
      if (e.target === el && e.propertyName === "opacity") finish();
    });
    window.setTimeout(finish, 1500);
  }

  function show(el) {
    if (el.classList.contains("flag")) { el.classList.add("in"); return; }
    if (el.hasAttribute("data-count")) { runCounter(el); return; }
    el.classList.add("in");
    settle(el);
  }

  var targets = reveals.concat(flags, counters);

  if (reduceMotion || !("IntersectionObserver" in window)) {
    reveals.forEach(function (el) { el.classList.add("in"); });
    flags.forEach(function (el) { el.classList.add("in"); });
    counters.forEach(function (el) { runCounter(el); });
    return;
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        show(entry.target);
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });

  targets.forEach(function (el) { io.observe(el); });
})();
