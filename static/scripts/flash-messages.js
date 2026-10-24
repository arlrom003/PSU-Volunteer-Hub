(() => {
  'use strict';
  document.querySelectorAll('[data-flash-dismiss]').forEach(button => {
    button.addEventListener('click', () => {
      const flash = button.closest('.flash');
      flash?.remove();
    });
  });
})();
