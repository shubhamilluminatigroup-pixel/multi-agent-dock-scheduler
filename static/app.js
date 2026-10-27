let latestState = null;

// Setup mandatory light-dismiss fallback for browsers without native <dialog closedby="any"> support
function initDialogLightDismissFallbacks() {
  const dialogs = document.querySelectorAll("dialog");
  dialogs.forEach((dialog) => {
    if (!("closedBy" in HTMLDialogElement.prototype)) {
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const isDialogContent =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width;
        if (isDialogContent) return;
        dialog.close();
      });
    }
  });
}

function showToast(msg) {
  const banner = document.getElementById("toastBanner");
  banner.textContent = msg;
  banner.hidden = false;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {
    banner.hidden = true;
  }, 4000);
}

function shiftHour(timeStr, deltaHours) {
  const parts = (timeStr || "09:00").split(":");
  let h = parseInt(parts[0], 10) + deltaHours;
  const m = parseInt(parts[1] || "0", 10);
  h = Math.max(0, Math.min(23, h));
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

async function fetchSystemState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  latestState = data;
  renderAll(data);
}

function switchViewTab(tabKey) {
  const tabs = ["gantt", "ops", "connections"];
  tabs.forEach((k) => {
    const isActive = k === tabKey;
    const li = document.getElementById(`tab-li-${k}`);
    const btn = document.getElementById(`tab-btn-${k}`);
    const panel = document.getElementById(`tabpanel-${k}`);
    if (li) li.classList.toggle("active", isActive);
    if (btn) btn.setAttribute("aria-selected", isActive ? "true" : "false");
    if (panel) panel.hidden = !isActive;
  });
}

function timeToPercent(timeStr) {
  // Maps 24-hour clock: 00:00 -> 0%, 24:00 -> 100% (1440 minutes span)
  if (!timeStr || timeStr === "HOLD") return 0;
  const parts = timeStr.split(":");
  const mins = parseInt(parts[0], 10) * 60 + parseInt(parts[1] || "0", 10);
  const pct = (mins / 1440) * 100;
  return Math.max(0, Math.min(100, pct));
}

function scrollGanttToHour(hourFloat, smooth = true) {
  const hourPx = 240; // Each hour is 240px wide (5760px / 24h)
  const targetLeft = Math.max(0, Math.round(hourFloat * hourPx));
  window.__ganttScrollLeft = targetLeft;
  const viewports = document.querySelectorAll(".gantt-scroll-viewport");
  viewports.forEach((vp) => {
    vp.scrollTo({
      left: targetLeft,
      behavior: smooth ? "smooth" : "auto",
    });
  });
}

function scrollGanttByDelta(deltaPx) {
  const firstVp = document.querySelector(".gantt-scroll-viewport");
  const currentLeft = firstVp ? firstVp.scrollLeft : window.__ganttScrollLeft || 0;
  const nextLeft = Math.max(0, currentLeft + deltaPx);
  window.__ganttScrollLeft = nextLeft;
  const viewports = document.querySelectorAll(".gantt-scroll-viewport");
  viewports.forEach((vp) => {
    vp.scrollTo({
      left: nextLeft,
      behavior: "smooth",
    });
  });
}

function bindSynchronizedGanttScroll() {
  const viewports = Array.from(document.querySelectorAll(".gantt-scroll-viewport"));
  if (!viewports.length) return;

  // Restore saved scroll position or center on 07:45 (Active Window 08:00-14:00) on first load
  if (window.__ganttScrollInitialized === undefined) {
    window.__ganttScrollInitialized = true;
    window.__ganttScrollLeft = Math.round(7.65 * 240);
  }
  const initialLeft = window.__ganttScrollLeft || 0;
  viewports.forEach((vp) => {
    vp.scrollLeft = initialLeft;
  });

  let isSyncing = false;
  viewports.forEach((vp) => {
    vp.addEventListener(
      "scroll",
      () => {
        if (isSyncing) return;
        isSyncing = true;
        const left = vp.scrollLeft;
        window.__ganttScrollLeft = left;
        viewports.forEach((other) => {
          if (other !== vp) {
            other.scrollLeft = left;
          }
        });
        requestAnimationFrame(() => {
          isSyncing = false;
        });
      },
      { passive: true }
    );
  });
}

function renderKPIs(state) {
  const totalTrucks = (state.trucks || []).length;
  const conflicts = (state.eta_analyses || []).filter((a) => a.requires_rescheduling).length;
  const proposals = (state.pending_proposals || []).length;
  const dispatches = (state.communications || []).length;

  const elTrucks = document.getElementById("kpiTotalTrucks");
  const elConflicts = document.getElementById("kpiConflicts");
  const elProposals = document.getElementById("kpiProposals");
  const elDispatches = document.getElementById("kpiDispatches");

  if (elTrucks) elTrucks.textContent = totalTrucks;
  if (elConflicts) elConflicts.textContent = conflicts;
  if (elProposals) elProposals.textContent = proposals;
  if (elDispatches) elDispatches.textContent = dispatches;
}

function renderAll(state) {
  const pendingCount = (state.pending_proposals || []).length;
  renderKPIs(state);
  renderAgentStrip(state);
  renderGanttChart(state);
  renderTruckTable(state);
  renderProposals(state.pending_proposals || []);
  renderCommunications(state.communications || []);
  renderConnections(state.connections || {});

  const badge = document.getElementById("pendingCountBadge");
  if (badge) badge.textContent = pendingCount;
  const opsBadge = document.getElementById("opsTabPendingCount");
  if (opsBadge) opsBadge.textContent = pendingCount;
}

