'use strict';
const status = document.querySelector('#api-status');
fetch('/api/health').then(response => {
  if (!response.ok) throw new Error('Health check failed');
  return response.json();
}).then(data => {
  if (!data.ok || data.mode !== 'demo') throw new Error('Unexpected server');
  status.textContent = '● API ready / demo';
}).catch(() => { status.textContent = 'API unavailable — start server.py'; });

document.querySelector('#lead-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#submit-lead');
  const formStatus = document.querySelector('#form-status');
  const form = event.currentTarget;
  const lead = Object.fromEntries(new FormData(form));
  button.disabled = true;
  formStatus.textContent = 'Validating request…';
  // Clear stale success indicators before attempting another request.
  document.querySelectorAll('#steps li').forEach(item => item.classList.remove('done'));
  document.querySelector('#notification').textContent = 'Waiting for this request…';
  document.querySelector('#json-output').textContent = 'Waiting for this request…';
  try {
    const response = await fetch('/api/leads', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(lead),
      signal: AbortSignal.timeout(12000)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
    document.querySelectorAll('#steps li').forEach(item => item.classList.add('done'));
    document.querySelector('#steps li small').textContent = `Request ${data.id} validated.`;
    document.querySelector('#notification').textContent = data.notification.payload.text;
    document.querySelector('#json-output').textContent = JSON.stringify(data, null, 2);
    formStatus.textContent = `${data.id} · ${data.notice}`;
  } catch (error) {
    formStatus.textContent = error.name === 'TimeoutError'
      ? 'Request timed out. Check the local server and try again.'
      : `Request failed: ${error.message}`;
    document.querySelector('#notification').textContent = 'No notification was prepared for this request.';
    document.querySelector('#json-output').textContent = 'No successful response.';
    document.querySelector('#steps li small').textContent = 'Request did not complete.';
  } finally { button.disabled = false; }
});
