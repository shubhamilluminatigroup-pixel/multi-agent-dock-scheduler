let latestTransportState = null;
let selectedTransportTruckId = "TRK-101";

function showToast(msg) {
  const banner = document.getElementById("toastBanner");
  if (!banner) return;
  banner.textContent = msg;
  banner.hidden = false;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {
    banner.hidden = true;
  }, 4200);
}

// validate-input-after-interaction: WeakMap fallback & ARIA synchronization for :user-invalid
const UserInvalidFallback = (() => {
  const dirtyState = new WeakMap();

  const updateState = (input) => {
    const isValid = input.checkValidity();
    input.classList.toggle("user-invalid-fallback", !isValid);
    input.classList.toggle("user-valid-fallback", isValid);
    if (!isValid) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
  };

  const handleEvent = (event) => {
    const input = event.target;
    if (event.type === "reset") {
      const controls = input.elements || [];
      for (const control of controls) {
        dirtyState.delete(control);
        control.classList.remove("user-invalid-fallback", "user-valid-fallback");
        control.removeAttribute("aria-invalid");
      }
      return;
    }
    if (!input.checkValidity) return;
    if (event.type === "input" || event.type === "change") {
      const state = dirtyState.get(input) || { hasInteracted: false, hasBlurred: false };
      state.hasInteracted = true;
      dirtyState.set(input, state);
      if (state.hasBlurred) updateState(input);
    } else if (event.type === "blur") {
      const state = dirtyState.get(input) || { hasInteracted: false, hasBlurred: false };
      state.hasBlurred = true;
      dirtyState.set(input, state);
      if (state.hasInteracted) updateState(input);
    }
  };

  const init = (root = document) => {
    if (CSS.supports("selector(:user-invalid)")) return;
    root.addEventListener("blur", handleEvent, true);
    root.addEventListener("input", handleEvent);
    root.addEventListener("change", handleEvent);
    root.addEventListener("reset", handleEvent, true);
  };

  return { init };
})();

const syncAria = (el) => {
  if (el && el.matches && CSS.supports("selector(:user-invalid)")) {
    el.setAttribute?.("aria-invalid", el.matches(":user-invalid") ? "true" : "false");
  }
};

async function fetchTransportState(forceFormUpdate = false) {
  const res = await fetch("/api/state");
  const data = await res.json();
  latestTransportState = data;
  renderTransportForms(data, forceFormUpdate);
}

function renderTransportForms(state, forceFormUpdate = false) {
  const trucks = state.trucks || [];
  if (!trucks.length) return;

  if (!trucks.some((t) => t.truck_id === selectedTransportTruckId)) {
    selectedTransportTruckId = trucks[0].truck_id;
  }

  // Suggest next unbooked Truck ID if user is not currently editing #bookTruckId
  const bookTruckIdEl = document.getElementById("bookTruckId");
  if (bookTruckIdEl && document.activeElement !== bookTruckIdEl) {
    const nextNum = 101 + trucks.length;
    bookTruckIdEl.value = `TRK-${nextNum}`;
  }

  // Populate Truck Dropdown in Form 1 (Edit Existing Truck ETA)
  const selectEl = document.getElementById("transportTruckSelect");
  if (selectEl && document.activeElement !== selectEl) {
    selectEl.innerHTML = trucks
      .map((t) => {
        const durMins = t.duration_mins || 60;
        const slotStr = t.scheduled_dock_id
          ? `${t.scheduled_dock_id} [${t.scheduled_slot_start}-${t.scheduled_slot_end}, ${durMins}m]`
          : `UNBOOKED (${durMins}m)`;
        const selectedAttr = t.truck_id === selectedTransportTruckId ? "selected" : "";
        return `<option value="${t.truck_id}" ${selectedAttr}>${t.truck_id} — ${t.carrier_name} (${slotStr}, Current ETA: ${t.current_eta})</option>`;
      })
      .join("");
  }

  populateSelectedTruckDetails(selectedTransportTruckId, forceFormUpdate);
}

function onSelectTransportTruck(truckId) {
  selectedTransportTruckId = truckId;
  populateSelectedTruckDetails(truckId, true);
}

