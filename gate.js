/* Prototype password gate. This is an embargo curtain, not security: the
   underlying files are public NYC Open Data aggregates in a public repo.
   Unlocks for the browser session on a SHA-256 match. */

'use strict';

(function () {
  const HASH = '90f077629ee17bf1216f752ea162f0706215b023d441def76d4cd5d510fb9549';
  const KEY = 'vcDisorderUnlocked';
  if (sessionStorage.getItem(KEY) === HASH) return;

  document.documentElement.classList.add('gated');

  const overlay = document.createElement('div');
  overlay.className = 'gate-overlay';
  overlay.innerHTML = `
    <div class="gate-box">
      <span class="gate-wordmark">VITAL CITY</span>
      <h1>The disorder index</h1>
      <p>This is an unpublished prototype. Enter the password to view it.</p>
      <form class="gate-form">
        <input type="password" autocomplete="off" aria-label="Password" autofocus>
        <button type="submit">Enter</button>
      </form>
      <p class="gate-err" hidden>That's not it — try again.</p>
    </div>`;

  async function check(pw) {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(pw));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function mount() {
    document.body.appendChild(overlay);
    overlay.querySelector('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const hex = await check(overlay.querySelector('input').value);
      if (hex === HASH) {
        sessionStorage.setItem(KEY, HASH);
        overlay.remove();
        document.documentElement.classList.remove('gated');
      } else {
        overlay.querySelector('.gate-err').hidden = false;
        overlay.querySelector('input').select();
      }
    });
  }

  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);
})();
