(() => {
  const body = document.body;
  const role = body.dataset.tourRole;
  const replay = body.dataset.tourReplay === 'true';
  const firstUse = body.dataset.tourFirstUse === 'true';
  if (!role || (!replay && !firstUse) || !window.HTMLDialogElement) return;

  const steps = {
    volunteer: [
      ['profile', 'Complete your profile', 'Keep your interests and skills current so recommendations can compare relevant activities.'],
      ['opportunities', 'Find an activity', 'Browse available activities, review their schedule and agreement, then register when you are available.'],
      ['join-activity', 'Register for an activity', 'Open an opportunity, review the agreement and cancellation deadline, and confirm your participation.'],
      ['registrations', 'Review your registrations', 'Use this calendar and list to monitor upcoming commitments or request cancellation before the deadline.'],
      ['help', 'Get help when needed', 'The Help page explains registration, attendance, recommendations, and account access.'],
    ],
    coordinator: [
      ['annual-goals', 'Track Campus Goals', 'The large number shows approved annual targets achieved. Open it for AOP and ASP evidence, or use Campus Goal Proposals to submit a target for director approval.'],
      ['summary', 'Start with Campus Follow-Up', 'Review cancellation requests and complete attendance for ended activities. This unresolved work covers all dates; performance below uses its own reporting period.'],
      ['create-activity', 'Create an Activity', 'Add the activity details, target, cancellation deadline, and applicable SDGs before publishing.'],
      ['activity-workspace', 'Manage Activities', 'Use the activity filters and campus list to record attendance, publish updates, and upload milestones. The workspace is always visible below Performance Overview.'],
      ['attendance', 'Complete Attendance Records', 'Record present, absent, or excused attendance for each participant. After the activity ends, confirm completion for present participants so the results can support decisions.'],
      ['cancellations', 'Review Cancellations', 'Pending campus requests appear here when a decision is needed. An empty queue is labelled clearly; the navigation also opens the cancellation workspace.'],
      ['analytics', 'Use Analytics and Reports', 'Filter campus results, review attendance outcomes, then download the matching CSV or PDF report.'],
    ],
    director: [
      ['annual-goals', 'Review Annual-Plan Achievement', 'Open university targets and campus goals. Worst Performing Campus shows the lowest annual goal-achievement rate among campuses with approved targets, including ties and zero achievement.'],
      ['recognition', 'Review Outstanding Recognition', 'Review university-wide volunteer and campus rankings. Award Year is independent of report filters and the calendar month.'],
      ['calendar', 'Review the Activity Calendar', 'Review the complete university schedule for a month. Open an activity for its report evidence, or open the full calendar.'],
      ['campus-comparison', 'Compare Campuses', 'Set the report filters and review campus activity coverage. Open Analytics for the matching campus participation chart, attendance outcomes, and detailed activity report.'],
      ['reports', 'Download Reports', 'Choose CSV or PDF to download every activity matching the dashboard report filters.'],
      ['analytics', 'Review Detailed Analytics', 'The selected report scope follows you into Analytics and stays consistent through pagination and report downloads.'],
    ],
    admin: [
      ['summary', 'Check the system summary', 'Review the current database connection and account totals before making administrative changes.'],
      ['user-management', 'Manage users', 'Create, edit, assign roles, and deactivate accounts through this protected workspace.'],
      ['admin-controls', 'Configure the system', 'Use these controls for campuses, policies, categories, exports, backups, notifications, and settings.'],
      ['internal-reporting', 'Access internal reporting', 'Export user records from this protected administrative workspace.'],
    ],
  };

  const visibleTarget = (id) => Array.from(document.querySelectorAll(`[data-tour-id="${id}"]`))
    .find((node) => {
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      return rect.width > 0 && rect.height > 0 && rect.right > 0
        && rect.left < window.innerWidth && style.visibility !== 'hidden'
        && style.display !== 'none' && !node.closest('[hidden], [inert]');
    });
  const tourSteps = (steps[role] || []).map(([id, title, text]) => ({
    id, target: visibleTarget(id), title, text,
  })).filter((step) => step.target);
  if (!tourSteps.length) return;

  const dialog = document.createElement('dialog');
  dialog.className = 'first-use-tour';
  dialog.setAttribute('aria-labelledby', 'tourTitle');
  dialog.setAttribute('aria-describedby', 'tourText');
  dialog.innerHTML = `
    <div class="first-use-tour__spotlight" aria-hidden="true"></div>
    <section class="first-use-tour__card" aria-labelledby="tourTitle" aria-describedby="tourText">
      <p class="first-use-tour__count"></p>
      <h2 id="tourTitle"></h2>
      <p id="tourText" aria-live="polite"></p>
      <div class="first-use-tour__actions">
        <button class="btn btn--ghost" type="button" data-tour-skip>${['coordinator', 'director'].includes(role) ? 'Skip Guide' : 'Skip guide'}</button>
        <span class="first-use-tour__navigation">
          <button class="btn btn--outline" type="button" data-tour-back>Back</button>
          <button class="btn btn--primary" type="button" data-tour-next>Next</button>
        </span>
      </div>
    </section>`;
  document.body.append(dialog);

  const spotlight = dialog.querySelector('.first-use-tour__spotlight');
  const count = dialog.querySelector('.first-use-tour__count');
  const title = dialog.querySelector('#tourTitle');
  const text = dialog.querySelector('#tourText');
  const back = dialog.querySelector('[data-tour-back]');
  const next = dialog.querySelector('[data-tour-next]');
  const card = dialog.querySelector('.first-use-tour__card');
  const skip = dialog.querySelector('[data-tour-skip]');
  let index = 0;
  let target = null;

  const restoreFocus = () => {
    if (!target) return;
    if (!target.matches('a[href], button, input, select, textarea, [tabindex]')) {
      target.setAttribute('tabindex', '-1');
      target.addEventListener('blur', () => target.removeAttribute('tabindex'), { once: true });
    }
    target.focus({ preventScroll: true });
  };

  const dismiss = async () => {
    if (skip.disabled) return;
    skip.disabled = true;
    back.disabled = true;
    next.disabled = true;
    if (!replay) {
      const token = document.querySelector('meta[name="csrf-token"]')?.content;
      try {
        const response = await fetch(body.dataset.tourDismissUrl, {
          method: 'POST', credentials: 'same-origin',
          headers: token ? { 'X-CSRFToken': token, 'Accept': 'application/json' } : {},
        });
        if (!response.ok) throw new Error('Guide save failed');
      } catch (_) {
        text.textContent = 'The guide could not be saved. Please try again.';
        skip.disabled = back.disabled = next.disabled = false;
        return;
      }
    }
    dialog.close();
    resizeObserver.disconnect();
    restoreFocus();
  };

  const place = () => {
    if (!target) return;
    const currentTarget = visibleTarget(tourSteps[index].id);
    if (!currentTarget) {
      if (index < tourSteps.length - 1) {
        index += 1;
        show();
      } else dismiss();
      return;
    }
    target = currentTarget;
    const rect = spotlightTarget().getBoundingClientRect();
    spotlight.style.setProperty('--tour-x', `${Math.max(8, rect.left - 6)}px`);
    spotlight.style.setProperty('--tour-y', `${Math.max(8, rect.top - 6)}px`);
    spotlight.style.setProperty('--tour-width', `${Math.min(window.innerWidth - 16, rect.width + 12)}px`);
    spotlight.style.setProperty('--tour-height', `${Math.min(window.innerHeight - 16, rect.height + 12)}px`);
    if (window.innerWidth > 767) {
      const width = card.offsetWidth;
      const height = card.offsetHeight;
      const left = rect.right + width + 24 < window.innerWidth
        ? rect.right + 16 : Math.max(16, Math.min(rect.left, window.innerWidth - width - 16));
      const top = rect.bottom + height + 24 < window.innerHeight
        ? rect.bottom + 16 : Math.max(16, rect.top - height - 16);
      card.style.left = `${left}px`;
      card.style.top = `${Math.min(top, window.innerHeight - height - 16)}px`;
    } else {
      card.style.removeProperty('left');
      card.style.removeProperty('top');
    }
  };

  const spotlightTarget = () => {
    const availableHeight = window.innerHeight - card.offsetHeight - 48;
    if (window.innerWidth <= 767 && target.getBoundingClientRect().height > availableHeight) {
      return target.querySelector('.summary-stat, .panel__header, h2') || target;
    }
    return target;
  };

  const resizeObserver = new ResizeObserver(place);
  resizeObserver.observe(card);
  resizeObserver.observe(document.documentElement);

  const show = () => {
    const step = tourSteps[index];
    target = visibleTarget(step.id) || step.target;
    count.textContent = `Step ${index + 1} of ${tourSteps.length}`;
    title.textContent = step.title;
    text.textContent = step.text;
    back.hidden = index === 0;
    next.textContent = index === tourSteps.length - 1 ? 'Finish' : 'Next';
    spotlightTarget().scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
    if (window.innerWidth <= 767 && !target.closest('.role-sidebar')) {
      window.scrollBy({ top: card.offsetHeight / 2, behavior: 'instant' });
    }
    place();
    next.focus();
  };

  back.addEventListener('click', () => { index -= 1; show(); });
  next.addEventListener('click', () => {
    if (index === tourSteps.length - 1) dismiss();
    else { index += 1; show(); }
  });
  skip.addEventListener('click', dismiss);
  dialog.addEventListener('cancel', (event) => { event.preventDefault(); dismiss(); });
  dialog.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    const controls = Array.from(dialog.querySelectorAll('button'))
      .filter((button) => !button.hidden && !button.disabled);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (!controls.length) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  window.addEventListener('resize', place);
  window.addEventListener('scroll', place, true);
  dialog.showModal();
  show();
})();
