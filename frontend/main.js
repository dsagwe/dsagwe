let dashboard = null;
let employers = [];
let selected = null;
let detail = null;

const $ = (id) => document.getElementById(id);
const money = (value) => `KES ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;" }[c]));
const badge = (status) => `<span class="badge ${esc(status || "unknown")}">${esc(status || "unknown")}</span>`;

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadDashboard() {
  dashboard = await api("/api/dashboard");
  renderStats();
}

function renderStats() {
  const summary = dashboard?.summary || {};
  const cards = [
    ["Employers Monitored", summary.total_employers || 0, "Local registry records"],
    ["Total Arrears", money(summary.total_arrears), "Outstanding principal"],
    ["Penalty Exposure", money(summary.total_penalties), "2% statutory penalty"],
    ["Critical Cases", summary.critical_count || 0, "High-risk enforcement queue"],
    ["Average Risk", `${Number(summary.avg_risk || 0).toFixed(1)}%`, "Behavioral risk model"],
  ];
  $("stats").innerHTML = cards.map(([label, value, hint]) => `<div class="card pad"><div class="muted small">${label}</div><div class="metric">${value}</div><div class="muted small">${hint}</div></div>`).join("");
}

async function searchEmployers() {
  const q = encodeURIComponent($("query").value.trim());
  const data = await api(`/api/employers?q=${q}&limit=100`);
  employers = data.items || [];
  renderEmployers();
  if (!selected && employers[0]) await loadDetail(employers[0].id);
}

function renderEmployers() {
  $("employer-list").innerHTML = employers.map((e) => `
    <button class="item ${selected?.id === e.id ? "active" : ""}" data-employer-id="${e.id}">
      <div class="between"><strong>${esc(e.employer_name)}</strong>${badge(e.compliance_status)}</div>
      <div class="muted small">${esc(e.sha_employer_code)} · ${esc(e.kra_pin || "No KRA PIN")} · ${esc(e.county || "No county")}</div>
      <div class="small"><strong>${money(e.current_arrears)}</strong> arrears · risk ${Number(e.risk_score).toFixed(0)} · ${e.consecutive_default_months} consecutive default months</div>
    </button>`).join("") || `<div class="pad muted">No employers found.</div>`;
  document.querySelectorAll("[data-employer-id]").forEach((el) => el.addEventListener("click", () => loadDetail(el.dataset.employerId)));
}

async function loadDetail(id) {
  detail = await api(`/api/employers/${id}`);
  selected = detail.employer;
  renderEmployers();
  renderDetail();
}

function renderDetail() {
  const e = detail.employer;
  const activeCase = detail.cases.find((c) => c.status === "open");
  $("detail").innerHTML = `
    <div class="card pad">
      <div class="between"><div><h2>${esc(e.employer_name)}</h2><div class="muted small">${esc(e.sha_employer_code)} · ${esc(e.kra_pin || "No KRA PIN")} · ${esc(e.industry || "No industry")}</div></div>${badge(e.compliance_status)}</div>
      <div class="grid four" style="margin-top:16px">
        <div><div class="muted small">Arrears</div><strong>${money(e.current_arrears)}</strong></div>
        <div><div class="muted small">Penalties</div><strong>${money(e.penalty_exposure)}</strong></div>
        <div><div class="muted small">Risk Score</div><strong>${Number(e.risk_score).toFixed(0)}%</strong></div>
        <div><div class="muted small">Defaults</div><strong>${e.consecutive_default_months} months</strong></div>
      </div>
    </div>
    <div class="grid two">
      <div class="card pad"><h3>Officer Engagement Capture</h3><textarea id="engagement-summary" placeholder="Call notes, commitment, dispute, follow-up details..."></textarea><button id="log-engagement" class="btn teal" style="margin-top:10px">Log Immutable Engagement</button></div>
      <div class="card pad"><h3>Demand Notice Automation</h3><p class="muted small">Generate a legally traceable PDF and automatically record it in the engagement timeline.</p><select id="notice-type"><option value="first_demand">First demand</option><option value="final_demand">Repeat offender final demand</option><option value="litigation_warning">Litigation warning</option></select><button id="generate-notice" class="btn red" style="margin-top:10px">Generate PDF Notice</button></div>
    </div>
    <div class="grid two">
      <div class="card"><div class="pad"><strong>Remittance History Engine</strong></div><table><thead><tr><th>Period</th><th class="num">Due</th><th class="num">Paid</th><th class="num">Penalty</th></tr></thead><tbody>${detail.remittances.map((r) => `<tr><td>${esc(r.period)}</td><td class="num">${money(r.amount_due)}</td><td class="num">${money(r.amount_paid)}</td><td class="num">${money(r.statutory_penalty)}</td></tr>`).join("")}</tbody></table></div>
      <div class="card"><div class="pad"><strong>Compliance Cases</strong></div>${detail.cases.map((c) => `<div class="timeline"><strong>${esc(c.case_number)}</strong><div class="small">${esc(c.stage)} · priority ${c.priority} · due ${esc(c.due_at || "N/A")}</div><div class="muted small">${esc(c.summary || "")}</div></div>`).join("") || `<div class="pad muted">No cases.</div>`}</div>
    </div>
    <div class="card"><div class="pad"><strong>Immutable Engagement Timeline</strong></div>${detail.engagements.map((g) => `<div class="timeline"><div class="between"><strong>${esc(g.channel).replaceAll("_", " ")} · ${esc(g.outcome)}</strong><span class="muted small">${new Date(g.created_at).toLocaleString()}</span></div><p>${esc(g.summary)}</p><div class="muted small">Officer: ${esc(g.officer_name)} · Hash: ${esc(g.hash).slice(0, 16)}...</div></div>`).join("") || `<div class="pad muted">No engagements yet.</div>`}</div>`;

  $("log-engagement").addEventListener("click", () => createEngagement(activeCase));
  $("generate-notice").addEventListener("click", generateNotice);
}

async function createEngagement(activeCase) {
  const summary = $("engagement-summary").value.trim();
  if (!summary || !selected) return;
  await api(`/api/employers/${selected.id}/engagements`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-officer-id": "local-officer", "x-officer-name": "Local Compliance Officer", "x-role": "compliance_officer" },
    body: JSON.stringify({ case_id: activeCase?.id, channel: "call", summary, outcome: "contacted", follow_up_deadline: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10) })
  });
  await Promise.all([loadDashboard(), loadDetail(selected.id)]);
}

async function generateNotice() {
  if (!selected) return;
  const data = await api("/api/notices", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-officer-id": "local-officer", "x-officer-name": "Local Compliance Officer", "x-role": "compliance_officer" },
    body: JSON.stringify({ employer_ids: [selected.id], notice_type: $("notice-type").value })
  });
  await Promise.all([loadDashboard(), loadDetail(selected.id)]);
  const noticeId = data.generated_notice_ids?.[0];
  if (noticeId) window.open(`/api/notices/${noticeId}/download`, "_blank");
}

$("search").addEventListener("click", searchEmployers);
$("query").addEventListener("keydown", (e) => { if (e.key === "Enter") searchEmployers(); });
loadDashboard().then(searchEmployers).catch((err) => { $("detail").innerHTML = `<div class="card pad">${esc(err.message)}</div>`; });
