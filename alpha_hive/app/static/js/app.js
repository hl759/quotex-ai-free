async function refresh() {
  const resp = await fetch('/snapshot');
  const data = await resp.json();
  document.getElementById('decision').textContent = JSON.stringify(data.current_decision, null, 2);
  document.getElementById('signals').textContent = JSON.stringify(data.signals, null, 2);
  document.getElementById('meta').textContent = JSON.stringify(data.meta, null, 2);
}
async function runScan() {
  await fetch('/run-scan');
  await refresh();
}
refresh();
setInterval(refresh, 20000);
