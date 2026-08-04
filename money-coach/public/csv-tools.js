(function () {
function parseRows(text) {
  const rows = [];
  let row = [], value = "", quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') { value += '"'; index += 1; }
      else if (character === '"') quoted = false;
      else value += character;
    } else if (character === '"') quoted = true;
    else if (character === ",") { row.push(value); value = ""; }
    else if (character === "\n") { row.push(value); if (row.some((cell) => cell.trim())) rows.push(row); row = []; value = ""; }
    else if (character !== "\r") value += character;
  }
  row.push(value);
  if (row.some((cell) => cell.trim())) rows.push(row);
  return rows;
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function parseTransactionCsv(text, categories, createId = () => crypto.randomUUID()) {
  const rows = parseRows(text);
  if (rows.length < 2) throw new Error("The CSV needs a header row and at least one transaction.");
  const headers = rows[0].map((value) => value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_"));
  const find = (...names) => names.map((name) => headers.indexOf(name)).find((index) => index >= 0) ?? -1;
  const dateIndex = find("date", "transaction_date");
  const nameIndex = find("name", "merchant", "description", "transaction");
  const amountIndex = find("amount", "value");
  const typeIndex = find("type", "transaction_type");
  const categoryIndex = find("category");
  const noteIndex = find("note", "notes", "memo");
  if ([dateIndex, nameIndex, amountIndex].some((index) => index < 0)) throw new Error("CSV headers must include Date, Name, and Amount. Type, Category, and Note are optional.");
  const imported = [];
  for (const row of rows.slice(1, 5001)) {
    const rawDate = row[dateIndex]?.trim();
    const parsedDate = /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : new Date(rawDate);
    const date = typeof parsedDate === "string" ? parsedDate : Number.isNaN(parsedDate.getTime()) ? "" : new Date(parsedDate.getTime() - parsedDate.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const name = row[nameIndex]?.trim().slice(0, 80);
    let amount = Number(String(row[amountIndex] || "").replace(/[$,()]/g, ""));
    if (String(row[amountIndex]).includes("(")) amount = -Math.abs(amount);
    const type = row[typeIndex]?.trim().toLowerCase();
    if (type === "expense" || type === "debit") amount = -Math.abs(amount);
    if (type === "income" || type === "credit") amount = Math.abs(amount);
    if (!date || !name || !Number.isFinite(amount) || amount === 0 || Math.abs(amount) > 100000000) continue;
    const categoryRaw = row[categoryIndex]?.trim();
    const category = categories.find((item) => item.toLowerCase() === categoryRaw?.toLowerCase()) || (amount >= 0 ? "Income" : "Needs Review");
    imported.push({ id: createId(), source: "manual", date, name, amount: Math.round(amount * 100) / 100, category, note: row[noteIndex]?.trim().slice(0, 120) || "Imported from CSV", updatedAt: new Date().toISOString() });
  }
  if (!imported.length) throw new Error("No valid transaction rows were found. Check dates and amounts, then try again.");
  return imported;
}

function createTransactionCsv(transactions) {
  const header = ["Date", "Name", "Amount", "Type", "Category", "Note"];
  const rows = [...transactions]
    .sort((a, b) => b.date.localeCompare(a.date))
    .map((item) => [item.date, item.name, Math.abs(Number(item.amount)).toFixed(2), Number(item.amount) >= 0 ? "Income" : "Expense", item.category, item.note || ""]);
  return [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
}

globalThis.MoneyCoachCsv = Object.freeze({ parseTransactionCsv, createTransactionCsv });
})();