function formatShortCargo(cargoType) {
  if (!cargoType) return "";
  if (cargoType === "REFRIGERATED") return "REFRIG";
  if (cargoType === "DRY_VAN") return "DRY VAN";
  return cargoType;
}

function renderGanttChart(state) {
  const docks = state.docks || [];
  const existing = state.existing_schedule || [];
  const simulated = state.simulated_new_schedule || [];

  const analysesByTruck = {};
  (state.eta_analyses || []).forEach((a) => {
    analysesByTruck[a.truck_id] = a;
  });

  const trucksById = {};
  (state.trucks || []).forEach((t) => {
    trucksById[t.truck_id] = t;
  });

  const proposalByTarget = {};
  (state.pending_proposals || []).forEach((p) => {
    proposalByTarget[`${p.new_dock_id}__${p.new_slot_start}`] = {
      type: p.action_type,
      truck: p.primary_truck_id,
      reason: p.reason,
    };
    if (p.secondary_truck_id && p.partner_new_dock_id && p.partner_new_slot_start) {
      proposalByTarget[`${p.partner_new_dock_id}__${p.partner_new_slot_start}`] = {
        type: p.action_type,
        truck: p.secondary_truck_id,
        reason: p.reason,
      };
    }
  });

  // Build 24-hour header ticks (00:00 -> 24:00) with 15/30/45m sub-tick ruler
  const ticksArr = [];
  const bgCellsArr = [];
  for (let h = 0; h < 24; h++) {
    const hStart = `${String(h).padStart(2, "0")}:00`;
    const hEnd = `${String(h + 1).padStart(2, "0")}:00`;
    const isActiveWindow = h >= 8 && h < 14;
    ticksArr.push(`
      <div class="gantt-tick ${isActiveWindow ? "tick-active-window" : ""}">
        <div>${hStart} &ndash; ${hEnd}</div>
        <div class="gantt-subtick-row">
          <span>:00</span>
          <span>:15</span>
          <span>:30</span>
          <span>:45</span>
        </div>
      </div>
    `);
    bgCellsArr.push(`
      <div class="gantt-bg-cell ${isActiveWindow ? "cell-active-window" : ""}">${hStart}</div>
    `);
  }

  const bgCellsHtml = bgCellsArr.join("");

  // Build Overlapping ETA Red Alert Banner if any trucks have overlapping ETAs
  const overlappingAnalyses = (state.eta_analyses || []).filter((a) => a.has_eta_overlap);
  let overlapBannerHtml = "";
  if (overlappingAnalyses.length > 0) {
    const chipsHtml = overlappingAnalyses
      .map((a) => {
        const partners = (a.overlapping_trucks || []).join(", ");
        const dockLbl = a.scheduled_dock_id || "DOCK-A";
        return `
          <span class="overlap-truck-chip" onclick="openETAModal('${a.truck_id}')" style="cursor:pointer;" title="${a.overlap_summary || "Click to edit ETA"}">
            &#9888; ${a.truck_id} (${a.duration_mins || 60}m, ETA ${a.current_eta}&ndash;${a.live_eta_end || ""}) &harr; ${partners} on ${dockLbl}
          </span>
        `;
      })
      .join("");
    overlapBannerHtml = `
      <div class="gantt-overlap-alert-banner" role="status">
        <div>
          <strong>&#9888; OVERLAPPING ETA RED INDICATOR (${overlappingAnalyses.length} Active Collision${overlappingAnalyses.length > 1 ? "s" : ""}):</strong>
          Live arrival window <code>[ETA &rarr; ETA + Duration]</code> collides with another appointment on the same dock:
        </div>
        <div class="overlap-chip-list">${chipsHtml}</div>
      </div>
    `;
  }

  const dockGanttContainer = document.getElementById("dockGanttContainer");
  dockGanttContainer.innerHTML =
    overlapBannerHtml +
    docks
      .map((dock) => {
        const existingSlots = existing.filter((r) => r.dock_id === dock.dock_id && r.assigned_truck_id);
        const proposedSlots = simulated.filter((r) => r.dock_id === dock.dock_id && r.assigned_truck_id);
        const existingByStart = {};
        existing
          .filter((r) => r.dock_id === dock.dock_id)
          .forEach((r) => {
            existingByStart[r.slot_start] = r;
          });

        const existingBarsHtml = existingSlots
          .map((slot) => {
            const tId = slot.assigned_truck_id;
            const truckObj = trucksById[tId] || {};
            const analysis = analysesByTruck[tId];
            const durationMins =
              slot.duration_mins || (analysis && analysis.duration_mins) || truckObj.duration_mins || 60;
            const leftPct = timeToPercent(slot.slot_start);
            const widthPct = (durationMins / 1440) * 100;

            const hasConflict = analysis && analysis.requires_rescheduling;
            const hasEtaOverlap = analysis && analysis.has_eta_overlap;
            const wasCommitted = slot.change_type && slot.change_type !== "NONE";
            const shortCargo = formatShortCargo(slot.cargo_type);

            let barClass = "bar-ok";
            let statusNote = `ETA ${analysis ? analysis.current_eta : ""} &bull; On Time`;
            let footerStatus = `${slot.slot_start}&ndash;${slot.slot_end} (${durationMins}m)`;

            if (hasEtaOverlap) {
              barClass = "bar-eta-overlap";
              const overlapWith = (analysis.overlapping_trucks || []).join(",");
              statusNote = `&#9888; ETA ${analysis.current_eta}&ndash;${analysis.live_eta_end} Overlaps ${overlapWith}`;
              footerStatus = `&#9888; OVERLAPPING ETA (${durationMins}m)`;
            } else if (hasConflict) {
              barClass = "bar-conflict";
              statusNote = `ETA ${analysis.current_eta} (${analysis.eta_classification})`;
              footerStatus = `${slot.slot_start}&ndash;${slot.slot_end} Conflict`;
            } else if (wasCommitted) {
              barClass = "bar-committed";
              statusNote = `ETA ${analysis ? analysis.current_eta : ""} &bull; Approved`;
              footerStatus = `${slot.change_type.replace(/_/g, " ")} (${durationMins}m)`;
            }

            const etaPinPct = analysis ? timeToPercent(analysis.current_eta) : null;
            const etaPinHtml =
              etaPinPct !== null
                ? `
                  <div class="gantt-eta-pin" style="left:${etaPinPct}%;">
                    <span class="gantt-eta-pin-label">&#9830; ${tId} ${analysis.current_eta}</span>
                  </div>
                `
                : "";

            return `
              <div
                class="gantt-bar ${barClass}"
                style="left:calc(${leftPct}% + 2px); width:calc(${widthPct}% - 4px);"
                onclick="openETAModal('${tId}')"
                title="Click to modify ${tId} ETA | ${slot.slot_start}-${slot.slot_end} (${durationMins} min, ${slot.cargo_type})${hasEtaOverlap ? " | " + analysis.overlap_summary : ""}"
              >
                <div class="gantt-bar-header-row">
                  <span class="gantt-bar-title">${tId}</span>
                  <div class="gantt-bar-badges">
                    <span class="gantt-duration-tag">${durationMins}m</span>
                    <span class="gantt-cargo-tag">${shortCargo}</span>
                  </div>
                </div>
                <div class="gantt-bar-sub">${statusNote}</div>
                <div class="gantt-bar-actions-row">
                  <span class="gantt-status-pill">${footerStatus}</span>
                </div>
              </div>
              ${etaPinHtml}
            `;
          })
          .join("");

        const proposedBarsHtml = proposedSlots
          .map((slot) => {
            const tId = slot.assigned_truck_id;
            const truckObj = trucksById[tId] || {};
            const analysis = analysesByTruck[tId];
            const durationMins =
              slot.duration_mins || (analysis && analysis.duration_mins) || truckObj.duration_mins || 60;
            const leftPct = timeToPercent(slot.slot_start);
            const widthPct = (durationMins / 1440) * 100;

            const hourSlotKey = `${ slot.slot_start.split(":")[0] }:00`;
            const propHit =
              proposalByTarget[`${dock.dock_id}__${slot.slot_start}`] ||
              proposalByTarget[`${dock.dock_id}__${hourSlotKey}`];
            const origRow = existingByStart[slot.slot_start] || existingByStart[hourSlotKey];
            const wasCommitted = origRow && origRow.change_type && origRow.change_type !== "NONE";
            const shortCargo = formatShortCargo(slot.cargo_type);

            let barClass = "bar-ok";
            let subText = `${slot.slot_start}&ndash;${slot.slot_end} (${durationMins}m) &bull; ETA ${analysis ? analysis.current_eta : ""}`;
            let bottomRowHtml = `<span class="gantt-status-pill">&#10003; Aligned (${durationMins}m)</span>`;

            if (propHit) {
              barClass = propHit.type === "BOOK_NEW_APPOINTMENT" ? "bar-new" : "bar-swap";
              const shortAction = propHit.type
                .replace("BOOK_NEW_APPOINTMENT", "NEW BOOKING")
                .replace(/_/g, " ");
              subText = `${shortAction} (${durationMins}m) &bull; ETA ${analysis ? analysis.current_eta : ""}`;
              bottomRowHtml = `
                <div class="gantt-chip-group">
                  <button
                    type="button"
                    class="gantt-approve-chip"
                    onclick="approveProposal('${tId}', event)"
                    title="Approve & Commit this schedule change for ${tId}"
                  >
                    &#10003; Approve
                  </button>
                  <button
                    type="button"
                    class="gantt-reject-chip"
                    onclick="rejectProposal('${tId}', event)"
                    title="Reject proposal and keep original slot for ${tId}"
                  >
                    &#10005;
                  </button>
                </div>
              `;
            } else if (wasCommitted) {
              barClass = "bar-committed";
              subText = `${slot.slot_start}&ndash;${slot.slot_end} (${durationMins}m) &bull; ETA ${analysis ? analysis.current_eta : ""}`;
              bottomRowHtml = `<span class="gantt-status-pill">&#10003; Approved (${origRow.change_type.replace(/_/g, " ")})</span>`;
            }

            return `
              <div
                class="gantt-bar ${barClass}"
                style="left:calc(${leftPct}% + 2px); width:calc(${widthPct}% - 4px);"
                onclick="openETAModal('${tId}')"
                title="${propHit ? propHit.reason : `Click to modify ${tId} ETA (${durationMins}m appointment)`}"
              >
                <div class="gantt-bar-header-row">
                  <span class="gantt-bar-title">${tId}</span>
                  <div class="gantt-bar-badges">
                    <span class="gantt-duration-tag">${durationMins}m</span>
                    <span class="gantt-cargo-tag">${shortCargo}</span>
                  </div>
                </div>
                <div class="gantt-bar-sub">${subText}</div>
                <div class="gantt-bar-actions-row">
                  ${bottomRowHtml}
                </div>
              </div>
            `;
          })
          .join("");

        return `
          <div class="gantt-dock-card">
            <div class="gantt-dock-header">
              <span class="dock-title">${dock.dock_name} <code>${dock.dock_id}</code></span>
              <span class="dock-caps">24-Hr Timeline (00:00&ndash;24:00) &bull; Supported Cargo: <code>${dock.supported_cargo}</code> &bull; Max: <strong>${dock.max_weight_tons}T</strong></span>
            </div>
            <div class="gantt-split-board">
              <div class="gantt-frozen-col">
                <div class="gantt-frozen-header">Schedule Track</div>
                <div class="gantt-frozen-track-label">
                  <div>1. Existing Schedule</div>
                  <div class="gantt-track-sub">Current DB + &#9830; Live ETA Pins</div>
                </div>
                <div class="gantt-frozen-track-label">
                  <div class="gantt-track-label-proposed">2. Proposed Schedule</div>
                  <div class="gantt-track-sub">Click &#10003; Approve on bar to commit</div>
                </div>
              </div>
              <div class="gantt-scroll-viewport">
                <div class="gantt-scroll-inner">
                  <div class="gantt-time-ticks">
                    ${ticksArr.join("")}
                  </div>
                  <div class="gantt-track-canvas-row">
                    <div class="gantt-timeline-canvas">${bgCellsHtml}${existingBarsHtml}</div>
                  </div>
                  <div class="gantt-track-canvas-row">
                    <div class="gantt-timeline-canvas">${bgCellsHtml}${proposedBarsHtml}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

  bindSynchronizedGanttScroll();
}

function renderAgentStrip(state) {
  const logs = state.agent_preview_logs || [];
  logs.forEach((item, idx) => {
    const el = document.getElementById(`agent-log-${idx + 1}`);
    if (el) {
      el.textContent = item.message.replace(/^\[[^\]]+\]\s*/, "");
    }
  });
  const commCount = (state.communications || []).length;
  const el5 = document.getElementById("agent-log-5");
  if (el5) {
    el5.textContent = `${commCount} decisions/notifications dispatched to Master Scheduler & Drivers.`;
  }
}

function renderTruckTable(state) {
  const tbody = document.getElementById("truckTableBody");
  const trucks = state.trucks || [];
  const analysesByTruck = {};
  (state.eta_analyses || []).forEach((a) => {
    analysesByTruck[a.truck_id] = a;
  });

  const proposalByTruck = {};
  (state.pending_proposals || []).forEach((p) => {
    proposalByTruck[p.primary_truck_id] = {
      action: p.action_type,
      targetDock: p.new_dock_id,
      targetSlot: `${p.new_slot_start}-${p.new_slot_end}`,
      partner: p.secondary_truck_id,
      reason: p.reason,
    };
    if (p.secondary_truck_id) {
      const pEnd =
        p.partner_new_slot_end ||
        `${String(parseInt(p.partner_new_slot_start.split(":")[0], 10) + 1).padStart(2, "0")}:00`;
      proposalByTruck[p.secondary_truck_id] = {
        action: p.action_type,
        targetDock: p.partner_new_dock_id,
        targetSlot: `${p.partner_new_slot_start}-${pEnd}`,
        partner: p.primary_truck_id,
        reason: p.reason,
      };
    }
  });

  tbody.innerHTML = trucks
    .map((t) => {
      const analysis = analysesByTruck[t.truck_id] || {};
      const prop = proposalByTruck[t.truck_id];
      const durMins = t.duration_mins || analysis.duration_mins || 60;

      const origSlot = t.original_dock_id
        ? `<code>${t.original_dock_id}</code> [${t.original_slot_start}-${t.original_slot_end}] <span class="badge-duration-pill">${durMins}m</span>`
        : `<span class="badge badge-new">UNBOOKED NEW</span> <span class="badge-duration-pill">${durMins}m</span>`;

      let currentSlot = `<span class="badge badge-warn">Not Booked Yet</span> <span class="badge-duration-pill">${durMins}m</span>`;
      if (t.scheduled_dock_id === "HOLD") {
        currentSlot = `<span class="badge badge-danger">MANUAL HOLD (Rejected)</span>`;
      } else if (t.scheduled_dock_id) {
        currentSlot = `<code>${t.scheduled_dock_id}</code> [${t.scheduled_slot_start}-${t.scheduled_slot_end}] <span class="badge-duration-pill">${durMins}m</span>`;
      }

      let statusBadgeClass = "badge-ok";
      if (analysis.eta_classification === "DELAYED") statusBadgeClass = "badge-danger";
      else if (analysis.eta_classification === "EARLY") statusBadgeClass = "badge-warn";
      else if (analysis.eta_classification === "UNBOOKED") statusBadgeClass = "badge-new";
      else if (analysis.eta_classification === "KEPT_ORIGINAL") statusBadgeClass = "badge-rescheduled";

      const varianceStr =
        analysis.variance_mins !== null && analysis.variance_mins !== undefined
          ? `${analysis.variance_mins >= 0 ? "+" : ""}${analysis.variance_mins}m`
          : "New";

      const overlapBadgeHtml = analysis.has_eta_overlap
        ? `<div style="margin-top:0.22rem;"><span class="badge badge-overlap-red" title="${analysis.overlap_summary || ""}">&#9888; OVERLAPS ${(analysis.overlapping_trucks || []).join(", ")}</span></div>`
        : "";

      let proposedHtml = `<span class="badge badge-ok">&#10003; Aligned / Approved</span>`;
      if (prop) {
        const badgeStyle =
          prop.action === "BOOK_NEW_APPOINTMENT" ? "badge-new" : "badge-swap";
        proposedHtml = `
          <div>
            <span class="badge ${badgeStyle}">${prop.action.replace(/_/g, " ")}</span>
            <div style="margin-top:0.25rem;font-size:0.75rem;">
              &rarr; <code>${prop.targetDock}</code> <strong>[${prop.targetSlot}]</strong>
              ${prop.partner ? `(with <strong>${prop.partner}</strong>)` : ""}
            </div>
            <div class="proposal-actions">
              <button type="button" class="btn btn-approve btn-xs" onclick="approveProposal('${t.truck_id}', event)">
                &#10003; Approve
              </button>
              <button type="button" class="btn btn-reject btn-xs" onclick="rejectProposal('${t.truck_id}', event)">
                &#10005; Reject
              </button>
            </div>
          </div>
        `;
      } else if (analysis.eta_classification === "KEPT_ORIGINAL") {
        proposedHtml = `<span class="badge badge-rescheduled">Kept Original Slot</span>`;
      }

      const minus1h = shiftHour(t.current_eta, -1);
      const plus1h = shiftHour(t.current_eta, 1);

      return `
        <tr>
          <th scope="row">
            <div>${t.truck_id}</div>
            <div style="font-size:0.72rem;color:#64748b;font-weight:500;">${t.carrier_name} &bull; ${t.driver_name}</div>
          </th>
          <td>
            <code>${t.cargo_type}</code>
            <div style="font-size:0.71rem;color:#64748b;margin-top:0.15rem;">${t.weight_tons} Tons &bull; <strong>${durMins} min</strong></div>
          </td>
          <td>${origSlot}</td>
          <td>${currentSlot}</td>
          <td>
            <div style="font-weight:700;font-size:0.88rem;font-family:'JetBrains Mono',monospace;">${t.current_eta} <span style="font-size:0.7rem;color:#64748b;font-weight:500;">(&rarr;${analysis.live_eta_end || ""})</span></div>
            <span class="badge ${statusBadgeClass}">${analysis.eta_classification || t.eta_status} (${varianceStr})</span>
            ${overlapBadgeHtml}
          </td>
          <td>${proposedHtml}</td>
          <td>
            <div class="eta-controls-group">
              <button type="button" class="btn btn-secondary btn-xs" onclick="quickModifyETA('${t.truck_id}', '${minus1h}')" title="Simulate 1 hr earlier arrival">
                -1h
              </button>
              <button type="button" class="btn btn-secondary btn-xs" onclick="quickModifyETA('${t.truck_id}', '${plus1h}')" title="Simulate 1 hr delay">
                +1h
              </button>
              <button type="button" class="btn btn-outline btn-xs" onclick="openETAModal('${t.truck_id}')" title="Inspect or adjust ETA for ${t.truck_id}">
                Edit ETA
              </button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderProposals(proposals) {
  const countLabel = document.getElementById("proposalCountLabel");
  if (countLabel) {
    countLabel.textContent = `${proposals.length} Pending`;
  }
  const container = document.getElementById("proposalsList");
  if (!container) return;

  if (!proposals.length) {
    container.innerHTML = `
      <div class="feed-item">
        <strong>All Proposed Schedule Changes Approved or Aligned!</strong>
        <p style="margin:0.25rem 0 0;color:#64748b;">
          Modify any truck's ETA in the table below (or select a scenario in the top bar) to generate new dynamic slot swap, dock swap, or appointment booking proposals.
        </p>
      </div>
    `;
    return;
  }

  container.innerHTML = proposals
    .map(
      (p) => `
      <div class="feed-item feed-swap">
        <div class="feed-top">
          <span>
            <span class="badge badge-swap">${p.action_type.replace(/_/g, " ")}</span> &bull;
            <strong>${p.primary_truck_id}</strong> ${p.secondary_truck_id ? `&harr; <strong>${p.secondary_truck_id}</strong>` : ""}
          </span>
          <span class="feed-time">ETA: ${p.eta}</span>
        </div>
        <div>${p.reason}</div>
        <div class="proposal-actions">
          <button type="button" class="btn btn-approve btn-xs" onclick="approveProposal('${p.primary_truck_id}', event)">
            &#10003; Approve &amp; Commit
          </button>
          <button type="button" class="btn btn-reject btn-xs" onclick="rejectProposal('${p.primary_truck_id}', event)">
            &#10005; Reject / Keep Original Slot
          </button>
        </div>
      </div>
    `
    )
    .join("");
}

function renderCommunications(comms) {
  const countLabel = document.getElementById("commCountLabel");
  if (countLabel) countLabel.textContent = `${comms.length} Dispatches`;
  const container = document.getElementById("communicationsList");
  if (!container) return;

  if (!comms.length) {
    container.innerHTML = `
      <div class="feed-item">
        <strong>No Scheduler Dispatches Yet</strong>
        <p style="margin:0.25rem 0 0;color:#64748b;">
          Click <em>"&#10003; Approve"</em> on any proposed change to commit the schedule update and notify the Master Scheduler.
        </p>
      </div>
    `;
    return;
  }

  container.innerHTML = comms
    .map(
      (c) => `
      <div class="feed-item feed-comm">
        <div class="feed-top">
          <span>${c.recipient_name} &bull; <span class="badge ${c.status === "REJECTED_BY_USER" ? "badge-danger" : "badge-ok"}">${c.status}</span></span>
          <span class="feed-time">${c.timestamp}</span>
        </div>
        <div>${c.summary}</div>
      </div>
    `
    )
    .join("");
}

function pulseAgentCards() {
  for (let i = 1; i <= 5; i++) {
    const card = document.getElementById(`agent-card-${i}`);
    if (!card) continue;
    setTimeout(() => {
      card.classList.add("active-pulse");
      setTimeout(() => card.classList.remove("active-pulse"), 650);
    }, (i - 1) * 120);
  }
}

async function approveProposal(truckId, event) {
  if (event) event.stopPropagation();
  pulseAgentCards();
  const res = await fetch("/api/approve-proposal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ truck_id: truckId }),
  });
  if (!res.ok) {
    const err = await res.json();
    showToast(`Approval error: ${err.detail}`);
    return;
  }
  const data = await res.json();
  latestState = data.state;
  renderAll(data.state);
  const count =
    data.decision_result && data.decision_result.executed_proposals
      ? data.decision_result.executed_proposals.length
      : 1;
  showToast(
    `Approved & committed schedule change for ${truckId} (${count} operation${count > 1 ? "s" : ""} persisted to DBs)!`
  );
}

async function rejectProposal(truckId, event) {
  if (event) event.stopPropagation();
  const res = await fetch("/api/reject-proposal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ truck_id: truckId }),
  });
  if (!res.ok) {
    const err = await res.json();
    showToast(`Rejection error: ${err.detail}`);
    return;
  }
  const data = await res.json();
  latestState = data.state;
  renderAll(data.state);
  showToast(`Rejected proposed change for ${truckId}; kept original slot.`);
}

async function quickModifyETA(truckId, newEta) {
  const autoExec = document.getElementById("autoExecuteToggle").checked;
  const res = await fetch("/api/modify-eta", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      truck_id: truckId,
      new_eta: newEta,
      auto_execute: autoExec,
    }),
  });
  const data = await res.json();
  latestState = data.state;
  pulseAgentCards();
  renderAll(data.state);
  showToast(
    autoExec
      ? `Updated ${truckId} ETA to ${newEta} and auto-approved 5-Agent Schedule Update!`
      : `Updated ${truckId} ETA to ${newEta} in truck_db.sqlite! Review & approve the new proposal.`
  );
}

async function applyInlineETA(truckId) {
  const input = document.getElementById(`inline-eta-${truckId}`);
  if (!input || !input.value) return;
  await quickModifyETA(truckId, input.value);
}

function openETAModal(truckId) {
  if (!latestState) return;
  const truck = (latestState.trucks || []).find((t) => t.truck_id === truckId);
  if (!truck) return;

  document.getElementById("modalTruckId").value = truck.truck_id;
  document.getElementById("modalTruckDisplay").value = `${truck.truck_id} - ${truck.carrier_name} (${truck.cargo_type}, ${truck.weight_tons}T)`;
  document.getElementById("modalCurrentSlot").value = truck.scheduled_dock_id
    ? `${truck.scheduled_dock_id} [${truck.scheduled_slot_start} - ${truck.scheduled_slot_end}]`
    : "UNBOOKED (Needs New Appointment)";
  document.getElementById("modalNewEta").value = truck.current_eta;
  document.getElementById("modalNotes").value = truck.notes || "";

  document.getElementById("etaModal").showModal();
}

async function submitModalETA(event) {
  event.preventDefault();
  const truckId = document.getElementById("modalTruckId").value;
  const newEta = document.getElementById("modalNewEta").value;
  const notes = document.getElementById("modalNotes").value;
  const autoExec = document.getElementById("autoExecuteToggle").checked;

  const res = await fetch("/api/modify-eta", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      truck_id: truckId,
      new_eta: newEta,
      notes: notes,
      auto_execute: autoExec,
    }),
  });
  const data = await res.json();
  document.getElementById("etaModal").close();
  latestState = data.state;
  pulseAgentCards();
  renderAll(data.state);
  showToast(`Saved custom ETA ${newEta} for ${truckId}.`);
}

async function executeMultiAgentPipeline() {
  pulseAgentCards();
  const res = await fetch("/api/run-agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      auto_execute: true,
      trigger_source: "UI_APPROVE_ALL_BUTTON",
    }),
  });
  const data = await res.json();
  latestState = data.state;
  renderAll(data.state);
  const executedCount = data.pipeline_result.proposals.length;
  showToast(
    executedCount > 0
      ? `Approved & executed ${executedCount} schedule changes across schedule_db.sqlite & truck_db.sqlite!`
      : `All schedules are already approved and aligned with live ETAs.`
  );
}

async function loadScenario(scenarioId, btnEl) {
  if (btnEl) {
    document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
    btnEl.classList.add("active");
  }
  const res = await fetch("/api/preset-scenario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario_id: scenarioId }),
  });
  const data = await res.json();
  latestState = data.state;
  pulseAgentCards();
  renderAll(data.state);
  showToast(`Loaded synthetic scenario: ${scenarioId}. Review & approve proposed changes.`);
}

async function resetDatabases() {
  document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  const fullBtn = document.getElementById("scen-full");
  if (fullBtn) fullBtn.classList.add("active");

  const res = await fetch("/api/reset", { method: "POST" });
  const data = await res.json();
  latestState = data.state;
  pulseAgentCards();
  renderAll(data.state);
  showToast("Reset both SQLite databases to initial synthetic baseline.");
}

// ============================================================================
// DB & EXTERNAL SYSTEM CONNECTIONS HUB (Truck DB, Schedule DB, Live ETA Link)
// ============================================================================
function renderConnections(connections) {
  const keys = ["truck_connection", "schedule_connection", "eta_connection"];
  let connectedCount = 0;

  keys.forEach((key, idx) => {
    const conn = connections[key];
    if (!conn) return;
    if (conn.status === "CONNECTED") connectedCount += 1;

    const typeEl = document.getElementById(`type-${key}`);
    const linkEl = document.getElementById(`link-${key}`);
    const tableEl = document.getElementById(`table-${key}`);
    const tokenEl = document.getElementById(`token-${key}`);
    const badgeEl = document.getElementById(`status-badge-${key}`);
    const diagEl = document.getElementById(`diag-${key}`);

    if (typeEl && document.activeElement !== typeEl) typeEl.value = conn.connector_type;
    if (linkEl && document.activeElement !== linkEl) linkEl.value = conn.connection_link;
    if (tableEl && document.activeElement !== tableEl) tableEl.value = conn.db_table_or_endpoint || "";
    if (tokenEl && document.activeElement !== tokenEl && conn.api_key_or_token !== undefined) {
      tokenEl.value = conn.api_key_or_token;
    }

    if (badgeEl) {
      badgeEl.textContent = conn.status || "CONNECTED";
      badgeEl.className = `badge ${conn.status === "CONNECTED" ? "badge-ok" : "badge-danger"}`;
    }
    if (diagEl) {
      diagEl.classList.toggle("status-error", conn.status !== "CONNECTED");
      const timeStr = conn.last_tested ? ` (Verified ${conn.last_tested.split(" ")[1] || conn.last_tested})` : "";
      diagEl.innerHTML = `<strong>[${conn.bound_agent} &rarr; ${conn.connector_type}]</strong> ${conn.last_message || "Ready."}${timeStr}`;
    }

    // Update top 5-Agent pipeline pill with compact protocol label so agent cards stay cleanly formatted
    const agentCardPill = document.querySelector(`#agent-card-${idx + 1} .agent-db-pill`);
    if (agentCardPill) {
      const shortLabels = {
        SQLITE_DB: "SQLite DB",
        REST_API: "REST API",
        SQL_URI: "SQL URI",
        REST_TELEMATICS_API: "Telematics API",
        INTERNAL_TRUCK_DB: "Truck DB",
        WEBHOOK_FEED: "Webhook",
      };
      agentCardPill.textContent = shortLabels[conn.connector_type] || conn.connector_type;
    }
  });

  const connCountBadge = document.getElementById("activeConnCountBadge");
  if (connCountBadge) {
    connCountBadge.textContent = `${connectedCount}/3 Linked`;
  }
}

