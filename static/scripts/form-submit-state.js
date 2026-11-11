(() => {
  const trackedButtons = new Set();

  const restoreButtons = () => {
    trackedButtons.forEach((button) => {
      button.removeAttribute('aria-disabled');
      button.classList.remove('is-submitting');
      button.removeAttribute('aria-busy');
      if (button.dataset.originalLabel) {
        button.innerHTML = button.dataset.originalLabel;
        delete button.dataset.originalLabel;
      }
      button.form?.removeAttribute('aria-busy');
    });
    trackedButtons.clear();
  };

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (event.defaultPrevented || !(form instanceof HTMLFormElement) || form.dataset.noSubmitState !== undefined) {
      return;
    }

    if (form.getAttribute('aria-busy') === 'true') {
      event.preventDefault();
      return;
    }

    const button = event.submitter;
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }

    button.dataset.originalLabel = button.innerHTML;
    // Native disabled submitters lose their name/value (for example, decision).
    // Keep the submitter successful; the busy-form guard prevents repeat submits.
    button.setAttribute('aria-disabled', 'true');
    button.classList.add('is-submitting');
    button.setAttribute('aria-busy', 'true');
    button.innerHTML = '<span class="submit-spinner" aria-hidden="true"></span><span>Working…</span>';
    form.setAttribute('aria-busy', 'true');
    trackedButtons.add(button);
  });

  window.addEventListener('pageshow', restoreButtons);
  document.addEventListener('form-submit-cancelled', restoreButtons);
})();
