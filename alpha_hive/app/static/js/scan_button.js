(function () {
  const apiBase = ((window.BACKEND_URL || '') + '').replace(/\/$/, '');

  function showError(message) {
    const box = document.getElementById('scan_error_msg');
    if (!box) return;
    box.style.display = 'block';
    box.textContent = message;
  }

  async function refreshSnapshot() {
    try {
      const resp = await fetch(apiBase + '/snapshot?ts=' + Date.now(), { cache: 'no-store' });
      if (!resp.ok) return null;
      const data = await resp.json();
      if (typeof window.applySnapshot === 'function') {
        window.applySnapshot(data);
      } else if (typeof window.renderSnapshot === 'function') {
        window.renderSnapshot(data);
      } else if (typeof window.refresh === 'function') {
        await window.refresh();
      }
      return data;
    } catch (_) {
      return null;
    }
  }

  async function runManualScan(btn) {
    if (!btn || btn.dataset.scanBusy === '1') return;
    btn.dataset.scanBusy = '1';
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = 'wait';
    btn.style.opacity = '0.82';
    btn.textContent = '⟳ Escaneando...';
    const started = Date.now();

    try {
      const resp = await fetch(apiBase + '/atualizar', {
        method: 'POST',
        cache: 'no-store',
        headers: { 'Accept': 'application/json' }
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      await resp.json().catch(function () { return null; });
      await refreshSnapshot();
      const seconds = ((Date.now() - started) / 1000).toFixed(1).replace('.', ',');
      btn.textContent = '✓ Atualizado em ' + seconds + 's';
    } catch (err) {
      btn.textContent = '⚠ Erro no scan';
      showError('Falha ao escanear: ' + (err && err.message ? err.message : err));
    } finally {
      setTimeout(function () {
        btn.dataset.scanBusy = '0';
        btn.style.cursor = 'pointer';
        btn.style.opacity = '1';
        btn.textContent = '↻ Atualizar agora';
      }, 1200);
    }
  }

  function bindButton() {
    const btn = document.getElementById('scanStatusPill');
    if (!btn) return;
    btn.style.pointerEvents = 'auto';
    btn.style.cursor = btn.dataset.scanBusy === '1' ? 'wait' : 'pointer';
    btn.style.textAlign = 'center';
    btn.setAttribute('role', 'button');
    btn.setAttribute('tabindex', '0');
    btn.title = 'Clique para escanear agora';

    if (btn.dataset.scanBusy !== '1' && /escaneando|carregando/i.test(btn.textContent || '')) {
      btn.textContent = '↻ Atualizar agora';
    }

    if (btn.dataset.scanBound === '1') return;
    btn.dataset.scanBound = '1';
    btn.addEventListener('click', function () { runManualScan(btn); });
    btn.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        runManualScan(btn);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindButton);
  } else {
    bindButton();
  }

  try {
    new MutationObserver(bindButton).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  } catch (_) {}
})();