function applyConnectorPreset(targetKey, presetCode) {
  const typeEl = document.getElementById(`type-${targetKey}`);
  const linkEl = document.getElementById(`link-${targetKey}`);
  const tableEl = document.getElementById(`table-${targetKey}`);
  const tokenEl = document.getElementById(`token-${targetKey}`);

  if (targetKey === "truck_connection") {
    if (presetCode === "SQLITE_DEFAULT") {
      typeEl.value = "SQLITE_DB";
      linkEl.value = "sqlite:///data/truck_db.sqlite";
      tableEl.value = "trucks";
    } else if (presetCode === "SQLITE_EXTERNAL") {
      typeEl.value = "SQLITE_DB";
      linkEl.value = "sqlite:///data/external_tms_trucks.sqlite";
      tableEl.value = "trucks";
    } else if (presetCode === "REST_MOCK") {
      typeEl.value = "REST_API";
      linkEl.value = `${window.location.origin}/api/external-mock/tms-trucks`;
      tableEl.value = "/api/external-mock/tms-trucks";
    } else if (presetCode === "POSTGRES_URI") {
      typeEl.value = "SQL_URI";
      linkEl.value = "postgresql://tms_reader:secret@erp-db.logistics.internal:5432/fleet_tms";
      tableEl.value = "public.trucks";
    }
  } else if (targetKey === "schedule_connection") {
    if (presetCode === "SQLITE_DEFAULT") {
      typeEl.value = "SQLITE_DB";
      linkEl.value = "sqlite:///data/schedule_db.sqlite";
      tableEl.value = "schedule_records, docks";
    } else if (presetCode === "SQLITE_EXTERNAL") {
      typeEl.value = "SQLITE_DB";
      linkEl.value = "sqlite:///data/external_wms_schedule.sqlite";
      tableEl.value = "schedule_records, docks";
    } else if (presetCode === "REST_MOCK") {
      typeEl.value = "REST_API";
      linkEl.value = `${window.location.origin}/api/external-mock/wms-schedule`;
      tableEl.value = "/api/external-mock/wms-schedule";
    } else if (presetCode === "POSTGRES_URI") {
      typeEl.value = "SQL_URI";
      linkEl.value = "postgresql://wms_scheduler:secret@wms-db.warehouse.internal:5432/dock_master";
      tableEl.value = "public.schedule_records";
    }
  } else if (targetKey === "eta_connection") {
    if (presetCode === "TELEMATICS_REST") {
      typeEl.value = "REST_TELEMATICS_API";
      linkEl.value = `${window.location.origin}/api/external-mock/telematics-eta`;
      tableEl.value = "/api/external-mock/telematics-eta";
      tokenEl.value = "telematics-demo-token-2026";
    } else if (presetCode === "INTERNAL_DB") {
      typeEl.value = "INTERNAL_TRUCK_DB";
      linkEl.value = "sqlite:///data/truck_db.sqlite";
      tableEl.value = "trucks.current_eta";
    } else if (presetCode === "SAMSARA_WEBHOOK") {
      typeEl.value = "WEBHOOK_FEED";
      linkEl.value = "https://api.samsara.com/fleet/vehicles/locations/eta-stream";
      tableEl.value = "v1/fleet/eta-webhook";
    }
  }

  linkEl.classList.remove("user-invalid-fallback");
  linkEl.removeAttribute("aria-invalid");
  showToast(`Loaded preset (${presetCode}) for ${targetKey}. Click 'Save & Bind to Agent' to activate.`);
}

