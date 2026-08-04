"use strict";

const { createTransactionCsv, parseTransactionCsv } = window.MoneyCoachCsv;

const DB_NAME = "reid-wilson-money-coach";
const DB_VERSION = 1;
const STATE_KEY = "current";
const SESSION_KEY = "rw-money-coach-session";
const CATEGORIES = ["Housing", "Food", "Transport", "Utilities", "Bills", "Shopping", "Subscriptions", "Debt", "Health", "Education", "Savings", "Giving", "Income", "Needs Review", "Other"];
const BUDGET_CATEGORIES = CATEGORIES.filter((item) => !["Income", "Needs Review"].includes(item));

const defaultState = () => ({
  schemaVersion: 1,
  transactions: [],
  budget: { income: 0, categories: Object.fromEntries(BUDGET_CATEGORIES.map((category) => [category, 0])) },
  goals: [],
  bank: { connected: false, lastSyncedAt: null, environment: "sandbox" },
  updatedAt: new Date().toISOString()
});

let state = defaultState();
let statusTimer;
let budgetSaveTimer;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains("app")) database.createObjectStore("app");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readState() {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction("app", "readonly");
    const request = transaction.objectStore("app").get(STATE_KEY);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => database.close();
  });
}

async function writeState() {
  state.updatedAt = new Date().toISOString();
  const database = await openDatabase();
  await new Promise((resolve, reject) => {
    const transaction = database.transaction("app", "readwrite");
    transaction.objectStore("app").put(state, STATE_KEY);
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

async function clearState() {
  const database = await openDatabase();
  await new Promise((resolve, reject) => {
    const transaction = database.transaction("app", "readwrite");
    transaction.objectStore("app").delete(STATE_KEY);
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

function normalizeState(saved) {
  const clean = defaultState();
  if (!saved || typeof saved !== "object") return clean;
  clean.transactions = Array.isArray(saved.transactions) ? saved.transactions.filter(validTransaction).slice(0, 20000) : [];
  clean.goals = Array.isArray(saved.goals) ? saved.goals.filter((goal) => goal && typeof goal.name === "string").slice(0, 100) : [];
  clean.budget.income = safeNumber(saved.budget?.income);
  for (const category of BUDGET_CATEGORIES) clean.budget.categories[category] = safeNumber(saved.budget?.categories?.[category]);
  clean.bank = {
    connected: Boolean(saved.bank?.connected),
    lastSyncedAt: typeof saved.bank?.lastSyncedAt === "string" ? saved.bank.lastSyncedAt : null,
    environment: "sandbox"
  };
  clean.updatedAt = typeof saved.updatedAt === "string" ? saved.updatedAt : clean.updatedAt;
  return clean;
}

function validTransaction(item) {
  return item && typeof item.id === "string" && typeof item.name === "string" && Number.isFinite(Number(item.amount)) && /^\d{4}-\d{2}-\d{2}$/.test(item.date || "");
}

function safeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 100000000 ? Math.round(number * 100) / 100 : 0;
}

function signedNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && Math.abs(number) <= 100000000 ? Math.round(number * 100) / 100 : 0;
}

function money(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value) || 0);
}

function localToday() {
  const now = new Date();
  const adjusted = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(0, 10);
}

function thisMonthTransactions() {
  const prefix = localToday().slice(0, 7);
  return state.transactions.filter((item) => item.date.startsWith(prefix));
}

function totals(transactions = thisMonthTransactions()) {
  return transactions.reduce((result, item) => {
    const amount = signedNumber(item.amount);
    if (amount >= 0) result.income += amount;
    else result.expenses += Math.abs(amount);
    result.net += amount;
    return result;
  }, { income: 0, expenses: 0, net: 0 });
}

function announce(message, isError = false) {
  const element = $("#statusMessage");
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.add("show");
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => element.classList.remove("show"), 4200);
}

async function saveAndRender(message) {
  await writeState();
  renderAll();
  if (message) announce(message);
}

function showView(viewName) {
  $$("[data-view-panel]").forEach((panel) => {
    const active = panel.dataset.viewPanel === viewName;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  $$(".nav-button").forEach((button) => {
    const active = button.dataset.view === viewName;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  window.history.replaceState(null, "", `#${viewName}`);
  $("#mainContent").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setOptions(select, values, includeAll = false) {
  select.replaceChildren();
  if (includeAll) select.add(new Option("All categories", ""));
  for (const value of values) select.add(new Option(value, value));
}

function transactionRow(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "transaction-row";
  button.dataset.transactionId = item.id;
  button.setAttribute("aria-label", `Edit ${item.name}, ${money(item.amount)}, ${item.date}`);
  const main = document.createElement("span");
  main.className = "transaction-main";
  const name = document.createElement("strong");
  name.textContent = item.name;
  const note = document.createElement("small");
  note.textContent = item.note || (item.source === "plaid" ? "Plaid Sandbox test data" : "Manual entry");
  main.append(name, note);
  const date = document.createElement("span");
  date.className = "transaction-date";
  date.textContent = new Date(`${item.date}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  const category = document.createElement("span");
  category.className = "transaction-category";
  category.textContent = item.category || "Other";
  const amount = document.createElement("span");
  amount.className = `transaction-amount ${Number(item.amount) >= 0 ? "income" : "expense"}`;
  amount.textContent = `${Number(item.amount) >= 0 ? "+" : "−"}${money(Math.abs(Number(item.amount)))}`;
  button.append(main, date, category, amount);
  button.addEventListener("click", () => openTransactionDialog(item.id));
  return button;
}

function renderTransactionList(container, items, emptyText) {
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = emptyText;
    container.append(empty);
    return;
  }
  items.forEach((item) => container.append(transactionRow(item)));
}

function renderHome() {
  const monthTotals = totals();
  $("#homeIncome").textContent = money(monthTotals.income);
  $("#homeSpending").textContent = money(monthTotals.expenses);
  $("#homeRemaining").textContent = money(monthTotals.net);
  const goalTarget = state.goals.reduce((sum, goal) => sum + safeNumber(goal.target), 0);
  const goalSaved = state.goals.reduce((sum, goal) => sum + safeNumber(goal.saved), 0);
  const goalPercent = goalTarget ? Math.min(100, Math.round(goalSaved / goalTarget * 100)) : 0;
  $("#homeGoalProgress").textContent = `${goalPercent}%`;
  $("#homeGoalCaption").textContent = goalTarget ? `${money(goalSaved)} of ${money(goalTarget)}` : "Add a goal to begin";
  const sorted = [...state.transactions].sort((a, b) => b.date.localeCompare(a.date) || String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
  renderTransactionList($("#recentTransactions"), sorted.slice(0, 5), "No transactions yet. Add one manually or upload a CSV.");

  const planned = Object.values(state.budget.categories).reduce((sum, value) => sum + safeNumber(value), 0);
  const ratio = planned ? Math.round(monthTotals.expenses / planned * 100) : 0;
  $("#budgetPulseBar").style.width = `${Math.min(100, ratio)}%`;
  $("#budgetPulseTitle").textContent = planned ? `${ratio}% of planned spending used` : "Set your monthly budget";
  $("#budgetPulseText").textContent = planned ? `${money(Math.max(0, planned - monthTotals.expenses))} remains across your category limits.` : "Add income and category limits to see how you are tracking.";
  $("#budgetHighlights").innerHTML = planned ? `<div><span>Planned limits</span><strong>${money(planned)}</strong></div><div><span>Actual spending</span><strong>${money(monthTotals.expenses)}</strong></div>` : "";
}

function filteredTransactions() {
  const search = $("#transactionSearch").value.trim().toLowerCase();
  const category = $("#categoryFilter").value;
  return [...state.transactions]
    .filter((item) => !category || item.category === category)
    .filter((item) => !search || [item.name, item.note, item.category].some((value) => String(value || "").toLowerCase().includes(search)))
    .sort((a, b) => b.date.localeCompare(a.date));
}

function renderSpending() {
  const monthTotals = totals();
  $("#spendingIncome").textContent = money(monthTotals.income);
  $("#spendingExpenses").textContent = money(monthTotals.expenses);
  $("#spendingNet").textContent = money(monthTotals.net);
  $("#spendingCount").textContent = String(state.transactions.length);
  renderTransactionList($("#allTransactions"), filteredTransactions(), "No matching transactions. Adjust the filter or add a new entry.");
}

function renderBudgetForm() {
  $("#budgetIncome").value = state.budget.income || "";
  const container = $("#budgetCategoryFields");
  container.replaceChildren();
  for (const category of BUDGET_CATEGORIES) {
    const label = document.createElement("label");
    const title = document.createElement("span");
    title.textContent = category;
    const wrapper = document.createElement("span");
    wrapper.className = "input-wrap";
    const symbol = document.createElement("b");
    symbol.textContent = "$";
    const input = document.createElement("input");
    input.type = "number";
    input.inputMode = "decimal";
    input.min = "0";
    input.max = "100000000";
    input.step = "0.01";
    input.value = state.budget.categories[category] || "";
    input.placeholder = "0.00";
    input.dataset.budgetCategory = category;
    wrapper.append(symbol, input);
    label.append(title, wrapper);
    container.append(label);
  }
}

function renderBudgetSummary() {
  const month = thisMonthTransactions();
  const actualByCategory = Object.fromEntries(BUDGET_CATEGORIES.map((category) => [category, 0]));
  for (const transaction of month) {
    if (Number(transaction.amount) < 0 && transaction.category in actualByCategory) actualByCategory[transaction.category] += Math.abs(Number(transaction.amount));
  }
  const planned = Object.values(state.budget.categories).reduce((sum, value) => sum + safeNumber(value), 0);
  const actual = Object.values(actualByCategory).reduce((sum, value) => sum + value, 0);
  const remainder = state.budget.income - planned;
  $("#plannedTotal").textContent = money(planned);
  $("#actualTotal").textContent = money(actual);
  $("#plannedRemaining").textContent = money(remainder);
  const title = $("#budgetSummaryTitle");
  const message = $("#budgetSummaryMessage");
  if (!state.budget.income && !planned) {
    title.textContent = "Ready when you are";
    message.textContent = "Enter your income and category limits to build your monthly plan.";
    message.classList.remove("warning");
  } else if (remainder < 0) {
    title.textContent = "Your plan needs an adjustment";
    message.textContent = `Planned category limits exceed income by ${money(Math.abs(remainder))}. Lower one or more limits to balance the plan.`;
    message.classList.add("warning");
  } else {
    title.textContent = "Your monthly plan is balanced";
    message.textContent = `${money(remainder)} remains after all planned category limits.`;
    message.classList.remove("warning");
  }

  const list = $("#budgetComparison");
  list.replaceChildren();
  const visible = BUDGET_CATEGORIES.filter((category) => state.budget.categories[category] || actualByCategory[category]);
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Add at least one category limit to compare actual spending.";
    list.append(empty);
    return;
  }
  for (const category of visible) {
    const limit = safeNumber(state.budget.categories[category]);
    const spent = actualByCategory[category];
    const percent = limit ? Math.round(spent / limit * 100) : spent ? 100 : 0;
    const row = document.createElement("div");
    row.className = "comparison-item";
    const name = document.createElement("strong");
    name.textContent = category;
    const track = document.createElement("div");
    track.className = "comparison-track";
    const bar = document.createElement("span");
    bar.style.width = `${Math.min(100, percent)}%`;
    if (percent > 100) bar.classList.add("over");
    track.append(bar);
    const detail = document.createElement("small");
    detail.textContent = `${money(spent)} of ${money(limit)}`;
    row.append(name, track, detail);
    list.append(row);
  }
}

function renderGoals() {
  const container = $("#goalsList");
  container.replaceChildren();
  if (!state.goals.length) {
    const empty = document.createElement("article");
    empty.className = "panel empty-state";
    empty.innerHTML = "<h2>No goals yet</h2><p>Add an emergency fund, debt payoff, purchase, or other savings goal.</p>";
    const button = document.createElement("button");
    button.className = "button primary";
    button.textContent = "+ Add your first goal";
    button.addEventListener("click", () => openGoalDialog());
    empty.append(button);
    container.append(empty);
    return;
  }
  for (const goal of state.goals) {
    const target = safeNumber(goal.target);
    const saved = safeNumber(goal.saved);
    const percent = target ? Math.min(100, Math.round(saved / target * 100)) : 0;
    const card = document.createElement("article");
    card.className = "goal-card";
    const heading = document.createElement("h2");
    heading.textContent = goal.name;
    const amounts = document.createElement("div");
    amounts.className = "goal-amounts";
    amounts.innerHTML = `<span>${money(saved)} saved</span><strong>${percent}%</strong>`;
    const progress = document.createElement("div");
    progress.className = "goal-progress";
    progress.innerHTML = `<span style="width:${percent}%"></span>`;
    const remaining = document.createElement("p");
    remaining.className = "muted";
    remaining.textContent = `${money(Math.max(0, target - saved))} remaining of ${money(target)}`;
    const date = document.createElement("p");
    date.className = "goal-date";
    date.textContent = goal.date ? `Target: ${new Date(`${goal.date}T12:00:00`).toLocaleDateString()}` : "No target date";
    const button = document.createElement("button");
    button.className = "button";
    button.textContent = "Update goal";
    button.addEventListener("click", () => openGoalDialog(goal.id));
    card.append(heading, amounts, progress, remaining, date, button);
    container.append(card);
  }
}

function renderCoach() {
  const cards = [];
  const month = thisMonthTransactions();
  const monthTotals = totals(month);
  const planned = Object.values(state.budget.categories).reduce((sum, value) => sum + safeNumber(value), 0);
  if (!state.transactions.length) {
    cards.push(["Start here", "Add your first transaction", "A few current entries will let Coach find useful patterns. Manual entry and CSV upload both work."]);
  } else {
    cards.push(["Monthly cash flow", monthTotals.net >= 0 ? "Income is ahead of spending" : "Spending is ahead of income", monthTotals.net >= 0 ? `You have ${money(monthTotals.net)} remaining from this month’s recorded activity.` : `Recorded spending is ${money(Math.abs(monthTotals.net))} above recorded income this month. Review large or flexible categories first.`]);
  }
  const categoryTotals = {};
  for (const item of month.filter((entry) => Number(entry.amount) < 0)) categoryTotals[item.category] = (categoryTotals[item.category] || 0) + Math.abs(Number(item.amount));
  const top = Object.entries(categoryTotals).sort((a, b) => b[1] - a[1])[0];
  if (top) cards.push(["Spending pattern", `${top[0]} is your largest category`, `${money(top[1])} is recorded in ${top[0]} this month. Check the entries for accuracy, then decide whether that level supports your priorities.`]);
  else cards.push(["Spending pattern", "No expense pattern yet", "Record or upload expenses to see which category is using the most money."]);
  if (planned) {
    const ratio = monthTotals.expenses / planned;
    cards.push(["Budget check", ratio <= 1 ? "You are within planned limits" : "You are above planned limits", ratio <= 1 ? `${money(planned - monthTotals.expenses)} remains across your category limits.` : `Actual spending is ${money(monthTotals.expenses - planned)} above the total of your current limits.`]);
  } else cards.push(["Budget check", "Create category limits", "A simple monthly plan makes it easier to spot a category that needs attention before the month ends."]);
  const nextGoal = [...state.goals].sort((a, b) => (safeNumber(a.target) - safeNumber(a.saved)) - (safeNumber(b.target) - safeNumber(b.saved)))[0];
  if (nextGoal) cards.push(["Goal focus", `${nextGoal.name}: ${money(Math.max(0, safeNumber(nextGoal.target) - safeNumber(nextGoal.saved)))} to go`, nextGoal.date ? `The target date is ${new Date(`${nextGoal.date}T12:00:00`).toLocaleDateString()}. Update the saved amount after each contribution.` : "Adding a target date can make the next contribution easier to plan."]);
  else cards.push(["Goal focus", "Choose one clear goal", "Start with one amount you want to reach, then update it whenever you make progress."]);
  const container = $("#coachCards");
  container.replaceChildren();
  for (const [label, title, text] of cards) {
    const card = document.createElement("article");
    card.className = "coach-card";
    card.innerHTML = `<p class="coach-label"></p><h2></h2><p></p>`;
    card.children[0].textContent = label;
    card.children[1].textContent = title;
    card.children[2].textContent = text;
    container.append(card);
  }
}

function renderTrust() {
  $("#bankStatusTitle").textContent = state.bank.connected ? "Sandbox bank connected" : "No test bank connected";
  $("#bankStatusText").textContent = state.bank.connected ? `Fictional Sandbox data${state.bank.lastSyncedAt ? ` last synced ${new Date(state.bank.lastSyncedAt).toLocaleString()}` : " is ready to sync"}.` : "Linking is optional. Manual entry and CSV upload remain fully available.";
  $("#syncBankButton").hidden = !state.bank.connected;
  $("#disconnectBankButton").hidden = !state.bank.connected;
}

function renderAll() {
  renderHome();
  renderSpending();
  renderBudgetSummary();
  renderGoals();
  renderCoach();
  renderTrust();
}

function openTransactionDialog(id = "") {
  const item = state.transactions.find((entry) => entry.id === id);
  $("#transactionDialogTitle").textContent = item ? "Update transaction" : "Add transaction";
  $("#transactionId").value = item?.id || "";
  $("#transactionDate").value = item?.date || localToday();
  $("#transactionAmount").value = item ? Math.abs(Number(item.amount)) : "";
  $("#transactionName").value = item?.name || "";
  $("#transactionCategory").value = item?.category || (item && Number(item.amount) >= 0 ? "Income" : "Other");
  $("#transactionNote").value = item?.note || "";
  const type = item && Number(item.amount) >= 0 ? "income" : "expense";
  $$("input[name=transactionType]").forEach((radio) => radio.checked = radio.value === type);
  $("#deleteTransactionButton").hidden = !item;
  $("#transactionError").textContent = "";
  $("#transactionDialog").showModal();
  setTimeout(() => $(item ? "#transactionName" : "#transactionAmount").focus(), 40);
}

async function submitTransaction(event) {
  event.preventDefault();
  const amount = safeNumber($("#transactionAmount").value);
  const name = $("#transactionName").value.trim();
  const date = $("#transactionDate").value;
  const category = $("#transactionCategory").value;
  const type = $("input[name=transactionType]:checked").value;
  if (!amount || !name || !date || !category) {
    $("#transactionError").textContent = "Enter a date, amount, name, and category.";
    return;
  }
  const id = $("#transactionId").value;
  const existing = state.transactions.find((item) => item.id === id);
  const record = {
    id: id || crypto.randomUUID(),
    source: existing?.source || "manual",
    date,
    name: name.slice(0, 80),
    amount: type === "income" ? amount : -amount,
    category,
    note: $("#transactionNote").value.trim().slice(0, 120),
    userEdited: Boolean(existing?.source === "plaid" || existing?.userEdited),
    updatedAt: new Date().toISOString()
  };
  if (existing) state.transactions[state.transactions.indexOf(existing)] = { ...existing, ...record };
  else state.transactions.push(record);
  $("#transactionDialog").close();
  await saveAndRender(existing ? "Transaction updated." : "Transaction added.");
}

async function deleteCurrentTransaction() {
  const id = $("#transactionId").value;
  if (!id || !(await confirmAction("Delete transaction?", "This removes the selected entry from this device."))) return;
  state.transactions = state.transactions.filter((item) => item.id !== id);
  $("#transactionDialog").close();
  await saveAndRender("Transaction deleted.");
}

function openGoalDialog(id = "") {
  const goal = state.goals.find((item) => item.id === id);
  $("#goalDialogTitle").textContent = goal ? "Update goal" : "Add goal";
  $("#goalId").value = goal?.id || "";
  $("#goalName").value = goal?.name || "";
  $("#goalTarget").value = goal?.target || "";
  $("#goalSaved").value = goal?.saved || 0;
  $("#goalDate").value = goal?.date || "";
  $("#deleteGoalButton").hidden = !goal;
  $("#goalError").textContent = "";
  $("#goalDialog").showModal();
  setTimeout(() => $("#goalName").focus(), 40);
}

async function submitGoal(event) {
  event.preventDefault();
  const name = $("#goalName").value.trim();
  const target = safeNumber($("#goalTarget").value);
  const saved = safeNumber($("#goalSaved").value);
  if (!name || !target) {
    $("#goalError").textContent = "Enter a goal name and a target greater than $0.";
    return;
  }
  const id = $("#goalId").value;
  const existing = state.goals.find((goal) => goal.id === id);
  const record = { id: id || crypto.randomUUID(), name: name.slice(0, 80), target, saved, date: $("#goalDate").value || "", updatedAt: new Date().toISOString() };
  if (existing) state.goals[state.goals.indexOf(existing)] = record;
  else state.goals.push(record);
  $("#goalDialog").close();
  await saveAndRender(existing ? "Goal updated." : "Goal added.");
}

async function deleteCurrentGoal() {
  const id = $("#goalId").value;
  if (!id || !(await confirmAction("Delete goal?", "This removes the goal and its progress from this device."))) return;
  state.goals = state.goals.filter((goal) => goal.id !== id);
  $("#goalDialog").close();
  await saveAndRender("Goal deleted.");
}

function confirmAction(title, text, confirmLabel = "Confirm") {
  return new Promise((resolve) => {
    const dialog = $("#confirmDialog");
    $("#confirmTitle").textContent = title;
    $("#confirmText").textContent = text;
    $("#confirmAction").textContent = confirmLabel;
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
    dialog.showModal();
  });
}

async function importCsv(file) {
  try {
    if (!file || file.size > 5_000_000) throw new Error("Choose a CSV file smaller than 5 MB.");
    const imported = parseTransactionCsv(await file.text(), CATEGORIES);
    state.transactions.push(...imported);
    await saveAndRender(`${imported.length} transaction${imported.length === 1 ? "" : "s"} imported.`);
  } catch (error) {
    announce(error instanceof Error ? error.message : "Could not import that CSV.", true);
  } finally {
    $("#csvFileInput").value = "";
  }
}

function download(name, content, type) {
  const link = document.createElement("a");
  const url = URL.createObjectURL(new Blob([content], { type }));
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportCsv() {
  download(`money-coach-transactions-${localToday()}.csv`, createTransactionCsv(state.transactions), "text/csv;charset=utf-8");
  announce("CSV downloaded.");
}

function backupData() {
  const backup = { product: "Reid & Wilson Money Coach", formatVersion: 1, exportedAt: new Date().toISOString(), data: state };
  download(`money-coach-backup-${localToday()}.json`, JSON.stringify(backup, null, 2), "application/json");
  announce("Backup downloaded. Keep it somewhere private.");
}

async function restoreData(file) {
  try {
    if (!file || file.size > 10_000_000) throw new Error("Choose a Money Coach backup smaller than 10 MB.");
    const backup = JSON.parse(await file.text());
    if (backup?.product !== "Reid & Wilson Money Coach" || backup?.formatVersion !== 1 || !backup.data) throw new Error("That file is not a supported Money Coach backup.");
    if (!(await confirmAction("Replace current data?", "Restoring this backup replaces the transactions, budget, and goals currently saved in this browser.", "Restore backup"))) return;
    state = normalizeState(backup.data);
    await saveAndRender("Backup restored.");
  } catch (error) {
    announce(error instanceof Error ? error.message : "Could not restore that backup.", true);
  } finally {
    $("#backupFileInput").value = "";
  }
}

async function ensureSession() {
  let token = localStorage.getItem(SESSION_KEY);
  if (token) return token;
  const response = await fetch("/api/session/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const data = await response.json();
  if (!response.ok || !data.session_token) throw new Error(data.message || "Could not start a secure bank-linking session.");
  token = data.session_token;
  localStorage.setItem(SESSION_KEY, token);
  return token;
}

async function api(path, options = {}, retry = true) {
  const token = await ensureSession();
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(options.headers || {}) }
  });
  if (response.status === 401 && retry) {
    localStorage.removeItem(SESSION_KEY);
    return api(path, options, false);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || "The secure service could not complete that request.");
  return data;
}

async function connectBank() {
  try {
    if (window.self !== window.top) {
      window.open(`${location.origin}/#trust`, "_blank", "noopener,noreferrer");
      announce("Money Coach opened in a full browser tab. Choose Link a test bank there to continue securely.");
      return;
    }
    if (!window.Plaid) throw new Error("The Plaid Sandbox window could not load. Check your connection and try again.");
    announce("Preparing the secure Plaid Sandbox window…");
    const linkData = await api("/api/plaid/link-token", { method: "POST", body: JSON.stringify({ platform: "web" }) });
    const handler = window.Plaid.create({
      token: linkData.link_token,
      onSuccess: async (publicToken) => {
        try {
          await api("/api/plaid/exchange", { method: "POST", body: JSON.stringify({ public_token: publicToken }) });
          state.bank.connected = true;
          state.bank.environment = "sandbox";
          await syncBank();
        } catch (error) { announce(error.message || "Could not finish linking the test bank.", true); }
      },
      onExit: (error) => { if (error) announce("Plaid Sandbox closed before the connection finished.", true); }
    });
    handler.open();
  } catch (error) {
    announce(error instanceof Error ? error.message : "Bank linking is unavailable. Manual tools still work.", true);
  }
}

async function syncBank() {
  try {
    announce("Syncing fictional Sandbox transactions…");
    const data = await api("/api/plaid/sync", { method: "POST", body: "{}" });
    const existing = new Map(state.transactions.map((item) => [item.id, item]));
    for (const incoming of data.transactions || []) {
      const prior = existing.get(incoming.id);
      const normalized = { ...incoming, note: prior?.note || "Plaid Sandbox test data", userEdited: prior?.userEdited || false, updatedAt: new Date().toISOString() };
      if (prior?.userEdited) {
        normalized.name = prior.name;
        normalized.category = prior.category;
        normalized.note = prior.note;
      }
      existing.set(incoming.id, normalized);
    }
    state.transactions = Array.from(existing.values());
    state.bank.connected = true;
    state.bank.lastSyncedAt = data.last_synced_at || new Date().toISOString();
    await saveAndRender("Plaid Sandbox test transactions synced.");
  } catch (error) {
    announce(error instanceof Error ? error.message : "Could not sync the test bank.", true);
  }
}

async function disconnectBank() {
  if (!(await confirmAction("Disconnect Sandbox bank?", "This revokes the test connection and removes synced Sandbox transactions from this device. Manual data stays saved.", "Disconnect"))) return;
  try {
    await api("/api/plaid/disconnect", { method: "POST", body: JSON.stringify({ deleteSyncedData: true }) });
    state.transactions = state.transactions.filter((item) => item.source !== "plaid");
    state.bank = { connected: false, lastSyncedAt: null, environment: "sandbox" };
    await saveAndRender("Sandbox bank disconnected and test data removed.");
  } catch (error) { announce(error instanceof Error ? error.message : "Could not disconnect the test bank.", true); }
}

async function deleteAllData() {
  if (!(await confirmAction("Delete all Money Coach data?", "This permanently erases transactions, budgets, goals, and any Sandbox bank connection for this browser. Download a backup first if you may need it.", "Delete everything"))) return;
  try {
    const token = localStorage.getItem(SESSION_KEY);
    if (token) {
      await fetch("/api/session/data", { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    }
  } catch { /* Local deletion must still finish if the server is unavailable. */ }
  await clearState();
  localStorage.removeItem(SESSION_KEY);
  state = defaultState();
  renderBudgetForm();
  renderAll();
  announce("Money Coach data deleted from this browser.");
}

function handleAction(action) {
  const actions = {
    "add-transaction": () => openTransactionDialog(),
    "add-goal": () => openGoalDialog(),
    "import-csv": () => $("#csvFileInput").click(),
    "export-csv": exportCsv,
    "backup-data": backupData,
    "restore-data": () => $("#backupFileInput").click(),
    "connect-bank": connectBank,
    "sync-bank": syncBank,
    "disconnect-bank": disconnectBank,
    "delete-data": deleteAllData
  };
  actions[action]?.();
}

async function initialize() {
  try { state = normalizeState(await readState()); }
  catch { announce("Saved data could not be opened. Nothing was uploaded or replaced.", true); }
  setOptions($("#transactionCategory"), CATEGORIES);
  setOptions($("#categoryFilter"), CATEGORIES, true);
  renderBudgetForm();
  renderAll();
  const initialView = location.hash.replace("#", "");
  showView(["home", "spending", "budget", "goals", "coach", "trust"].includes(initialView) ? initialView : "home");

  document.addEventListener("click", (event) => {
    const viewButton = event.target.closest("[data-view]");
    if (viewButton) showView(viewButton.dataset.view);
    const actionButton = event.target.closest("[data-action]");
    if (actionButton) handleAction(actionButton.dataset.action);
    const closeButton = event.target.closest("[data-close-dialog]");
    if (closeButton) closeButton.closest("dialog")?.close();
  });
  $("#transactionForm").addEventListener("submit", submitTransaction);
  $("#deleteTransactionButton").addEventListener("click", deleteCurrentTransaction);
  $("#goalForm").addEventListener("submit", submitGoal);
  $("#deleteGoalButton").addEventListener("click", deleteCurrentGoal);
  $("#transactionSearch").addEventListener("input", renderSpending);
  $("#categoryFilter").addEventListener("change", renderSpending);
  $("#csvFileInput").addEventListener("change", (event) => importCsv(event.target.files[0]));
  $("#backupFileInput").addEventListener("change", (event) => restoreData(event.target.files[0]));
  $("#budgetForm").addEventListener("input", (event) => {
    if (event.target.id === "budgetIncome") state.budget.income = safeNumber(event.target.value);
    if (event.target.dataset.budgetCategory) state.budget.categories[event.target.dataset.budgetCategory] = safeNumber(event.target.value);
    renderBudgetSummary();
    renderHome();
    clearTimeout(budgetSaveTimer);
    budgetSaveTimer = setTimeout(() => writeState().then(() => announce("Budget saved.")), 550);
  });
  $("#resetBudget").addEventListener("click", async () => {
    if (!(await confirmAction("Reset monthly budget?", "This clears income and all category limits. Transactions and goals are not changed.", "Reset budget"))) return;
    state.budget = defaultState().budget;
    renderBudgetForm();
    await saveAndRender("Budget reset.");
  });
  $$(".modal").forEach((dialog) => dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  }));
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(() => {});
}

initialize();