function populateSelectedTruckDetails(truckId, forceUpdateInputs = true) {
  if (!latestTransportState) return;
  const truck = (latestTransportState.trucks || []).find((t) => t.truck_id === truckId);
  if (!truck) return;

  const analysesByTruck = {};
  (latestTransportState.eta_analyses || []).forEach((a) => {
    analysesByTruck[a.truck_id] = a;
  });
  const analysis = analysesByTruck[truckId] || {};

  const dispDriver = document.getElementById("transDispDriver");
  if (dispDriver) dispDriver.textContent = `${truck.carrier_name} • ${truck.driver_name}`;

  const dispCargo = document.getElementById("transDispCargo");
  const durMins = truck.duration_mins || analysis.duration_mins || 60;
  if (dispCargo) dispCargo.textContent = `${truck.cargo_type} (${truck.weight_tons}T • ${durMins}m)`;

  const dispSlot = document.getElementById("transDispSlot");
  if (dispSlot) {
    dispSlot.textContent = truck.scheduled_dock_id
      ? `${truck.scheduled_dock_id} • ${truck.scheduled_slot_start}-${truck.scheduled_slot_end} (${durMins}m)`
      : `UNBOOKED (${durMins}m Pending Slot)`;
  }

  const dispEta = document.getElementById("transDispCurrentEta");
  if (dispEta) {
    const varStr =
      analysis.variance_mins !== null && analysis.variance_mins !== undefined
        ? `${analysis.variance_mins >= 0 ? "+" : ""}${analysis.variance_mins}m`
        : "Unbooked";
    const overlapFlag = analysis.has_eta_overlap ? " • ⚠ OVERLAP" : "";
    dispEta.textContent = `${truck.current_eta} (${varStr}${overlapFlag})`;
  }

  if (forceUpdateInputs) {
    const etaInput = document.getElementById("transportNewEtaInput");
    const distInput = document.getElementById("transportDistanceInput");
    const notesInput = document.getElementById("transportNotesInput");
    if (etaInput) {
      etaInput.value = truck.current_eta;
      etaInput.classList.remove("user-invalid-fallback");
      etaInput.removeAttribute("aria-invalid");
    }
    if (distInput) {
      distInput.value = truck.distance_km !== undefined ? truck.distance_km : 25.0;
    }
    if (notesInput) {
      notesInput.value = truck.notes || "Carrier manual ETA update";
    }
  }
}

