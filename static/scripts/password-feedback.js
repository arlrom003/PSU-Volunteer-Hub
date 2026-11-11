(() => {
  document.querySelectorAll('[data-password-feedback]').forEach(panel => {
    const input = document.getElementById(panel.dataset.passwordInput);
    const confirmation = document.getElementById(panel.dataset.passwordConfirmation);
    if (!input || !confirmation) return;
    const minimum = Number(panel.dataset.passwordMinimum);
    const meter = panel.querySelector('[data-password-meter]');
    const summary = panel.querySelector('[data-password-summary]');
    const descriptions = new Set((input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
    descriptions.add(summary.id);
    input.setAttribute('aria-describedby', [...descriptions].join(' '));
    meter.hidden = false;

    const update = () => {
      const password = input.value;
      const length = [...password].length;
      const rules = {
        length: length >= minimum,
        uppercase: /[A-Z]/.test(password),
        lowercase: /[a-z]/.test(password),
        number: /\p{Decimal_Number}/u.test(password),
        special: /[^A-Za-z0-9]/.test(password),
        match: password.length > 0 && password === confirmation.value,
      };
      const completed = Object.values(rules).filter(Boolean).length;
      const message = completed === 6 ? 'All 6 password requirements met.' : `Password requirements: ${completed} of 6 met.`;
      if (summary.textContent !== message) summary.textContent = message;
      meter.value = completed;
      meter.setAttribute('aria-valuetext', message);
      panel.querySelectorAll('[data-password-rule]').forEach(row => {
        const met = rules[row.dataset.passwordRule];
        row.classList.toggle('is-met', met);
        row.querySelector('[data-rule-icon]').textContent = met ? '✓' : '○';
        row.querySelector('[data-rule-state]').textContent = met ? 'Met' : 'Needed';
      });
    };
    input.addEventListener('input', update);
    confirmation.addEventListener('input', update);
    input.addEventListener('change', update);
    confirmation.addEventListener('change', update);
    window.addEventListener('pageshow', update);
    input.form?.addEventListener('reset', () => setTimeout(update, 0));
    update();
  });
})();
