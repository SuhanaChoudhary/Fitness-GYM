"use strict";

const clientForm = document.getElementById("client-form");
const clientList = document.getElementById("client-list");
const summaryBox = document.getElementById("summary");
const chartBox = document.getElementById("adherence-chart");
const workoutRows = document.getElementById("workout-rows");
const progressForm = document.getElementById("progress-form");
const workoutForm = document.getElementById("workout-form");
const toast = document.getElementById("toast");

let selectedClient = null;

function notify(message, isError) {
  toast.textContent = message;
  toast.classList.toggle("error", Boolean(isError));
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 3200);
}

async function api(path, options) {
  const response = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, options));
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || "Request failed");
  }
  return body;
}

function formValues(form) {
  const data = {};
  new FormData(form).forEach((value, key) => { data[key] = value; });
  return data;
}

function requireClient() {
  if (!selectedClient) {
    notify("Select a client first", true);
    return false;
  }
  return true;
}

async function loadClients(preferred) {
  const { clients } = await api("/api/clients");
  clientList.replaceChildren();
  clients.forEach((client) => {
    const option = document.createElement("option");
    option.value = client.name;
    option.textContent = client.name;
    clientList.appendChild(option);
  });
  const target = preferred || selectedClient || (clients[0] && clients[0].name);
  if (target) {
    clientList.value = target;
    await selectClient(target);
  }
}

function metric(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "metric";
  const title = document.createElement("span");
  title.textContent = label;
  const amount = document.createElement("strong");
  amount.textContent = value;
  wrapper.append(title, amount);
  return wrapper;
}

function renderSummary(summary) {
  summaryBox.replaceChildren();
  const grid = document.createElement("div");
  grid.className = "metric-grid";
  grid.append(
    metric("Program", summary.program.name),
    metric("Calories", summary.calories ? `${summary.calories} kcal` : "-"),
    metric("BMI", summary.bmi ? `${summary.bmi} (${summary.bmi_category})` : "-"),
    metric("Avg adherence", `${summary.average_adherence}%`),
    metric("Weeks logged", summary.weeks_logged),
    metric("Workouts", `${summary.total_workouts} / ${summary.total_minutes} min`),
    metric("Membership", summary.membership.status),
    metric("On track", summary.on_track ? "Yes" : "No")
  );
  summaryBox.appendChild(grid);

  const detail = document.createElement("p");
  detail.textContent = summary.program.description;
  summaryBox.appendChild(detail);
}

function renderChart(entries) {
  chartBox.replaceChildren();
  if (!entries.length) {
    chartBox.textContent = "No progress entries yet.";
    return;
  }
  entries.slice(-12).forEach((entry) => {
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${Math.max(entry.adherence, 2)}%`;
    const value = document.createElement("span");
    value.textContent = `${entry.adherence}%`;
    const label = document.createElement("em");
    label.textContent = entry.week;
    bar.append(value, label);
    chartBox.appendChild(bar);
  });
}

function renderWorkouts(workouts) {
  workoutRows.replaceChildren();
  workouts.forEach((workout) => {
    const row = document.createElement("tr");
    [workout.date, workout.workout_type, workout.duration_min, workout.notes || ""].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
    workoutRows.appendChild(row);
  });
}

function fillForm(client) {
  clientForm.name.value = client.name;
  clientForm.age.value = client.age ?? "";
  clientForm.height_cm.value = client.height_cm ?? "";
  clientForm.weight_kg.value = client.weight_kg ?? "";
  clientForm.target_weight_kg.value = client.target_weight_kg ?? "";
  clientForm.target_adherence.value = client.target_adherence ?? "";
  clientForm.membership_end.value = client.membership_end ?? "";
  clientForm.program.value = client.program;
}

async function selectClient(name) {
  selectedClient = name;
  const encoded = encodeURIComponent(name);
  const [{ client, summary }, { progress }, { workouts }] = await Promise.all([
    api(`/api/clients/${encoded}`),
    api(`/api/clients/${encoded}/progress`),
    api(`/api/clients/${encoded}/workouts`),
  ]);
  fillForm(client);
  renderSummary(summary);
  renderChart(progress);
  renderWorkouts(workouts);
}

clientForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const { client } = await api("/api/clients", {
      method: "POST",
      body: JSON.stringify(formValues(clientForm)),
    });
    notify(`Saved ${client.name}`);
    await loadClients(client.name);
  } catch (error) {
    notify(error.message, true);
  }
});

clientList.addEventListener("change", () => selectClient(clientList.value).catch((e) => notify(e.message, true)));

progressForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireClient()) return;
  try {
    await api(`/api/clients/${encodeURIComponent(selectedClient)}/progress`, {
      method: "POST",
      body: JSON.stringify(formValues(progressForm)),
    });
    progressForm.reset();
    notify("Progress recorded");
    await selectClient(selectedClient);
  } catch (error) {
    notify(error.message, true);
  }
});

workoutForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireClient()) return;
  try {
    await api(`/api/clients/${encodeURIComponent(selectedClient)}/workouts`, {
      method: "POST",
      body: JSON.stringify(formValues(workoutForm)),
    });
    notify("Workout logged");
    await selectClient(selectedClient);
  } catch (error) {
    notify(error.message, true);
  }
});

document.getElementById("generate-program").addEventListener("click", async () => {
  if (!requireClient()) return;
  const goal = window.prompt("Goal (fat_loss, muscle_gain, general):", "fat_loss");
  if (goal === null) return;
  const level = window.prompt("Level (beginner, intermediate, advanced):", "beginner");
  if (level === null) return;
  try {
    const { program } = await api(`/api/clients/${encodeURIComponent(selectedClient)}/program`, {
      method: "POST",
      body: JSON.stringify({ goal, level }),
    });
    notify(`Program set to ${program.name}`);
    await selectClient(selectedClient);
  } catch (error) {
    notify(error.message, true);
  }
});

document.getElementById("download-report").addEventListener("click", async () => {
  if (!requireClient()) return;
  try {
    const report = await api(`/api/clients/${encodeURIComponent(selectedClient)}/report`);
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${selectedClient}_report.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    notify(error.message, true);
  }
});

loadClients().catch((error) => notify(error.message, true));
