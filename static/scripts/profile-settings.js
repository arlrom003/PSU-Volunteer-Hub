(() => {
  const forms = [...document.querySelectorAll('[data-profile-form]')];
  if (!forms.length) return;
  const openSection = () => {
    const section = document.getElementById(location.hash.slice(1));
    if (section?.matches('.profile-account-section')) section.open = true;
  };
  openSection();
  window.addEventListener('hashchange', openSection);
  const campus = document.getElementById('account-campus_id');
  const college = document.getElementById('account-college_affiliation');
  const colleges = JSON.parse(document.getElementById('profile-colleges').textContent);
  campus.addEventListener('change', () => {
    college.replaceChildren(new Option('Select your college', ''));
    (colleges[campus.value] || []).forEach(name => college.add(new Option(name, name)));
  });
  document.querySelectorAll('[data-profile-password]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => {
      const field = document.getElementById(button.dataset.profilePassword);
      const show = field.type === 'password';
      field.type = show ? 'text' : 'password';
      button.textContent = show ? 'Hide' : 'Show';
      button.setAttribute('aria-pressed', String(show));
      button.setAttribute('aria-label', `${show ? 'Hide' : 'Show'} ${document.querySelector(`label[for="${field.id}"]`).textContent.toLowerCase()}`);
    });
  });
  document.querySelector('[data-profile-errors]')?.focus();
  const snapshots = new Map();
  const values = form => JSON.stringify([...new FormData(form)].filter(([key]) => key !== 'csrf_token')
    .map(([key, value]) => [key, value instanceof File ? [value.name, value.size, value.lastModified] : value]));
  forms.forEach(form => snapshots.set(form, values(form)));
  let submitting = null;
  const restore = () => { submitting = null; };
  document.addEventListener('submit', event => {
    if (forms.includes(event.target) && !event.defaultPrevented) submitting = event.target;
  });
  window.addEventListener('beforeunload', event => {
    if (forms.some(form => form !== submitting && values(form) !== snapshots.get(form))) {
      event.preventDefault();
      event.returnValue = '';
      // A cancelled navigation must leave every form usable.
      setTimeout(() => {
        restore();
        document.dispatchEvent(new Event('form-submit-cancelled'));
      }, 0);
    }
  });
  window.addEventListener('pageshow', restore);
})();
