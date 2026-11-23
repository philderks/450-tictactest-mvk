const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

async function openPage(config, responses = {}) {
  const elements = Object.fromEntries(
    ['terminal', 'console-link', 'backend-version', 'frontend-version', 'notice']
      .map((id) => [id, { textContent: '', hidden: true }]),
  );
  const requests = [];
  const script = path.resolve(__dirname, '../../frontend/app.js');
  assert.ok(fs.existsSync(script), 'The frontend application must exist');
  await vm.runInNewContext(fs.readFileSync(script, 'utf8'), {
    window: { TICTACTEST_CONFIG: config },
    document: { getElementById: (id) => elements[id] },
    AbortSignal,
    fetch: async (url, options) => {
      requests.push({ url, options });
      const response = responses[url];
      if (!response) throw new Error('Connection failed');
      return { ok: response.ok !== false, text: async () => response.body };
    },
  });
  return { elements, requests };
}

test('uses configured URLs and displays independently fetched versions', async () => {
  const config = {
    consoleUrl: 'https://console.example.test/',
    backendVersionUrl: 'https://console.example.test/version.txt',
  };
  const { elements, requests } = await openPage(config, {
    [config.backendVersionUrl]: { body: '2.3.4\n' },
    'version.txt': { body: '5.6.7\n' },
  });
  assert.equal(elements.terminal.src, config.consoleUrl);
  assert.equal(elements['console-link'].href, config.consoleUrl);
  assert.equal(elements['backend-version'].textContent, '2.3.4');
  assert.equal(elements['frontend-version'].textContent, '5.6.7');
  assert.ok(requests.every(({ options }) => options.cache === 'no-store'));
});

test('missing configuration produces a visible message without opening a game', async () => {
  const { elements, requests } = await openPage(undefined);
  assert.equal(elements.terminal.src, undefined);
  assert.equal(requests.length, 0);
  assert.equal(elements.notice.hidden, false);
  assert.match(elements.notice.textContent, /config\.js/);
});

test('a failed backend version does not hide the frontend version or game', async () => {
  const config = {
    consoleUrl: 'https://console.example.test/',
    backendVersionUrl: 'https://console.example.test/version.txt',
  };
  const { elements } = await openPage(config, {
    [config.backendVersionUrl]: { ok: false, body: 'Gateway error' },
    'version.txt': { body: 'dev\n' },
  });
  assert.equal(elements['backend-version'].textContent, 'nicht erreichbar');
  assert.equal(elements['frontend-version'].textContent, 'dev');
  assert.equal(elements.terminal.src, config.consoleUrl);
  assert.equal(elements.notice.hidden, false);
  assert.match(elements.notice.textContent, /Netzwerk|CORS/);
});

test('release B shares its blue accent across heading, links and field numbers', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../../frontend/style.css'), 'utf8');
  assert.match(css, /--accent:\s*#a8cef4;/);
  assert.match(css, /h1 \{[^}]*color:\s*var\(--accent\)/);
  assert.match(css, /a \{[^}]*color:\s*var\(--accent\)/);
  assert.match(css, /\.positions \{[^}]*color:\s*var\(--accent\)/);
});
