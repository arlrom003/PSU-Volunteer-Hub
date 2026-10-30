(() => {
  const error = document.querySelector('.goal-form-error');
  if (error) {
    error.tabIndex = -1;
    error.focus();
  }
  let changed = false;
  document.querySelectorAll('form.goal-form').forEach((form) => {
    form.addEventListener('input', () => { changed = true; });
    form.addEventListener('submit', () => { changed = false; });
  });
  window.addEventListener('beforeunload', (event) => {
    if (!changed) return;
    event.preventDefault();
    event.returnValue = '';
  });
})();
