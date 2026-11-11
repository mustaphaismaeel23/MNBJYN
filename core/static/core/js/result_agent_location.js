(function () {
  "use strict";

  var lgaSelect = document.getElementById("id_assignment_lga");
  var wardSelect = document.getElementById("id_assignment_ward");
  var pollingUnitSelect = document.getElementById("id_assignment_polling_unit");
  if (!lgaSelect || !wardSelect || !pollingUnitSelect) return;

  var roleSelect = document.getElementById("id_role");
  var status = document.createElement("p");
  status.className = "help";
  status.setAttribute("role", "status");
  pollingUnitSelect.parentNode.appendChild(status);

  function option(value, label) {
    var item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    return item;
  }

  function reset(select, label) {
    select.innerHTML = "";
    select.appendChild(option("", label));
    select.disabled = true;
  }

  function updateRequired() {
    var required = !roleSelect || roleSelect.value === "agent";
    lgaSelect.required = required;
    wardSelect.required = required;
    pollingUnitSelect.required = required;
  }

  function loadPollingUnits(lga, ward, selectedCode, sequence) {
    reset(pollingUnitSelect, "Loading polling units...");
    if (!lga || !ward) {
      reset(pollingUnitSelect, "Select a ward first");
      return Promise.resolve();
    }

    return fetch("/api/v1/public/lgas/" + encodeURIComponent(lga) +
      "/wards/" + encodeURIComponent(ward) + "/polling-units/")
      .then(function (response) {
        if (!response.ok) throw new Error("Could not load polling units.");
        return response.json();
      })
      .then(function (data) {
        if (sequence !== requests) return;
        reset(pollingUnitSelect, "Select polling unit");
        data.polling_units.forEach(function (unit) {
          var label = unit.code + " - " + unit.name;
          pollingUnitSelect.appendChild(option(unit.code, label));
        });
        pollingUnitSelect.disabled = false;
        if (selectedCode) pollingUnitSelect.value = selectedCode;
        status.textContent = data.polling_units.length
          ? ""
          : "No active polling units are listed for this ward.";
      })
      .catch(function () {
        if (sequence !== requests) return;
        reset(pollingUnitSelect, "Polling units could not be loaded");
        status.textContent = "Could not load polling units. Refresh the page and try again.";
      });
  }

  var requests = 0;
  function loadWards(lga, selectedWard, selectedCode) {
    var sequence = ++requests;
    reset(wardSelect, "Loading wards...");
    reset(pollingUnitSelect, "Select a ward first");
    status.textContent = "";
    if (!lga) {
      reset(wardSelect, "Select local government first");
      return;
    }

    fetch("/api/v1/public/lgas/" + encodeURIComponent(lga) + "/wards/")
      .then(function (response) {
        if (!response.ok) throw new Error("Could not load wards.");
        return response.json();
      })
      .then(function (data) {
        if (sequence !== requests) return;
        reset(wardSelect, "Select ward");
        data.wards.forEach(function (ward) {
          wardSelect.appendChild(option(String(ward.index), ward.name));
        });
        wardSelect.disabled = false;
        if (selectedWard) wardSelect.value = selectedWard;
        if (wardSelect.value) {
          return loadPollingUnits(lga, wardSelect.value, selectedCode, sequence);
        }
      })
      .catch(function () {
        if (sequence !== requests) return;
        reset(wardSelect, "Wards could not be loaded");
        status.textContent = "Could not load wards. Refresh the page and try again.";
      });
  }

  lgaSelect.addEventListener("change", function () {
    loadWards(lgaSelect.value, "", "");
  });
  wardSelect.addEventListener("change", function () {
    loadPollingUnits(lgaSelect.value, wardSelect.value, "", ++requests);
  });
  if (roleSelect) roleSelect.addEventListener("change", updateRequired);

  updateRequired();
  loadWards(lgaSelect.value, wardSelect.value, pollingUnitSelect.value);
})();