function shiftTransportFormEta(deltaMins) {
  const etaInput = document.getElementById("transportNewEtaInput");
  if (!etaInput) return;
  const parts = (etaInput.value || "09:00").split(":");
  let totalMins = parseInt(parts[0], 10) * 60 + parseInt(parts[1] || "0", 10) + deltaMins;
  totalMins = Math.max(0, Math.min(23 * 60 + 55, totalMins));
  const h = Math.floor(totalMins / 60);
  const m = totalMins % 60;
  etaInput.value = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function resetTransportFormToBooked() {
  if (!latestTransportState) return;
  const truck = (latestTransportState.trucks || []).find((t) => t.truck_id === selectedTransportTruckId);
  if (!truck) return;
  const etaInput = document.getElementById("transportNewEtaInput");
  if (etaInput) {
    etaInput.value = truck.scheduled_slot_start || truck.original_slot_start || "09:05";
  }
  const notesInput = document.getElementById("transportNotesInput");
  if (notesInput) {
    notesInput.value = "On schedule normal transit";
  }
}

function applyTransportReasonPreset(val) {
  const notesInput = document.getElementById("transportNotesInput");
  if (notesInput) {
    notesInput.value = val;
  }
}

async function submitTransportManualETA(event) {
  if (event) event.preventDefault();
  const submitBtn = document.getElementById("btnSubmitEta");
  if (submitBtn) submitBtn.disabled = true;

  try {
    const truckId = document.getElementById("transportTruckSelect").value;
    const newEta = document.getElementById("transportNewEtaInput").value;
    const distKm = parseFloat(document.getElementById("transportDistanceInput").value || "25");
    const notes = document.getElementById("transportNotesInput").value;

    const res = await fetch("/api/modify-eta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        truck_id: truckId,
        new_eta: newEta,
        distance_km: distKm,
        notes: notes,
        auto_execute: false,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(`Error updating ETA: ${err.detail}`);
      return;
    }

    const data = await res.json();
    latestTransportState = data.state;
    selectedTransportTruckId = truckId;
    renderTransportForms(data.state, false);

    const feedbackEl = document.getElementById("transportSubmissionFeedback");
    const prop = (data.state.pending_proposals || []).find(
      (p) => p.primary_truck_id === truckId || p.secondary_truck_id === truckId
    );

    if (feedbackEl) {
      if (prop) {
        feedbackEl.innerHTML = `<strong>&#10003; ETA Updated!</strong> <strong>${truckId}</strong> ETA set to <code>${newEta}</code>. Proposed schedule adjustment (<code>${prop.action_type}</code> &rarr; <code>${prop.new_dock_id}</code> [${prop.new_slot_start}-${prop.new_slot_end}]) sent to Scheduler.`;
      } else {
        feedbackEl.innerHTML = `<strong>&#10003; ETA Updated!</strong> <strong>${truckId}</strong> ETA set to <code>${newEta}</code> and aligned with its current dock slot.`;
      }
    }

    showToast(`Updated ETA for ${truckId} to ${newEta}!`);
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function submitNewTransportBooking(event) {
  if (event) event.preventDefault();
  const submitBtn = document.getElementById("btnSubmitSchedule");
  if (submitBtn) submitBtn.disabled = true;

  try {
    const truckId = document.getElementById("bookTruckId").value.trim();
    const carrierName = document.getElementById("bookCarrierName").value.trim();
    const driverName = document.getElementById("bookDriverName").value.trim();
    const cargoRadio = document.querySelector('input[name="cargo_type"]:checked');
    const cargoType = cargoRadio ? cargoRadio.value : "REFRIGERATED";
    const durRadio = document.querySelector('input[name="duration_mins"]:checked');
    const durationMins = durRadio ? parseInt(durRadio.value, 10) : 45;
    const weightTons = parseFloat(document.getElementById("bookWeightTons").value || "16.5");
    const distanceKm = parseFloat(document.getElementById("bookDistanceKm").value || "38.0");
    const currentEta = document.getElementById("bookTruckEta").value;
    const notes = document.getElementById("bookNotes").value.trim();

    const res = await fetch("/api/add-truck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        truck_id: truckId,
        carrier_name: carrierName,
        driver_name: driverName,
        cargo_type: cargoType,
        weight_tons: weightTons,
        distance_km: distanceKm,
        current_eta: currentEta,
        duration_mins: durationMins,
        notes: notes,
        auto_execute: false,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(`Error scheduling appointment: ${err.detail}`);
      return;
    }

    const data = await res.json();
    latestTransportState = data.state;
    selectedTransportTruckId = truckId;
    renderTransportForms(data.state, true);

    const feedbackEl = document.getElementById("transportBookingFeedback");
    const prop = (data.state.pending_proposals || []).find((p) => p.primary_truck_id === truckId);

    if (feedbackEl) {
      if (prop) {
        feedbackEl.innerHTML = `<strong>&#10003; Appointment Scheduled!</strong> <strong>${truckId}</strong> (${cargoType}, ${durationMins} min, ETA <code>${currentEta}</code>) matched to slot <code>${prop.new_dock_id}</code> [${prop.new_slot_start}-${prop.new_slot_end}] and sent to Scheduler.`;
      } else {
        feedbackEl.innerHTML = `<strong>&#10003; Appointment Registered!</strong> <strong>${truckId}</strong> (${durationMins} min) added with ETA <code>${currentEta}</code>.`;
      }
    }

    showToast(`Scheduled new ${durationMins}m appointment request for ${truckId} (ETA ${currentEta})!`);
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  UserInvalidFallback.init(document);
  document.addEventListener("blur", (e) => syncAria(e.target), true);
  document.addEventListener("input", (e) => {
    if (e.target && e.target.hasAttribute && e.target.hasAttribute("aria-invalid")) {
      syncAria(e.target);
    }
  });
  fetchTransportState(true);
  setInterval(() => {
    const active = document.activeElement;
    const isTyping = active && (active.tagName === "INPUT" || active.tagName === "SELECT");
    if (!isTyping) {
      fetchTransportState(false);
    }
  }, 4000);
});
