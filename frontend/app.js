(async () => {
  const config = window.TICTACTEST_CONFIG;
  if (!config?.consoleUrl || !config?.backendVersionUrl) {
    const notice = document.getElementById('notice');
    notice.hidden = false;
    notice.textContent = 'Die Server-Adressen fehlen. Bitte config.js prüfen.';
    return;
  }
  document.getElementById('terminal').src = config.consoleUrl;
  document.getElementById('console-link').href = config.consoleUrl;

  async function showVersion(url, id) {
    try {
      const response = await fetch(url, {
        cache: 'no-store',
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error('Version request failed');
      document.getElementById(id).textContent = (await response.text()).trim();
    } catch {
      document.getElementById(id).textContent = 'nicht erreichbar';
      const notice = document.getElementById('notice');
      notice.hidden = false;
      notice.textContent = 'Eine Versionsabfrage ist fehlgeschlagen. Prüfe Konfiguration, Netzwerk und die Browser-Konsole (z. B. CORS).';
    }
  }

  await Promise.all([
    showVersion(config.backendVersionUrl, 'backend-version'),
    showVersion('version.txt', 'frontend-version'),
  ]);
})();
