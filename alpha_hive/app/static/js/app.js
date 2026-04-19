// RENDER FREE: polling reduzido de 20s → 90s
async function refresh() {
  try {
    const resp = await fetch('/snapshot');
    if (!resp.ok) return;
    const data = await resp.json();
    document.getElementById('decision').textContent =
      JSON.stringify(data.current_decision, null, 2);
    document.getElementById('signals').textContent =
      JSON.stringify(data.signals, null, 2);
    document.getElementById('meta').textContent =
      JSON.stringify(data.meta, null, 2);
  } catch (e) {
    console.warn('snapshot fetch error:', e);
  }
}

async function runScan() {
  await fetch('/run-scan');
  await refresh();
}

refresh();
setInterval(refresh, 90000); // era 20000
