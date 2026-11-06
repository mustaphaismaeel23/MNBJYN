/* LGA -> Ward pickers (home page hero + registration form).
   Data comes from the server (core/lga_data.py) via #lga-data. */
(function () {
  "use strict";
  var node = document.getElementById("lga-data");
  if (!node) return;
  var LGAS;
  try { LGAS = JSON.parse(node.textContent); } catch (e) { return; }

  function opt(value, label) {
    var o = document.createElement("option");
    o.value = value; o.textContent = label;
    return o;
  }
  function find(key) {
    for (var i = 0; i < LGAS.length; i++) if (LGAS[i].key === key) return LGAS[i];
    return null;
  }

  /* ---------- Home page: LGA dropdown, then ward dropdown ---------- */
  var lgaSel = document.getElementById("lga-select");
  var wardSel = document.getElementById("ward-select");
  var result = document.getElementById("lga-result");
  if (lgaSel && wardSel) {
    LGAS.forEach(function (l) { lgaSel.appendChild(opt(l.key, l.name)); });

    function showResult() {
      var l = find(lgaSel.value);
      if (!l || !wardSel.value) { result.hidden = true; result.textContent = ""; return; }
      result.innerHTML = "";
      var a = document.createElement("span"); a.className = "res-part";
      a.innerHTML = '<small>LGA</small>'; a.appendChild(document.createTextNode(l.name));
      var b = document.createElement("span"); b.className = "res-part";
      b.innerHTML = '<small>Ward</small>'; b.appendChild(document.createTextNode(wardSel.value));
      result.appendChild(a); result.appendChild(b);
      result.hidden = false;
    }

    lgaSel.addEventListener("change", function () {
      var l = find(lgaSel.value);
      wardSel.innerHTML = "";
      wardSel.appendChild(opt("", "Select ward (" + (l ? l.wards.length : 0) + ")"));
      if (l) {
        l.wards.forEach(function (w) { wardSel.appendChild(opt(w, w)); });
        wardSel.hidden = false;
      } else {
        wardSel.hidden = true;
      }
      showResult();
    });
    wardSel.addEventListener("change", showResult);
  }

  /* ---------- Registration form: suggest wards for the chosen LGA ---------- */
  var formLga = document.getElementById("id_lga");
  var list = document.getElementById("ward-options");
  if (formLga && list) {
    var sync = function () {
      list.innerHTML = "";
      var l = find(formLga.value);
      if (l) l.wards.forEach(function (w) { list.appendChild(opt(w, "")); });
    };
    formLga.addEventListener("change", sync);
    sync();
  }
})();