async function testConnectionConfig(targetKey) {
  const connectorType = document.getElementById(`type-${targetKey}`).value;
  const connectionLink = document.getElementById(`link-${targetKey}`).value;
  const dbTable = document.getElementById(`table-${targetKey}`).value;
  const token = document.getElementById(`token-${targetKey}`).value;

  const res = await fetch("/api/connections/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target_key: targetKey,
      connector_type: connectorType,
      connection_link: connectionLink,
      db_table_or_endpoint: dbTable,
      auth_mode: token ? "API_KEY_HEADER" : "NONE",
      api_key_or_token: token,
    }),
  });
  const data = await res.json();
  const tr = data.test_result;
  const diagEl = document.getElementById(`diag-${targetKey}`);
  const badgeEl = document.getElementById(`status-badge-${targetKey}`);
  if (diagEl) {
    diagEl.classList.toggle("status-error", !tr.ok);
    diagEl.innerHTML = `<strong>[Test Result: ${tr.status}]</strong> ${tr.message}`;
  }
  if (badgeEl) {
    badgeEl.textContent = tr.status;
    badgeEl.className = `badge ${tr.ok ? "badge-ok" : "badge-danger"}`;
  }
  showToast(tr.message);
}

async function saveConnectionConfig(event, targetKey) {
  event.preventDefault();
  const connectorType = document.getElementById(`type-${targetKey}`).value;
  const connectionLink = document.getElementById(`link-${targetKey}`).value;
  const dbTable = document.getElementById(`table-${targetKey}`).value;
  const token = document.getElementById(`token-${targetKey}`).value;

  const res = await fetch("/api/connections/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target_key: targetKey,
      connector_type: connectorType,
      connection_link: connectionLink,
      db_table_or_endpoint: dbTable,
      auth_mode: token ? "API_KEY_HEADER" : "NONE",
      api_key_or_token: token,
      sync_mode: "LIVE_QUERY",
    }),
  });
  const data = await res.json();
  latestState = data.state;
  pulseAgentCards();
  renderAll(data.state);
  showToast(`Bound ${data.connection.bound_agent} to ${connectorType} link (${connectionLink})!`);
}

async function syncAgentViaLink(targetKey) {
  const res = await fetch("/api/connections/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_key: targetKey }),
  });
  const data = await res.json();
  latestState = data.state;
  pulseAgentCards();
  renderAll(data.state);
  showToast(data.sync_summary);
}

async function resetConnectionsToDefaults() {
  const res = await fetch("/api/connections/reset-defaults", { method: "POST" });
  const data = await res.json();
  latestState = data.state;
  pulseAgentCards();
  renderAll(data.state);
  showToast("Restored all 3 Agent connections to default local SQLite DBs.");
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

window.addEventListener("DOMContentLoaded", () => {
  initDialogLightDismissFallbacks();
  UserInvalidFallback.init(document);
  document.addEventListener("blur", (e) => syncAria(e.target), true);
  document.addEventListener("input", (e) => {
    if (e.target && e.target.hasAttribute && e.target.hasAttribute("aria-invalid")) {
      syncAria(e.target);
    }
  });
  fetchSystemState();
  // Automatically sync updates submitted from the separate /transport portal
  setInterval(() => {
    const modal = document.getElementById("etaModal");
    if (modal && modal.open) return;
    fetchSystemState();
  }, 4000);
});
