// ON-DEMAND MODE: sem polling automático.
// Scans são ativados exclusivamente via botão "Atualizar agora" (POST /atualizar).
// Este arquivo é reserva; a UI principal usa o script embutido em index.html.

async function refresh() {
  try {
    const resp = await fetch('/snapshot');
    if (!resp.ok) return;
    const data = await resp.json();
    const dec = document.getElementById('decision');
    const sig = document.getElementById('signals');
    const meta = document.getElementById('meta');
    if (dec) dec.textContent = JSON.stringify(data.current_decision, null, 2);
    if (sig) sig.textContent = JSON.stringify(data.signals, null, 2);
    if (meta) meta.textContent = JSON.stringify(data.meta, null, 2);
  } catch (e) {
    console.warn('snapshot fetch error:', e);
  }
}

async function runScan() {
  const btn = document.querySelector('[onclick="runScan()"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Analisando...'; }
  try {
    await fetch('/atualizar', { method: 'POST' });
    await refresh();
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Atualizar agora'; }
  }
}

// Leitura única ao carregar — sem setInterval
refresh();
